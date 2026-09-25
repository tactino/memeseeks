"""Pure helpers for choosing E2 captions from ImgFlip575K entries."""

from __future__ import annotations

import csv
import io
import re

_ASCII_TEXT = re.compile(r"^[\x20-\x7E]+$")

TRANSCREATE_PROMPT = (
    "下面是一张英文梗图上的文字，多个文字框用 / 分隔。请把它改写成中文网络上会出现的译制版：意译，"
    "保留笑点和语气，可以用中文网络流行语，不要解释。只输出改写后的中文，多个文字框仍用 / 分隔。\n\n英文：{text}"
)


def caption_text(entry: dict) -> str:
    return " / ".join(b.strip() for b in entry["boxes"])


def _votes(entry: dict) -> int:
    return int(str(entry.get("metadata", {}).get("img-votes", "0")).replace(",", "") or 0)


def pick_captions(entries: list[dict], n: int = 3) -> list[dict]:
    good = []
    for e in entries:
        boxes = e.get("boxes") or []
        text = caption_text(e) if boxes else ""
        if (len(boxes) == 2 and all(b.strip() for b in boxes) and 10 <= len(text) <= 120
                and "http" not in text.lower() and _ASCII_TEXT.match(text)):
            good.append(e)
    return sorted(good, key=lambda e: (-_votes(e), e["url"]))[:n]


def read_popular(raw: bytes) -> list[dict]:
    """ImgFlip575K's popular_100_memes.csv is Windows-1252 (curly quotes as 0x92); accept UTF-8 too."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text)))
