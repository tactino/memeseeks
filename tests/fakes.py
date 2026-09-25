"""Deterministic stand-ins for the model wrappers, driven by solid-colour test images."""

import numpy as np
from PIL import Image

from memeseeks.models.ocr import OcrLine


def solid(folder, name, rgb):
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), rgb).save(folder / name)
    return folder / name


def _unit(v):
    v = np.asarray(v, np.float32)
    return v / (np.linalg.norm(v) or 1.0)


class FakeOcr:
    """Red images read "猫猫", blue images "狗狗", anything else has no text."""

    def __call__(self, image):
        r, g, b = image.getpixel((0, 0))
        if r > 200 and g < 50:
            return [OcrLine("猫猫", [[0, 0], [1, 0], [1, 1], [0, 1]], 0.9)]
        if b > 200 and r < 50:
            return [OcrLine("狗狗", [[0, 0], [1, 0], [1, 1], [0, 1]], 0.9)]
        return []


class FakeClip:
    """Image vector = mean colour; text "红" points at red, "蓝" at blue, anything else at green."""

    def embed_images(self, images):
        return np.stack([_unit(np.asarray(im, np.float32).reshape(-1, 3).mean(0) + 1e-3) for im in images])

    def embed_texts(self, texts):
        return np.stack([_unit([1, 0, 0] if "红" in t else [0, 0, 1] if "蓝" in t else [0, 1, 0]) for t in texts])


class FakeBge:
    """Text vector = [mentions 猫, mentions 狗, small constant]."""

    def embed(self, texts):
        return np.stack([_unit([("猫" in t) * 1.0, ("狗" in t) * 1.0, 0.01]) for t in texts])
