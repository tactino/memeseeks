"""E2 step 1: fetch 20 templates' captions and instance images, write Chinese transcreations."""

import json
import os
import urllib.request
from pathlib import Path

from experiments.e2_crosslingual.pairs import TRANSCREATE_PROMPT, caption_text, pick_captions, read_popular

RAW = "https://raw.githubusercontent.com/schesa/ImgFlip575K_Dataset/master/dataset"
API = "https://api.github.com/repos/schesa/ImgFlip575K_Dataset/contents/dataset/memes"
OUT = Path(os.environ["MEMESEEKS_RUNS"]) / "e2"
N_TEMPLATES = 20


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "memeseeks-p0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


if __name__ == "__main__":
    from memeseeks.models.vlm import QwenVl

    (OUT / "images").mkdir(parents=True, exist_ok=True)
    available = {item["name"] for item in json.loads(fetch(API))}
    popular = read_popular(fetch(f"{RAW}/popular_100_memes.csv"))
    chosen = []
    for row in popular:
        fname = row["Name"].replace(" ", "-") + ".json"
        if fname in available:
            caps = pick_captions(json.loads(fetch(f"{RAW}/memes/{fname}")), n=3)
            if len(caps) == 3:
                chosen.append((row["Name"], caps))
        if len(chosen) == N_TEMPLATES:
            break
    vlm = QwenVl()
    rows = []
    for t, (name, caps) in enumerate(chosen):
        for c, entry in enumerate(caps[:2]):
            path = OUT / "images" / f"t{t:02d}_c{c}.jpg"
            path.write_bytes(fetch(entry["url"]))
        rows.append({
            "template": name,
            "captions": [caption_text(e) for e in caps],
            "zh": vlm.chat(TRANSCREATE_PROMPT.format(text=caption_text(caps[0])), max_new_tokens=200),
            "images": [f"t{t:02d}_c0.jpg", f"t{t:02d}_c1.jpg"],
        })
        print(name, "->", rows[-1]["zh"])
    (OUT / "pairs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(rows)} templates written to {OUT / 'pairs.json'}")
