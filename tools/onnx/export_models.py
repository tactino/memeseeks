"""Export the search models to ONNX, and quantize them to 8 bits, for memeseeks.models.onnx (no PyTorch needed there).

  python tools/onnx/export_models.py OUT_DIR [--threads 4] [--only NAME ...] [--quantize-only]

Needs torch, transformers, onnx and onnxruntime, and the models in the Hugging Face cache. Writes
OUT_DIR/{bge-m3,chinese-clip-l336,chinese-clip-b16}-{fp32,q8}/ with the tokenizer files and memeseeks.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import torch

MODELS = {
    "bge-m3": "BAAI/bge-m3",
    "chinese-clip-l336": "OFA-Sys/chinese-clip-vit-large-patch14-336px",
    "chinese-clip-b16": "OFA-Sys/chinese-clip-vit-base-patch16",
}


def _quantize(fp32: Path, q8: Path) -> None:
    """8-bit weights in blocks of 128 (MatMulNBits), multiplied in 8 bits block by block (accuracy_level 4), and the
    vocabulary table stored in 8 bits. Plain dynamic quantization (one 8-bit scale per activation tensor) cost the
    CLIP text tower too much: see experiments/results/onnx.md."""
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.matmul_nbits_quantizer import DefaultWeightOnlyQuantConfig, MatMulNBitsQuantizer

    config = DefaultWeightOnlyQuantConfig(block_size=128, is_symmetric=True, bits=8, accuracy_level=4,
                                          op_types_to_quantize=("MatMul",), quant_axes=(("MatMul", 0),))
    quantizer = MatMulNBitsQuantizer(onnx.load(str(fp32)), algo_config=config)
    quantizer.process()
    matmuls = q8.with_suffix(".matmul.onnx")
    quantizer.model.save_model_to_file(str(matmuls), use_external_data_format=False)
    quantize_dynamic(matmuls, q8, weight_type=QuantType.QInt8, op_types_to_quantize=["Gather"])  # a lookup: weights only
    matmuls.unlink()


def _write_about(folder: Path, about: dict) -> None:
    (folder / "memeseeks.json").write_text(json.dumps(about, indent=1), encoding="utf-8")


def derive_q8(fp32: Path, q8: Path) -> None:
    """The 8-bit copy of an exported fp32 folder: the same tokenizer files, each .onnx quantized."""
    q8.mkdir(parents=True, exist_ok=True)
    for f in fp32.iterdir():
        if f.name in ("tokenizer.json", "vocab.txt"):
            shutil.copy(f, q8 / f.name)
    for part in fp32.glob("*.onnx"):
        _quantize(part, q8 / part.name)
    about = json.loads((fp32 / "memeseeks.json").read_text(encoding="utf-8"))
    _write_about(q8, {**about, "precision": "q8"})


def export_bge(out: Path) -> None:
    from huggingface_hub import hf_hub_download
    from transformers import AutoModel

    source = MODELS["bge-m3"]
    model = AutoModel.from_pretrained(source).eval()

    class First(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask):
            return self.m(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0]

    fp32 = out / "bge-m3-fp32"
    fp32.mkdir(parents=True, exist_ok=True)
    shutil.copy(hf_hub_download(source, "tokenizer.json"), fp32 / "tokenizer.json")
    ids = torch.ones((2, 8), dtype=torch.long)
    torch.onnx.export(First(model), (ids, torch.ones_like(ids)), str(fp32 / "model.onnx"), dynamo=False,
                      input_names=["input_ids", "attention_mask"], output_names=["embedding"], opset_version=17,
                      dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                    "embedding": {0: "batch"}})
    _write_about(fp32, {"source": source, "precision": "fp32", "dim": model.config.hidden_size,
                        "pad_id": model.config.pad_token_id, "pad_token": "<pad>"})


def export_clip(name: str, out: Path) -> None:
    from huggingface_hub import hf_hub_download
    from transformers import ChineseCLIPModel

    source = MODELS[name]
    model = ChineseCLIPModel.from_pretrained(source).eval()
    size = model.config.vision_config.image_size

    class Image(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, pixel_values):
            return self.m.visual_projection(self.m.vision_model(pixel_values=pixel_values).pooler_output)

    class Text(torch.nn.Module):  # the projected first token, as clip.py does (not get_text_features)
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask, token_type_ids):
            hidden = self.m.text_model(input_ids=input_ids, attention_mask=attention_mask,
                                       token_type_ids=token_type_ids).last_hidden_state
            return self.m.text_projection(hidden[:, 0, :])

    fp32 = out / f"{name}-fp32"
    fp32.mkdir(parents=True, exist_ok=True)
    shutil.copy(hf_hub_download(source, "vocab.txt"), fp32 / "vocab.txt")
    pixels = torch.zeros((2, 3, size, size))
    torch.onnx.export(Image(model), (pixels,), str(fp32 / "image.onnx"), dynamo=False, opset_version=17,
                      input_names=["pixel_values"], output_names=["embedding"],
                      dynamic_axes={"pixel_values": {0: "batch"}, "embedding": {0: "batch"}})
    ids = torch.ones((2, 8), dtype=torch.long)
    torch.onnx.export(Text(model), (ids, torch.ones_like(ids), torch.zeros_like(ids)), str(fp32 / "text.onnx"),
                      dynamo=False, opset_version=17, input_names=["input_ids", "attention_mask", "token_type_ids"],
                      output_names=["embedding"],
                      dynamic_axes={k: {0: "batch", 1: "seq"} for k in ("input_ids", "attention_mask", "token_type_ids")}
                      | {"embedding": {0: "batch"}})
    _write_about(fp32, {"source": source, "precision": "fp32", "dim": model.config.projection_dim,
                        "image_size": size})


def main() -> None:
    ap = argparse.ArgumentParser(description="export the search models to ONNX")
    ap.add_argument("out", type=Path)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--only", nargs="*", choices=list(MODELS))
    ap.add_argument("--quantize-only", action="store_true", help="only redo the 8-bit copies of fp32 exports")
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    for name in args.only or list(MODELS):
        if not args.quantize_only:
            print("exporting", name, flush=True)
            export_bge(args.out) if name == "bge-m3" else export_clip(name, args.out)
        derive_q8(args.out / f"{name}-fp32", args.out / f"{name}-q8")
    for d in sorted(args.out.iterdir()):
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6
        print(f"{d.name}: {size:,.0f} MB")


if __name__ == "__main__":
    main()
