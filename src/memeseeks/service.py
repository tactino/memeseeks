"""What the web server needs from a library: fresh searcher, safe file lookup, thumbnails, 旧梗重温."""

from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path

from .images import load_image
from .inbox import PROVENANCE_FILE, read_provenance
from .index import _atomic_write_text, _tmp_for
from .search import Searcher

THUMB_QUALITY = 82
# Everything a Searcher reads: if any of these changed, rebuild it (an add writes them over minutes).
_WATCHED = ["paths.json", "relpaths.json", "ocr.jsonl", "vlm.jsonl", "clip_ids.json", "clip.npy",
            "text_ocr.json", "text_vlm.json"]


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

    def _item(self, s: Searcher, i: str, score: float | None = None, match: float | None = None) -> dict:
        item = {"id": i, "score": score, "match": match, "text": s.text.get(i, ""), "relpath": s.relpath[i]}
        found = self.sources().get(i)
        if found:  # the first place it was collected from
            item["source"] = {k: found[0][k] for k in ("site", "page_url", "page_title") if k in found[0]}
        return item

    def search(self, query: str, maybe_k: int = 12) -> dict:
        """Confident matches first; `maybe` holds a few more candidates for when nothing is certain."""
        s = self.searcher()
        matches, maybe = s.split_search(query, maybe_k=maybe_k)
        return {"matches": [self._item(s, h.id, h.score, h.match) for h in matches],
                "maybe": [self._item(s, h.id, h.score, h.match) for h in maybe]}

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

    def rediscover(self, n: int = 12) -> list[dict]:
        s = self.searcher()
        seen_path = self.library.root / "seen.json"
        with self._seen_lock:  # read-modify-write: two devices opening the home page at once
            try:
                seen = json.loads(seen_path.read_text(encoding="utf-8")) if seen_path.exists() else {}
            except json.JSONDecodeError:
                seen = {}  # only a display order; start over rather than fail every request
            now = self.clock()
            picked = pick_rediscover(s.ids, seen, n, now, self.rng)
            seen.update({i: now for i in picked})
            _atomic_write_text(seen_path, json.dumps(seen))
        return [self._item(s, i) for i in picked]

    def status(self) -> dict:
        s = self.searcher()
        return {"images": len(s.ids), "with_text": len(s.text), "vlm": bool(self.library.config()["vlm"])}
