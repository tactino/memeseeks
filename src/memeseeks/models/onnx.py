"""The search models on ONNX Runtime, without PyTorch: the same BGE-M3 and Chinese-CLIP, exported and quantized
by tools/onnx/export_models.py.

A model folder holds model.onnx (or text.onnx and image.onnx for CLIP), the tokenizer (tokenizer.json, or vocab.txt
for CLIP's BERT) and memeseeks.json saying what was exported from what. The vectors match the PyTorch wrappers'
(textembed.py, clip.py) closely enough to search the same index; model_id includes how they were made, so an index
built with the other one is re-embedded rather than mixed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np


def _session(path: Path, threads: int | None = None):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads or int(os.environ.get("MEMESEEKS_THREADS", "0")) or 0
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _about(folder: Path) -> dict:
    return json.loads((folder / "memeseeks.json").read_text(encoding="utf-8"))


class OnnxBge:
    """BGE-M3 dense vectors: the first token's hidden state, normalized (as sentence-transformers does)."""

    def __init__(self, folder, max_length: int = 512, threads: int | None = None):
        from tokenizers import Tokenizer

        folder = Path(folder)
        about = _about(folder)
        self.model_id = f"{about['source']}@onnx-{about['precision']}"
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length)
        self.tokenizer.enable_padding(pad_id=about.get("pad_id", 1), pad_token=about.get("pad_token", "<pad>"))
        self.session = _session(folder / "model.onnx", threads)
        self.dim = about["dim"]

    def embed(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), np.float32)
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tokenizer.encode_batch(list(texts[i:i + batch_size]))
            ids = np.array([e.ids for e in enc], np.int64)
            mask = np.array([e.attention_mask for e in enc], np.int64)
            out.append(self.session.run(None, {"input_ids": ids, "attention_mask": mask})[0])
        return _normalize(np.concatenate(out))


MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)


class OnnxClip:
    """Chinese-CLIP image and text features, normalized. Images are resized to the model's square (no crop),
    as ChineseCLIPProcessor does; text is BERT-tokenized to at most 52 tokens."""

    def __init__(self, folder, threads: int | None = None):
        from tokenizers import BertWordPieceTokenizer

        folder = Path(folder)
        about = _about(folder)
        self.model_id = f"{about['source']}@onnx-{about['precision']}"
        self.size, self.dim = about["image_size"], about["dim"]
        self.tokenizer = BertWordPieceTokenizer.from_file(str(folder / "vocab.txt"), lowercase=True)
        self.tokenizer.enable_truncation(52)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self.text_session = _session(folder / "text.onnx", threads)
        self.image_session = _session(folder / "image.onnx", threads)

    def _pixels(self, image) -> np.ndarray:
        from PIL import Image

        im = image.convert("RGB").resize((self.size, self.size), Image.Resampling.BICUBIC)
        x = (np.asarray(im, np.float32) / 255.0 - MEAN) / STD
        return x.transpose(2, 0, 1)

    def embed_images(self, images, batch_size: int = 8) -> np.ndarray:
        if not len(images):
            return np.zeros((0, self.dim), np.float32)
        out = []
        for i in range(0, len(images), batch_size):
            batch = np.stack([self._pixels(im) for im in images[i:i + batch_size]])
            out.append(self.image_session.run(None, {"pixel_values": batch})[0])
        return _normalize(np.concatenate(out))

    def embed_texts(self, texts, batch_size: int = 64) -> np.ndarray:
        if not len(texts):
            return np.zeros((0, self.dim), np.float32)
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tokenizer.encode_batch(list(texts[i:i + batch_size]))
            feed = {"input_ids": np.array([e.ids for e in enc], np.int64),
                    "attention_mask": np.array([e.attention_mask for e in enc], np.int64),
                    "token_type_ids": np.zeros((len(enc), len(enc[0].ids)), np.int64)}
            out.append(self.text_session.run(None, feed)[0])
        return _normalize(np.concatenate(out))
