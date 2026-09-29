from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("onnxruntime")
pytest.importorskip("tokenizers")

from memeseeks.models import store  # noqa: E402
from memeseeks.models.onnx import MEAN, STD, OnnxBge, OnnxClip  # noqa: E402

# tiny stand-ins with the real models' inputs, outputs, files and 8-bit operators (fixtures/onnx/make.py)
TINY = Path(__file__).parent / "fixtures" / "onnx"
TEXTS = ["今天好累", "a cat", "一只猫", "红色的汽车 and a very long line of text 1234567890", "x"]


def _unit(v):
    return np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-5)


def test_text_vectors_do_not_depend_on_the_batch_they_came_in():
    bge = OnnxBge(TINY / "bge-m3-q8")
    together = bge.embed(TEXTS, batch_size=16)  # padded to the longest
    alone = np.concatenate([bge.embed([t]) for t in TEXTS])
    assert together.shape == (5, 16) and together.dtype == np.float32 and _unit(together)
    assert np.allclose(together, alone, atol=1e-5)
    assert bge.embed([]).shape == (0, 16)
    assert bge.model_id == "tiny/bge@onnx-q8"


def test_clip_texts_and_images():
    clip = OnnxClip(TINY / "chinese-clip-l336-q8")
    together = clip.embed_texts(TEXTS)
    assert together.shape == (5, 16) and _unit(together)
    assert np.allclose(together, np.concatenate([clip.embed_texts([t]) for t in TEXTS]), atol=1e-5)
    images = [Image.new("RGB", (640, 200), "red"), Image.new("L", (40, 90), 128), Image.new("RGB", (32, 32), "blue")]
    vecs = clip.embed_images(images, batch_size=2)
    assert vecs.shape == (3, 16) and _unit(vecs)
    assert np.allclose(vecs[2], clip.embed_images(images[2:])[0], atol=1e-5)
    assert clip.embed_images([]).shape == (0, 16) and clip.embed_texts([]).shape == (0, 16)
    assert clip.model_id == "tiny/clip@onnx-q8"


def test_clip_pixels_are_resized_whole_and_normalized_like_the_processor():
    clip = OnnxClip(TINY / "chinese-clip-l336-q8")
    x = clip._pixels(Image.new("RGB", (300, 100), (255, 255, 255)))
    assert x.shape == (3, 32, 32)  # squashed to the square, not cropped
    assert np.allclose(x[:, 5, 5], (1 - MEAN) / STD)


def test_the_store_runs_onnx_models_from_a_local_folder(monkeypatch):
    monkeypatch.setenv("MEMESEEKS_BACKEND", "onnx")
    monkeypatch.setenv("MEMESEEKS_MODELS_DIR", str(TINY))
    assert store.backend() == "onnx"
    assert isinstance(store.make("bge"), OnnxBge) and isinstance(store.make("clip"), OnnxClip)
    monkeypatch.setenv("MEMESEEKS_MODELS_DIR", str(TINY / "nothing-here"))
    with pytest.raises(FileNotFoundError):
        store.model_dir("bge")


def test_backend_names(monkeypatch):
    for value, expected in (("torch", "torch"), (" Torch ", "torch"), ("onnx", "onnx"), ("ONNX", "onnx")):
        monkeypatch.setenv("MEMESEEKS_BACKEND", value)
        assert store.backend() == expected
