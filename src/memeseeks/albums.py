"""图集 (like playlists), 我喜欢, and the memes removed from the library. One JSON file each, in the library.

A 图集 holds image ids in the order they were added, never copies: a meme in five 图集 is stored once,
and deleting a 图集 never deletes a meme. 我喜欢 (id "liked") always exists and cannot be deleted.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path

from .index import _atomic_write_text

FILE = "collections.json"
REMOVED_FILE = "removed.json"
LIKED = "liked"
VERSION = 1
MAX_NAME = 40


class CollectionError(ValueError):
    pass


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectionError(f"{path.name} is damaged ({exc}); restore it from a backup or delete it") from exc


class Collections:
    def __init__(self, library_root, clock=time.time):
        self.path = Path(library_root) / FILE
        self.clock = clock
        self._lock = threading.Lock()

    # ---------- storage ----------

    def _load(self) -> dict:
        data = _read(self.path, {"version": VERSION, "collections": []})
        if not any(c["id"] == LIKED for c in data["collections"]):
            data["collections"].insert(0, {"id": LIKED, "name": "我喜欢", "created": 0, "items": []})
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(self.path, json.dumps(data, ensure_ascii=False, indent=1))

    def _find(self, data: dict, cid: str) -> dict:
        for c in data["collections"]:
            if c["id"] == cid:
                return c
        raise CollectionError("no such 图集")

    @staticmethod
    def _clean_name(name) -> str:
        name = " ".join(str(name or "").split())
        if not name:
            raise CollectionError("a 图集 needs a name")
        if len(name) > MAX_NAME:
            raise CollectionError(f"names are at most {MAX_NAME} characters")
        return name

    # ---------- reading ----------

    def all(self) -> list[dict]:
        return self._load()["collections"]

    def get(self, cid: str) -> dict:
        return self._find(self._load(), cid)

    def containing(self, image_id: str) -> list[str]:
        return [c["id"] for c in self.all() if any(it["id"] == image_id for it in c["items"])]

    # ---------- changing ----------

    def create(self, name) -> dict:
        name = self._clean_name(name)
        with self._lock:
            data = self._load()
            if any(c["name"] == name for c in data["collections"]):
                raise CollectionError(f"there is already a 图集 called {name}")
            c = {"id": secrets.token_hex(4), "name": name, "created": self.clock(), "items": []}
            data["collections"].append(c)
            self._save(data)
        return c

    def rename(self, cid: str, name) -> dict:
        name = self._clean_name(name)
        with self._lock:
            data = self._load()
            c = self._find(data, cid)
            if cid == LIKED:
                raise CollectionError("我喜欢 cannot be renamed")
            if any(o["name"] == name and o["id"] != cid for o in data["collections"]):
                raise CollectionError(f"there is already a 图集 called {name}")
            c["name"] = name
            self._save(data)
        return c

    def delete(self, cid: str) -> None:
        if cid == LIKED:
            raise CollectionError("我喜欢 cannot be deleted")
        with self._lock:
            data = self._load()
            data["collections"].remove(self._find(data, cid))
            self._save(data)

    def add(self, cid: str, image_ids: list[str]) -> int:
        """Append memes not in the 图集 yet; returns how many were added."""
        with self._lock:
            data = self._load()
            c = self._find(data, cid)
            have = {it["id"] for it in c["items"]}
            now = self.clock()
            new = [i for i in dict.fromkeys(image_ids) if i not in have]
            c["items"] += [{"id": i, "added": now} for i in new]
            self._save(data)
        return len(new)

    def remove(self, cid: str, image_ids: list[str]) -> int:
        drop = set(image_ids)
        with self._lock:
            data = self._load()
            c = self._find(data, cid)
            before = len(c["items"])
            c["items"] = [it for it in c["items"] if it["id"] not in drop]
            self._save(data)
        return before - len(c["items"])

    def forget(self, image_ids: list[str]) -> None:
        """A meme left the library: take it out of every 图集."""
        drop = set(image_ids)
        with self._lock:
            data = self._load()
            for c in data["collections"]:
                c["items"] = [it for it in c["items"] if it["id"] not in drop]
            self._save(data)


class Removed:
    """Memes removed from the library that live in your own folders: hidden, never deleted from disk."""

    def __init__(self, library_root):
        self.path = Path(library_root) / REMOVED_FILE
        self._lock = threading.Lock()

    def ids(self) -> set[str]:
        return set(_read(self.path, {"version": VERSION, "ids": []})["ids"])

    def add(self, image_ids: list[str]) -> None:
        with self._lock:
            ids = self.ids() | set(image_ids)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(self.path, json.dumps({"version": VERSION, "ids": sorted(ids)}))
