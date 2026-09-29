# The search models without PyTorch (2026-09-28)

The Windows installer is about 200 MB, most of it PyTorch, and the first run downloads 3.9 GB of models. Both are
there only to run BGE-M3 and Chinese-CLIP (ViT-L/14, 336 px). `tools/onnx/export_models.py` exports the two to ONNX
(BGE-M3: the first token's hidden state; Chinese-CLIP: the projected image pooler output and the projected first
text token, as `clip.py` computes them) and `models/onnx.py` runs them on ONNX Runtime with the `tokenizers`
library and Pillow/NumPy preprocessing.

On the maintainer's collection (128 memes, 25 labeled queries; aggregate numbers only), 4 threads on the GPU box's
CPU, each variant in a process of its own (`experiments/onnx_eval.py`):

| | R@1 / R@5 / MRR | CLIP route alone | right among confident matches / wrong per query | same confident matches as PyTorch | query vector cos, text model / CLIP | download MB | peak memory MB | ms per image indexed | ms per search |
|---|---|---|---|---|---|---|---|---|---|
| PyTorch (today) | 0.96 / 1.00 / 0.968 | 0.88 / 0.92 / 0.910 | 96% / 0.92 | | | 3,920 | 4,577 | 1,190 | 58 |
| ONNX fp32 | 0.96 / 1.00 / 0.968 | 0.88 / 0.92 / 0.910 | 96% / 0.92 | 25 of 25 | 1.0000 / 1.0000 | 3,911 | 4,751 | 730 | 50 |
| dynamic int8 | 0.92 / 0.96 / 0.942 | 0.64 / 0.80 / 0.718 | 96% / 0.80 | 20 of 25 | 0.982 / 0.861 | 997 | 2,267 | 294 | 21 |
| dynamic int8, CLIP ViT-B/16 | 0.88 / 0.96 / 0.927 | 0.60 / 0.88 / 0.731 | 96% / 0.80 | 20 of 25 | 0.982 / – | 777 | 1,524 | 33 | 21 |
| 8-bit weights, float math | 0.96 / 1.00 / 0.968 | 0.88 / 0.88 / 0.897 | 96% / 0.92 | 25 of 25 | 0.9997 / 0.9997 | 1,018 | 2,409 | 763 | 127 |
| **8-bit weights, 8-bit math in blocks (q8)** | 0.96 / 1.00 / 0.968 | 0.88 / 0.92 / 0.904 | 96% / 0.88 | 24 of 25 | 0.998 / 0.999 | 1,018 | 2,473 | 644 | 28 |

The fp32 export reproduces PyTorch exactly (cosine 1.0000 for every meme, image and query; identical results), and
the `tokenizers` tokenizers give the same ids as the transformers ones on all 153 texts and queries.

Plain dynamic quantization (8-bit weights, and each activation tensor rounded to 8 bits with one scale) is fast but
hurts Chinese-CLIP's text tower: query vectors keep only 0.86 cosine with the original and the CLIP route's R@1
falls from 0.88 to 0.64. Per-channel weight scales lift that to 0.98 (image vectors 0.95), still short. Transformer
activations have outliers that one scale per tensor cannot hold.

Storing the weights in 8 bits with a scale per block of 128 (ONNX Runtime's MatMulNBits) keeps the activations
float: vectors within 0.9997 of the original. Letting ONNX Runtime multiply in 8 bits block by block (accuracy
level 4) costs a little of that (0.998) and gives back the speed. That one (q8) keeps every search number: the same
top result for all 25 queries, the same confident matches for 24 (the 25th shows one wrong meme fewer). Against
today's app it downloads a quarter as much (about 1.0 GB), peaks at about half the memory, indexes an image in half
the time and answers a search in half the time. The vocabulary tables (BGE-M3's is 1 GB in fp32) are stored in 8
bits too; a lookup does no arithmetic on them. 4-bit weights (block 32) would save another 300 MB but drop to 0.97
cosine on BGE-M3 and 0.98 on CLIP.

Chinese-CLIP's patch embedding is a convolution; ONNX Runtime has no 8-bit CPU kernel for it, so it stays float.
The q8 files run unchanged on ONNX Runtime 1.23 (Linux) and 1.30 (Windows).
