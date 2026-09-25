"""The inbox: memes collected from the browser land here, with where they came from.

Images are stored byte for byte, so their id is the same one a folder scan gives them. A meme the
library already has is not stored twice; only its new source is recorded.
"""

from __future__ import annotations

import hashlib
import io
import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from .index import _atomic_write_text, _tmp_for

MAX_IMAGE_BYTES = 20 * 1024 * 1024
KEY_FILE = "inbox-key"
PROVENANCE_FILE = "provenance.jsonl"
# PIL format -> file extension; anything else is refused.
FORMATS = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp", "BMP": ".bmp"}
_TEXT_LIMITS = {"site": 40, "page_title": 200}
_URL_FIELDS = ("page_url", "image_url")
_URL_LIMIT = 2000


class InboxError(ValueError):
    pass


def persistent_secret(path: Path, nbytes: int = 24) -> str:
    """A random secret kept in `path`, created on first use."""
    try:
        found = path.read_text(encoding="utf-8").strip()
        if len(found) >= 32:
            return found
    except OSError:
        pass
    new = secrets.token_urlsafe(nbytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, new)
    return new


def clean_meta(meta: dict) -> dict:
    """Keep only the fields we show, trimmed; drop anything that is not an http(s) link."""
    out = {}
    for field, limit in _TEXT_LIMITS.items():
        value = meta.get(field)
        if isinstance(value, str) and value.strip():
            out[field] = " ".join(value.split())[:limit]
    for field in _URL_FIELDS:
        value = meta.get(field)
        if isinstance(value, str) and len(value) <= _URL_LIMIT and urlsplit(value).scheme in ("http", "https"):
            out[field] = value
    return out


class Inbox:
    def __init__(self, library, clock=time.time):
        self.library, self.clock = library, clock
        self.folder = library.root / "inbox"
        self._lock = threading.Lock()

    def key(self) -> str:
        return persistent_secret(self.library.root / KEY_FILE)

    def ensure_source(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.library.add_source(self.folder)

    def receive(self, data: bytes, meta: dict | None = None) -> dict:
        if len(data) > MAX_IMAGE_BYTES:
            raise InboxError(f"image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        try:
            with Image.open(io.BytesIO(data)) as im:
                fmt = im.format
                im.verify()
        except Exception as exc:
            raise InboxError("not an image") from exc
        if fmt not in FORMATS:
            raise InboxError(f"unsupported image type {fmt}")
        image_id = hashlib.sha256(data).hexdigest()[:16]
        with self._lock:
            self.ensure_source()
            existing = self.library.paths().get(image_id)
            target = self.folder / f"{image_id}{FORMATS[fmt]}"
            if (existing and Path(existing).is_file()) or target.exists():
                status = "duplicate"
            else:
                tmp = _tmp_for(target)
                tmp.write_bytes(data)
                tmp.replace(target)
                status = "added"
            source = clean_meta(meta or {})
            if source:
                with (self.library.root / PROVENANCE_FILE).open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": image_id, "at": self.clock(), **source}, ensure_ascii=False) + "\n")
        return {"id": image_id, "status": status}


def read_provenance(library_root: Path) -> dict[str, list[dict]]:
    """Every recorded source per image id, oldest first; a half-written last line is ignored."""
    found: dict[str, list[dict]] = {}
    path = Path(library_root) / PROVENANCE_FILE
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                found.setdefault(row.pop("id"), []).append(row)
            except (json.JSONDecodeError, KeyError, AttributeError):
                continue
    return found
