"""Check exported 8-bit models against the original PyTorch ones on a fixed set of texts and images.

  python tools/onnx/check_models.py OUT_DIR

OUT_DIR as written by export_models.py. Fails unless every vector keeps a cosine of at least MIN_COS with the
original's (the maintainer's collection measured 0.998 on average: experiments/results/onnx.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MIN_COS = 0.99
TEXTS = ["今天也是想辞职的一天", "我太难了", "打工人打工魂", "周一的早上", "猫猫震惊", "when the code works on the first try",
         "me pretending to understand the meeting", "一只猫坐在键盘上", "下雨天适合睡觉", "老板说今晚加班", "哈哈哈哈哈哈",
         "考研倒计时一百天", "这就是成年人的崩溃", "a dog wearing sunglasses", "どうしてこうなった", "电车难题"]


def images() -> list[Image.Image]:
    out = []
    font = ImageFont.load_default(size=40)
    for i, text in enumerate(["MONDAY COFFEE", "CAT ON KEYBOARD", "RAINY WEEKEND", "NO", "404"]):
        im = Image.new("RGB", (520 + 40 * i, 240), "white")
        ImageDraw.Draw(im).text((24, 90), text, fill="black", font=font)
        out.append(im)
    rng = np.random.default_rng(0)
    out += [Image.new("RGB", (300, 300), c) for c in ["red", "blue", "green", "yellow"]]
    out += [Image.fromarray(rng.integers(0, 255, (h, w, 3), dtype=np.uint8)) for h, w in [(336, 336), (200, 640), (900, 400)]]
    return out


def cos(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a * b).sum(axis=1)


def main() -> None:
    from memeseeks.models.clip import ChineseClip
    from memeseeks.models.onnx import OnnxBge, OnnxClip
    from memeseeks.models.textembed import BgeM3

    out = Path(sys.argv[1])
    pics = images()
    checks = {}
    ref, ours = BgeM3(device="cpu"), OnnxBge(out / "bge-m3-q8")
    checks["BGE-M3 texts"] = cos(ref.embed(TEXTS), ours.embed(TEXTS))
    del ref, ours
    ref, ours = ChineseClip(device="cpu"), OnnxClip(out / "chinese-clip-l336-q8")
    checks["Chinese-CLIP texts"] = cos(ref.embed_texts(TEXTS), ours.embed_texts(TEXTS))
    checks["Chinese-CLIP images"] = cos(ref.embed_images(pics), ours.embed_images(pics))
    failed = False
    for name, c in checks.items():
        print(f"{name}: mean cosine {c.mean():.4f}, lowest {c.min():.4f} ({len(c)})")
        failed |= bool(c.min() < MIN_COS)
    if failed:
        sys.exit(f"some vectors fell below {MIN_COS}")


if __name__ == "__main__":
    main()
