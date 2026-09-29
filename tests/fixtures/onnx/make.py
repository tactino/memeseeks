"""Make the tiny stand-ins for the exported search models that tests/test_models_onnx.py runs: the same inputs,
outputs, files and 8-bit recipe as tools/onnx/export_models.py, a few kilobytes each, random weights.

  python tests/fixtures/onnx/make.py   (needs torch, onnx, onnxruntime, tokenizers; run from the repo root)
"""

import json
import shutil
import sys
from pathlib import Path

import torch
from tokenizers import Regex, Tokenizer, models, pre_tokenizers, processors

sys.path.insert(0, "tools/onnx")
from export_models import derive_q8  # noqa: E402

HERE = Path(__file__).parent
CHARS = list("abcdefghijklmnopqrstuvwxyz0123456789 ") + list("猫狗今天好累一只汽车红色蓝的图片")
WIDTH, DIM, SIZE = 128, 16, 32  # hidden width (one 8-bit block), vector size, image side


class Tokens(torch.nn.Module):
    """First token plus the masked mean of all tokens, projected: padding must not change the result."""

    def __init__(self, vocab, dim, types=False):
        super().__init__()
        self.embed = torch.nn.Embedding(vocab, WIDTH)
        self.types = torch.nn.Embedding(2, WIDTH) if types else None
        self.hidden = torch.nn.Linear(WIDTH, WIDTH)
        self.out = torch.nn.Linear(WIDTH, dim)

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        h = self.embed(input_ids)
        if self.types is not None:
            h = h + self.types(token_type_ids)
        h = torch.relu(self.hidden(h))
        m = attention_mask.unsqueeze(-1).float()
        return self.out(h[:, 0] + (h * m).sum(1) / m.sum(1))


class Pixels(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.patch = torch.nn.Conv2d(3, WIDTH, 8, stride=8)
        self.out = torch.nn.Linear(WIDTH, DIM)

    def forward(self, pixel_values):
        return self.out(self.patch(pixel_values).flatten(2).mean(2))


def export(module, args, path, names, axes):
    torch.onnx.export(module.eval(), args, str(path), dynamo=False, opset_version=17, input_names=names,
                      output_names=["embedding"], dynamic_axes={**axes, "embedding": {0: "batch"}})


def main():
    torch.manual_seed(0)
    seq = {0: "batch", 1: "seq"}
    ids = torch.ones((2, 5), dtype=torch.long)

    bge = HERE / "bge-fp32"
    bge.mkdir(exist_ok=True)
    vocab = {"<s>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3} | {c: i + 4 for i, c in enumerate(CHARS)}
    tok = Tokenizer(models.WordLevel(vocab, unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.Split(Regex("."), behavior="isolated")
    tok.post_processor = processors.TemplateProcessing(single="<s> $A </s>", special_tokens=[("<s>", 0), ("</s>", 2)])
    tok.save(str(bge / "tokenizer.json"))
    export(Tokens(len(vocab), DIM), (ids, torch.ones_like(ids)), bge / "model.onnx",
           ["input_ids", "attention_mask"], {"input_ids": seq, "attention_mask": seq})
    (bge / "memeseeks.json").write_text(json.dumps({"source": "tiny/bge", "precision": "fp32", "dim": DIM,
                                                    "pad_id": 1, "pad_token": "<pad>"}))

    clip = HERE / "clip-fp32"
    clip.mkdir(exist_ok=True)
    words = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "cat", "red", "blue"] + [c for c in CHARS if c != " "]
    (clip / "vocab.txt").write_text("\n".join(words) + "\n", encoding="utf-8")
    export(Tokens(len(words), DIM, types=True), (ids, torch.ones_like(ids), torch.zeros_like(ids)), clip / "text.onnx",
           ["input_ids", "attention_mask", "token_type_ids"],
           {"input_ids": seq, "attention_mask": seq, "token_type_ids": seq})
    export(Pixels(), (torch.zeros((2, 3, SIZE, SIZE)),), clip / "image.onnx", ["pixel_values"],
           {"pixel_values": {0: "batch"}})
    (clip / "memeseeks.json").write_text(json.dumps({"source": "tiny/clip", "precision": "fp32", "dim": DIM,
                                                     "image_size": SIZE}))

    # named as models/store.py looks for them
    for src, dst in ((bge, "bge-m3-q8"), (clip, "chinese-clip-l336-q8")):
        shutil.rmtree(HERE / dst, ignore_errors=True)
        derive_q8(src, HERE / dst)
        shutil.rmtree(src)
    for f in sorted(HERE.rglob("*.*")):
        print(f.relative_to(HERE), f.stat().st_size)


if __name__ == "__main__":
    main()
