---
license: mit
language:
- zh
- en
- multilingual
library_name: onnx
pipeline_tag: feature-extraction
tags:
- onnx
- bge-m3
- chinese-clip
base_model:
- BAAI/bge-m3
- OFA-Sys/chinese-clip-vit-large-patch14-336px
---

# memeseeks models

8-bit ONNX copies of the two models that [迷因捕手 · memeseeks](https://github.com/tactino/memeseeks) searches with.
They run on ONNX Runtime without PyTorch, download a quarter as much as the originals (about 1.0 GB instead of
3.9 GB) and keep search results the same.

| Folder | Made from | Files | Output |
|---|---|---|---|
| `bge-m3-q8/` | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | `model.onnx`, `tokenizer.json` | the first token's last hidden state (1024); normalize it for BGE-M3's dense vector |
| `chinese-clip-l336-q8/` | [OFA-Sys/chinese-clip-vit-large-patch14-336px](https://huggingface.co/OFA-Sys/chinese-clip-vit-large-patch14-336px) | `text.onnx`, `image.onnx`, `vocab.txt` | projected text and image features (768); normalize them |

Inputs: `input_ids` and `attention_mask` (int64) for BGE-M3; the same plus `token_type_ids` (zeros) for the
Chinese-CLIP text model, at most 52 tokens; `pixel_values` for the image model: RGB resized to 336×336 (bicubic, no
crop), scaled to [0, 1] and normalized with mean (0.48145466, 0.4578275, 0.40821073) and std (0.26862954,
0.26130258, 0.27577711). `memeseeks.json` in each folder records the source and sizes.

## How they were made

[tools/onnx/export_models.py](https://github.com/tactino/memeseeks/blob/main/tools/onnx/export_models.py) exports
each model from its original weights to ONNX (opset 17), then stores the matrix-multiply weights in 8 bits with a
scale per block of 128 (MatMulNBits, 8-bit arithmetic block by block) and the vocabulary tables in 8 bits. Chinese-CLIP's
patch-embedding convolution stays float. The files here were built and checked by the repository's `models`
workflow, which compares every vector with the original model's.

On the maintainer's collection the vectors keep 0.998 cosine with the originals on average, and every search
measure is unchanged ([experiments/results/onnx.md](https://github.com/tactino/memeseeks/blob/main/experiments/results/onnx.md)).

## Licenses

Both models are MIT-licensed, and so are these copies.

- BGE-M3 by the Beijing Academy of Artificial Intelligence (BAAI), released under the MIT License. Chen et al., *BGE M3-Embedding:
  Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation*, 2024.
- Chinese-CLIP: Copyright (c) 2022-2023 OFA-Sys Team; Copyright (c) 2012-2022 Gabriel Ilharco, Mitchell Wortsman,
  Nicholas Carlini, Rohan Taori, Achal Dave, Vaishaal Shankar, John Miller, Hongseok Namkoong, Hannaneh Hajishirzi,
  Ali Farhadi, Ludwig Schmidt. MIT License ([github.com/OFA-Sys/Chinese-CLIP](https://github.com/OFA-Sys/Chinese-CLIP)).
  Yang et al., *Chinese CLIP: Contrastive Vision-Language Pretraining in Chinese*, 2022.

The MIT License: Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction, including without
limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of
the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
