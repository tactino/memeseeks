"""Load images into one uniform form (upright RGB, first frame) and scan folders into records."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}


class UnreadableImage(Exception):
    pass


def load_image(path: str | Path) -> Image.Image:
    try:
        with Image.open(path) as im:
            im.seek(0)
            im.load()
            return _to_rgb(ImageOps.exif_transpose(im))
    except Exception as exc:
        raise UnreadableImage(f"{path}: {exc}") from exc


def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode == "RGB":
        return im.copy()
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return im.convert("RGB")


@dataclass(frozen=True)
class ImageRecord:
    id: str
    relpath: str
    path: Path


@dataclass
class ScanResult:
    records: list[ImageRecord] = field(default_factory=list)
    duplicates: dict[str, list[str]] = field(default_factory=dict)
    unreadable: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def scan_folder(root: str | Path) -> ScanResult:
    root = Path(root)
    result = ScanResult()
    first_seen: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if path.suffix.lower() not in IMAGE_EXTS:
            result.skipped.append(rel)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        if digest in first_seen:
            result.duplicates.setdefault(first_seen[digest], []).append(rel)
            continue
        try:
            load_image(path)
        except UnreadableImage:
            result.unreadable.append(rel)
            continue
        first_seen[digest] = rel
        result.records.append(ImageRecord(digest, rel, path))
    return result
