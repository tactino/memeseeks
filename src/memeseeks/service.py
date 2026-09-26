"""What the web server needs from a library: fresh searcher, safe file lookup, thumbnails, 旧梗重温."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import random
import threading
import time
from pathlib import Path

from .albums import LIKED, CollectionError, Collections, Removed
from .images import load_image
from .inbox import PROVENANCE_FILE, read_provenance
from .review import Review
from .index import _atomic_write_text, _tmp_for
from .search import Searcher
from .settings import Settings

THUMB_QUALITY = 82
# Everything a Searcher reads: if any of these changed, rebuild it (an add writes them over minutes).
_WATCHED = ["paths.json", "relpaths.json", "ocr.jsonl", "vlm.jsonl", "clip_ids.json", "clip.npy",
            "text_ocr.json", "text_vlm.json"]


# Platform watermarks the OCR reads along with the meme ("小红书号：95037120793", "微博：@今日memes").
# They are hidden when text is shown; search still uses the text as read.
_WATERMARKS = re.compile(
    r"(小红书号|抖音号|快手号|B站|bilibili|微博|微信号|公众号)\s*[:：]?\s*@?[\w.-]+|@[\w\u4e00-\u9fff.-]{2,}|(?<!\S)小红书(?!\S)",
    re.IGNORECASE)


def display_text(text: str) -> str:
    cleaned = _WATERMARKS.sub(" ", text or "")
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def pick_rediscover(ids: list[str], seen: dict[str, float], n: int, now: float, rng) -> list[str]:
    """Never-shown memes first, then the least recently shown; ties broken at random."""
    return sorted(ids, key=lambda i: (seen.get(i, 0.0), rng.random()))[:n]


class LibraryService:
    def __init__(self, library, models, rng=None, clock=time.time):
        self.library, self.models = library, models
        self.rng, self.clock = rng or random.Random(), clock
        self._searcher, self._stamp = None, None
        self._searcher_lock = threading.Lock()
        self._seen_lock = threading.Lock()
        self._provenance, self._provenance_stamp = {}, None
        self.review = Review(library)
        self.albums = Collections(library.root, clock=clock)
        self.removed = Removed(library.root)
        self.settings = Settings(library.root)
        self._numbers, self._numbers_lock = None, threading.Lock()

    def _index_stamp(self):
        stamps = []
        for name in [*_WATCHED, "../library.json"]:
            try:
                stamps.append(os.stat(self.library.index_dir / name).st_mtime_ns)
            except OSError:
                stamps.append(None)
        return tuple(stamps)

    def searcher(self) -> Searcher:
        """Rebuilt whenever `memeseeks add` changed the index, so the server never needs a restart."""
        with self._searcher_lock:  # one rebuild at a time, one model load at a time
            stamp = self._index_stamp()
            if self._searcher is None or stamp != self._stamp:
                self._searcher, self._stamp = Searcher(self.library, self.models), stamp
            return self._searcher

    def warm(self) -> None:
        """Load the index and the query-side models now, so the first search is as fast as the rest."""
        self.searcher().search("warm up", k=1)

    def sources(self) -> dict[str, list[dict]]:
        """Where inbox memes came from, re-read only when the file changed."""
        try:
            stamp = os.stat(self.library.root / PROVENANCE_FILE).st_mtime_ns
        except OSError:
            stamp = None
        if stamp != self._provenance_stamp:
            self._provenance, self._provenance_stamp = read_provenance(self.library.root), stamp
        return self._provenance

    def numbers(self, s: Searcher | None = None) -> dict[str, int]:
        """Each meme's No.: given once, in the order memes came in, and never changed (numbers.json).
        A folder of old files added later gets new numbers; it never renumbers what you already have."""
        s = s or self.searcher()
        with self._numbers_lock:
            if self._numbers is None:
                try:
                    self._numbers = json.loads((self.library.root / "numbers.json").read_text(encoding="utf-8"))["numbers"]
                except (OSError, json.JSONDecodeError, KeyError):
                    self._numbers = {}
            new = [i for i in s.ids if i not in self._numbers]
            if new:
                start = max(self._numbers.values(), default=0) + 1
                for n, i in enumerate(sorted(new, key=lambda i: (self.added_at(i, s), i)), start):
                    self._numbers[i] = n
                _atomic_write_text(self.library.root / "numbers.json",
                                   json.dumps({"version": 1, "numbers": self._numbers}))
            return self._numbers

    def today(self, day: datetime.date | None = None) -> dict | None:
        """今日一梗: one meme with text per day, the same all day on every device."""
        s = self.searcher()
        pool = sorted(i for i in self.visible(s) if s.text.get(i))
        if not pool:
            return None
        day = day or datetime.date.today()
        pick = int(hashlib.sha256(day.isoformat().encode()).hexdigest(), 16) % len(pool)
        return self._item(s, pool[pick])

    def _item(self, s: Searcher, i: str, score: float | None = None, match: float | None = None) -> dict:
        item = {"id": i, "score": score, "match": match, "text": display_text(s.text.get(i, "")), "relpath": s.relpath[i],
                "no": self.numbers(s).get(i)}
        found = self.sources().get(i)
        if found:  # the first place it was collected from
            item["source"] = {k: found[0][k] for k in ("site", "page_url", "page_title") if k in found[0]}
        return item

    def _hidden(self, s: Searcher) -> set[str]:
        """Not shown anywhere: waiting in 待确认, rejected there, or removed from the library."""
        return self.review.hidden(s.paths, s.text) | self.removed.ids()

    def visible(self, s: Searcher | None = None) -> list[str]:
        s = s or self.searcher()
        hidden = self._hidden(s)
        return [i for i in s.ids if i not in hidden]

    def added_at(self, image_id: str, s: Searcher | None = None) -> float:
        """When a meme came in: when it was collected, else the file's modification time."""
        collected = self._collected_at(image_id)
        if collected:
            return collected
        try:
            return os.stat((s or self.searcher()).paths[image_id]).st_mtime
        except (OSError, KeyError):
            return 0.0

    # ---------- 相似的梗 and the meme page ----------

    def similar(self, image_id: str, k: int = 12) -> list[dict]:
        s = self.searcher()
        hidden = self._hidden(s)
        found = [(i, sc) for i, sc in s.similar(image_id) if i not in hidden][:k]
        return [self._item(s, i, score=sc) for i, sc in found]

    def meme(self, image_id: str, similar: bool = True) -> dict | None:
        s = self.searcher()
        if image_id not in s.paths or image_id in self._hidden(s):
            return None
        item = self._item(s, image_id)
        item["sources"] = [{k: src[k] for k in ("site", "page_url", "page_title", "at") if k in src}
                           for src in self.sources().get(image_id, [])]
        item["albums"] = self.albums.containing(image_id)
        item["liked"] = LIKED in item["albums"]
        item["added"] = self.added_at(image_id, s)
        item["similar"] = self.similar(image_id) if similar else []
        return item

    # ---------- 图集 ----------

    def album_list(self) -> list[dict]:
        """全部, 我喜欢 and your 图集, each with its count and cover (the newest meme in it)."""
        s = self.searcher()
        visible = self.visible(s)
        shown = set(visible)
        newest = max(visible, key=lambda i: self.added_at(i, s), default=None)
        out = [{"id": "all", "name": "全部", "count": len(visible), "cover": newest, "created": 0}]
        for a in self.albums.all():
            items = [it["id"] for it in a["items"] if it["id"] in shown]
            out.append({"id": a["id"], "name": a["name"], "count": len(items),
                        "cover": items[-1] if items else None, "created": a["created"]})
        return out

    def _album_ids(self, s: Searcher, cid: str, sort: str) -> tuple[str, list[str]]:
        shown = set(self.visible(s))
        if cid == "all":
            name = "全部"
            ids = sorted(shown, key=lambda i: (self.added_at(i, s), i))       # oldest first, like a 图集
        else:
            a = self.albums.get(cid)
            name, ids = a["name"], [it["id"] for it in a["items"] if it["id"] in shown]
        return name, ids[::-1] if sort == "new" else ids

    def album(self, cid: str, sort: str = "new") -> dict:
        s = self.searcher()
        name, ids = self._album_ids(s, cid, sort)
        return {"id": cid, "name": name, "count": len(ids), "items": [self._item(s, i) for i in ids]}

    # ---------- 刷梗 ----------

    def feed(self, album: str | None = None, meme: str | None = None, order: str = "new", seed: int = 0) -> list[str] | None:
        """The order 刷梗 shows memes in (docs/design.md, Pages and navigation); None for an unknown meme.
        A shuffle is seeded, so the same seed gives the same order and a stopped 刷梗 can resume."""
        s = self.searcher()
        rng = random.Random(seed)
        if meme is not None:  # that meme, the ones similar to it, then the rest shuffled
            shown = self.visible(s)
            if meme not in shown:
                return None
            hidden = self._hidden(s)
            near = [i for i, _ in s.similar(meme) if i not in hidden]
            first = {meme, *near}
            rest = [i for i in shown if i not in first]
            rng.shuffle(rest)
            return [meme, *near, *rest]
        if album is not None:  # the 图集's own order, or shuffled
            ids = self._album_ids(s, album, "old" if order == "old" else "new")[1]
            if order == "shuffle":
                rng.shuffle(ids)
            return ids
        seen = self._read_seen()  # everything: the ones not seen for longest first
        return sorted(self.visible(s), key=lambda i: (seen.get(i, 0.0), rng.random()))

    def remove_memes(self, image_ids: list[str]) -> int:
        """Take memes out of the library. Collected ones move to rejected/; your own files are only hidden."""
        paths = self.library.paths()
        own = []
        for i in image_ids:
            p = paths.get(i)
            if p and Path(p).is_file() and self.review.in_inbox(p):
                dest = self.library.root / "rejected"
                dest.mkdir(parents=True, exist_ok=True)
                Path(p).replace(dest / Path(p).name)
            elif p:
                own.append(i)
        self.removed.add(own)
        known = [i for i in image_ids if i in paths]
        self.albums.forget(known)
        return len(known)

    def search(self, query: str, maybe_k: int = 12) -> dict:
        """Confident matches first; `maybe` holds a few more candidates for when nothing is certain."""
        s = self.searcher()
        hidden = self._hidden(s)
        matches, maybe = s.split_search(query, maybe_k=maybe_k + len(hidden))
        matches = [h for h in matches if h.id not in hidden]
        maybe = [h for h in maybe if h.id not in hidden][:maybe_k]
        return {"matches": [self._item(s, h.id, h.score, h.match) for h in matches],
                "maybe": [self._item(s, h.id, h.score, h.match) for h in maybe]}

    def review_list(self) -> dict:
        """Collected memes waiting for 要 / 不要, newest first, and how far training is."""
        s = self.searcher()
        pending = self.review.pending(s.paths, s.text)
        newest = sorted(pending, key=lambda i: -self._collected_at(i))
        return {"pending": [self._item(s, i) for i in newest], "progress": self.review.progress()}

    def _collected_at(self, image_id: str) -> float:
        found = self.sources().get(image_id)
        return found[-1].get("at", 0.0) if found else 0.0

    def decide(self, image_id: str, decision: str) -> str:
        return self.review.decide(image_id, decision, self.library.paths())

    def path(self, image_id: str) -> Path | None:
        """Only ids the library knows, and only if the file still exists: never a client-supplied path."""
        known = self.library.paths().get(image_id)
        return Path(known) if known and Path(known).is_file() else None

    def thumbnail(self, image_id: str, size: int = 384) -> Path | None:
        src = self.path(image_id)
        if src is None:
            return None
        out = self.library.root / "thumbs" / f"{image_id}-{size}.jpg"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            im = load_image(src)
            im.thumbnail((size, size))
            tmp = _tmp_for(out)
            im.save(tmp, "JPEG", quality=THUMB_QUALITY)
            try:
                tmp.replace(out)
            except OSError:  # another request wrote the same thumbnail first
                tmp.unlink(missing_ok=True)
                if not out.exists():
                    raise
        return out

    # ---------- seen: when each meme was last shown (旧梗重温, 刷梗) ----------

    def _read_seen(self) -> dict[str, float]:
        path = self.library.root / "seen.json"
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except json.JSONDecodeError:
            return {}  # only a display order; start over rather than fail every request

    def mark_seen(self, image_ids: list[str]) -> int:
        known = [i for i in image_ids if i in self.searcher().paths]
        with self._seen_lock:  # read-modify-write: two devices at once
            seen = self._read_seen()
            seen.update({i: self.clock() for i in known})
            _atomic_write_text(self.library.root / "seen.json", json.dumps(seen))
        return len(known)

    def rediscover(self, n: int = 12) -> list[dict]:
        s = self.searcher()
        with self._seen_lock:
            seen = self._read_seen()
            hidden = self._hidden(s)
            picked = pick_rediscover([i for i in s.ids if i not in hidden], seen, n, self.clock(), self.rng)
        self.mark_seen(picked)
        return [self._item(s, i) for i in picked]

    def status(self) -> dict:
        s = self.searcher()
        return {"images": len(self.visible(s)), "with_text": len(s.text), "vlm": bool(self.library.config()["vlm"]),
                "pending_review": len(self.review.pending(s.paths, s.text))}
