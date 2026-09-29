"""Which search models run, and where their files come from.

The default backend runs 8-bit ONNX copies of BGE-M3 and Chinese-CLIP (tools/onnx/export_models.py) on ONNX
Runtime; MEMESEEKS_BACKEND=torch runs the original models on PyTorch instead (the torch extra). The ONNX copies sit
in one Hugging Face repository, so hf-mirror.com serves them as well; MEMESEEKS_MODELS_DIR points at a folder that
already holds them (bge-m3-q8/, chinese-clip-l336-q8/) and nothing is downloaded.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = "tactino/memeseeks-models"
REVISION = "f3dd69557c900c45b035b180215a4f561979de6f"  # the upload experiments/results/onnx.md was checked on
FOLDERS = {"bge": "bge-m3-q8", "clip": "chinese-clip-l336-q8"}
ONNX_BYTES = 1_017_661_296  # both folders at REVISION
TORCH_BYTES = {"BAAI/bge-m3": 2_293_331_623, "OFA-Sys/chinese-clip-vit-large-patch14-336px": 1_626_539_027}


def backend() -> str:
    return "torch" if os.environ.get("MEMESEEKS_BACKEND", "").strip().lower() == "torch" else "onnx"


def repo() -> str:
    return os.environ.get("MEMESEEKS_MODEL_REPO") or REPO


def downloads() -> dict[str, int]:
    """The Hugging Face repositories the chosen models come from, and how many bytes each downloads."""
    if backend() == "torch":
        return dict(TORCH_BYTES)
    if os.environ.get("MEMESEEKS_MODELS_DIR"):
        return {}
    return {repo(): ONNX_BYTES}


def model_dir(name: str) -> Path:
    """The folder with one model's files, downloaded first if need be."""
    local = os.environ.get("MEMESEEKS_MODELS_DIR")
    if local:
        folder = Path(local) / FOLDERS[name]
        if not (folder / "memeseeks.json").exists():
            raise FileNotFoundError(f"{folder} holds no exported model (MEMESEEKS_MODELS_DIR)")
        return folder
    from huggingface_hub import snapshot_download

    root = snapshot_download(repo(), revision=REVISION, allow_patterns=[f"{FOLDERS[name]}/*"])
    return Path(root) / FOLDERS[name]


def make(name: str):
    """The text ("bge") or image ("clip") model of the chosen backend."""
    if backend() == "torch":
        if name == "clip":
            from .clip import ChineseClip
            return ChineseClip()
        from .textembed import BgeM3
        return BgeM3()
    from .onnx import OnnxBge, OnnxClip

    return OnnxClip(model_dir("clip")) if name == "clip" else OnnxBge(model_dir("bge"))
