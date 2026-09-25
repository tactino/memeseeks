"""Paint over text regions so image similarity compares the base picture, not the caption."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw


def mask_text(image: Image.Image, boxes: list[list[list[float]]], pad: int = 4) -> Image.Image:
    out = image.convert("RGB").copy()
    fill = tuple(int(v) for v in np.median(np.asarray(out).reshape(-1, 3), axis=0))
    draw = ImageDraw.Draw(out)
    for box in boxes:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        draw.rectangle([min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad], fill=fill)
    return out
