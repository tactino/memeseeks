"""待确认: collected images that may be 表情包 wait for the user's 要 / 不要 before they show up.

Only images collected from the browser (in the inbox, with a recorded source) are ever held back;
the user's own folders are theirs and never second-guessed. Until the user has made enough
decisions to train a personal classifier, the rule is the text amount: collected memes with fewer
than MIN_CHARS characters of text wait for review. 不要 moves the file to <library>/rejected (not a
source, so it leaves the library) and every decision is logged, to train that classifier later.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

from .inbox import read_provenance

MIN_CHARS = 15
LOG_FILE = "review.jsonl"
TRAIN_AFTER = 200         # decisions before a personal classifier can be trained
TRAIN_AFTER_REJECTS = 50  # of which 不要


class ReviewError(ValueError):
    pass


def text_chars(text: str) -> int:
    return len("".join(text.split()))


class Review:
    def __init__(self, library, clock=time.time):
        self.library, self.clock = library, clock
        self.inbox = library.root / "inbox"
        self.rejected = library.root / "rejected"
        self._lock = threading.Lock()
        self._cache, self._cache_stamp = {}, None
        self._sources, self._sources_stamp = {}, None

    # ---------- reading ----------

    def _stamp(self, name: str):
        try:
            return os.stat(self.library.root / name).st_mtime_ns
        except OSError:
            return None

    def decisions(self) -> dict[str, str]:
        """The latest decision per image id: "keep" or "reject"."""
        stamp = self._stamp(LOG_FILE)
        if stamp != self._cache_stamp:
            found = {}
            path = self.library.root / LOG_FILE
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                        found[row["id"]] = row["decision"]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
            self._cache, self._cache_stamp = found, stamp
        return self._cache

    def _collected(self) -> dict[str, list[dict]]:
        stamp = self._stamp("provenance.jsonl")
        if stamp != self._sources_stamp:
            self._sources, self._sources_stamp = read_provenance(self.library.root), stamp
        return self._sources

    def in_inbox(self, path: str | Path) -> bool:
        try:
            return Path(path).resolve().is_relative_to(self.inbox.resolve())
        except OSError:
            return False

    def state(self, image_id: str, path: str | Path, text: str) -> str:
        """"normal" (not held back), "pending", "kept" or "rejected"."""
        decided = self.decisions().get(image_id)
        if decided:
            return "kept" if decided == "keep" else "rejected"
        if image_id in self._collected() and self.in_inbox(path) and text_chars(text) < MIN_CHARS:
            return "pending"
        return "normal"

    def hidden(self, paths: dict[str, str], texts: dict[str, str]) -> set[str]:
        """Ids that must not appear in search or 旧梗重温: waiting for review, or rejected."""
        return {i for i, p in paths.items() if self.state(i, p, texts.get(i, "")) in ("pending", "rejected")}

    def pending(self, paths: dict[str, str], texts: dict[str, str]) -> list[str]:
        return [i for i, p in paths.items() if self.state(i, p, texts.get(i, "")) == "pending"]

    def progress(self) -> dict:
        values = list(self.decisions().values())
        rejects = values.count("reject")
        return {"decided": len(values), "rejected": rejects, "kept": len(values) - rejects,
                "train_after": TRAIN_AFTER, "train_after_rejects": TRAIN_AFTER_REJECTS,
                "can_train": len(values) >= TRAIN_AFTER and rejects >= TRAIN_AFTER_REJECTS}

    # ---------- deciding ----------

    def mark_kept(self, image_ids: list[str]) -> None:
        """Memes you chose yourself (uploads): never held back in 待确认."""
        with self._lock:
            with (self.library.root / LOG_FILE).open("a", encoding="utf-8") as f:
                for image_id in image_ids:
                    f.write(json.dumps({"id": image_id, "decision": "keep", "at": self.clock()}) + "\n")

    def decide(self, image_id: str, decision: str, paths: dict[str, str]) -> str:
        """Record 要 ("keep") or 不要 ("reject"); a reject can be undone by a later keep."""
        if decision not in ("keep", "reject"):
            raise ReviewError(f"unknown decision {decision!r}")
        with self._lock:
            current = paths.get(image_id)
            parked = next(iter(self.rejected.glob(f"{image_id}.*")), None) if self.rejected.exists() else None
            if decision == "reject":
                if not current or not self.in_inbox(current) or not Path(current).is_file():
                    raise ReviewError("only collected memes still in the inbox can be rejected")
                self.rejected.mkdir(parents=True, exist_ok=True)
                shutil.move(current, self.rejected / Path(current).name)
            elif parked is not None:  # undo a reject: back into the inbox
                self.inbox.mkdir(parents=True, exist_ok=True)
                shutil.move(str(parked), self.inbox / parked.name)
            elif not current:
                raise ReviewError("unknown meme")
            with (self.library.root / LOG_FILE).open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": image_id, "decision": decision, "at": self.clock()}) + "\n")
        return "kept" if decision == "keep" else "rejected"
