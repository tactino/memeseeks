"""Text in the image via RapidOCR (ONNX runtime; CPU is fast enough)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class OcrLine:
    text: str
    box: list[list[float]]  # four corner points in pixel coordinates
    score: float


class RapidOcr:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def __call__(self, image: Image.Image) -> list[OcrLine]:
        bgr = np.ascontiguousarray(np.asarray(image.convert("RGB"))[:, :, ::-1])
        # The angle classifier costs half the OCR time and changes nothing on (upright) memes:
        # 10-image CPU check 3.78 -> 1.86 s/img, identical text (experiments/results/P1.md, P2a plan).
        result, _ = self._engine(bgr, use_cls=False)
        if not result:
            return []
        return [OcrLine(str(t), [[float(x), float(y)] for x, y in b], float(s)) for b, t, s in result]


def ocr_text(lines: list[OcrLine]) -> str:
    return " ".join(line.text for line in lines)
