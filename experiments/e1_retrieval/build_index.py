"""E1 step 1 (GPU box): OCR, VLM description and CLIP vector for every meme. Re-runnable."""

import os
from pathlib import Path

from memeseeks.images import scan_folder
from memeseeks.index import build_index
from memeseeks.models.clip import ChineseClip
from memeseeks.models.ocr import RapidOcr
from memeseeks.models.vlm import QwenVl

DATA = Path(os.environ["MEMESEEKS_DATA"])
RUNS = Path(os.environ["MEMESEEKS_RUNS"])

if __name__ == "__main__":
    scan = scan_folder(DATA / "my-memes")
    print(f"{len(scan.records)} images; unreadable={scan.unreadable}; "
          f"duplicates={sum(map(len, scan.duplicates.values()))}; skipped={len(scan.skipped)}")
    out = RUNS / "e1" / "index"
    build_index(scan.records, out, ocr=RapidOcr())
    build_index(scan.records, out, clip=ChineseClip())
    build_index(scan.records, out, vlm=QwenVl())
