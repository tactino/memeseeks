"""Sharing a 图集 as a file: <name>.memeseeks.zip holds its memes byte for byte and where they were collected from.
Whoever opens it in their own memeseeks gets the same 图集 in their library. There is no server: the file goes
however people send files (a chat, a drive, a USB stick).

Inside: album.json {"format": "memeseeks-album", "version": 1, "name", "items": [{"file": "images/<id>.<ext>",
"sources": [...]}]} and the images. A meme from your own folders carries no path, only its picture.
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from .albums import MAX_NAME, CollectionError
from .inbox import FORMATS, MAX_IMAGE_BYTES, InboxError, clean_meta, read_provenance

FORMAT, VERSION = "memeseeks-album", 1
MAX_PACKAGE_BYTES = 300 * 1024 * 1024
MAX_ITEMS = 2000
SITE = "图集分享"  # the source an imported meme is recorded with, next to where it was collected from
_ENTRY = re.compile(r"^images/[0-9a-f]{16}(" + "|".join(re.escape(e) for e in set(FORMATS.values())) + r")$")
_BUILT_IN = {"全部", "我喜欢"}


class ShareError(ValueError):
    pass


def export_album(service, cid: str) -> tuple[str, bytes]:
    """(the 图集's name, the file's bytes). Its memes in the 图集's own order, each with where it was collected."""
    s = service.searcher()
    name, ids = service._album_ids(s, cid, "old")
    sources = read_provenance(service.library.root)
    items, buf = [], io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:  # images are compressed already
        for i in ids:
            path = s.paths.get(i)
            ext = (path or "").rsplit(".", 1)[-1].lower()
            ext = ".jpg" if ext == "jpeg" else f".{ext}"
            if not path or ext not in FORMATS.values():
                continue
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            entry = f"images/{i}{ext}"
            zf.writestr(entry, data)
            seen, kept = set(), []
            for row in sources.get(i, []):
                meta = clean_meta(row)
                key = json.dumps(meta, sort_keys=True, ensure_ascii=False)
                if meta and meta.get("site") != SITE and key not in seen:
                    seen.add(key)
                    kept.append(meta)
            items.append({"file": entry, "sources": kept})
        zf.writestr("album.json", json.dumps({"format": FORMAT, "version": VERSION, "name": name, "items": items},
                                             ensure_ascii=False, indent=1))
    return name, buf.getvalue()


def _read_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(zf.read("album.json").decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShareError("这不是迷因捕手导出的图集文件") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ShareError("这不是迷因捕手导出的图集文件")
    if manifest.get("version") != VERSION:
        raise ShareError("这个图集文件来自更新的版本，请先更新迷因捕手")
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ShareError(f"图集文件坏了，或者超过 {MAX_ITEMS} 张")
    return manifest


def _free_name(service, name) -> str:
    """The shared 图集's name, or with （分享） after it when yours already has that name."""
    base = " ".join(str(name or "").split())[: MAX_NAME - 6] or "分享的图集"
    taken = {c["name"] for c in service.albums.all()} | _BUILT_IN
    if base not in taken:
        return base
    for n in range(1, 1000):
        candidate = f"{base}（分享）" if n == 1 else f"{base}（分享 {n}）"
        if candidate not in taken:
            return candidate
    raise ShareError("同名的图集太多了")


def import_album(service, inbox, data: bytes) -> dict:
    """Store the file's memes (ones you already have are not stored twice) and make them a 图集."""
    if len(data) > MAX_PACKAGE_BYTES:
        raise ShareError(f"图集文件超过 {MAX_PACKAGE_BYTES // (1024 * 1024)} MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ShareError("这不是迷因捕手导出的图集文件") from exc
    with zf:
        manifest = _read_manifest(zf)
        name = _free_name(service, manifest.get("name"))
        ids, added, duplicate, skipped = [], 0, 0, 0
        for item in manifest["items"]:
            entry = item.get("file") if isinstance(item, dict) else None
            try:
                info = zf.getinfo(entry) if isinstance(entry, str) and _ENTRY.match(entry) else None
            except KeyError:
                info = None
            if info is None or info.file_size > MAX_IMAGE_BYTES:
                skipped += 1
                continue
            with zf.open(info) as f:
                image = f.read(MAX_IMAGE_BYTES + 1)  # the declared size may lie
            try:
                found = inbox.receive(image)
            except InboxError:
                skipped += 1
                continue
            if found["status"] == "added":  # one you already had keeps its own story
                inbox.note_source(found["id"], {"site": SITE, "page_title": name})
                for source in item.get("sources") or []:
                    meta = clean_meta(source) if isinstance(source, dict) else {}
                    if meta and meta.get("site") != SITE:
                        inbox.note_source(found["id"], meta)
            ids.append(found["id"])
            added += found["status"] == "added"
            duplicate += found["status"] == "duplicate"
    if not ids:
        raise ShareError("图集文件里没有能用的图")
    try:
        album = service.albums.create(name)
    except CollectionError as exc:
        raise ShareError(str(exc)) from exc
    service.albums.add(album["id"], ids)
    service.review.mark_kept(ids)  # chosen by whoever shared them: no 待确认
    return {"album": {"id": album["id"], "name": name}, "added": added, "duplicate": duplicate, "skipped": skipped}

