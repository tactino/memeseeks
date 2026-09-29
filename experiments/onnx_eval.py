"""The search models on PyTorch against their ONNX exports (tools/onnx/export_models.py), fp32 and 8-bit: search
quality on labeled queries, how close the vectors come, speed, memory and download size.

  python experiments/onnx_eval.py LIB ONNX_DIR QUERIES --images DIR [DIR ...] --work DIR [--threads 4]

LIB is a copy of a library folder: its index/ texts are read, never written. Images are found by file name in the
--images folders. Each variant re-embeds everything in a work folder of its own, in a process of its own so its
memory is measured alone. Prints numbers only (no queries, no meme text), and writes them to WORK/results.json.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

VARIANTS = {  # name: (text model, image model) folders under ONNX_DIR; None is the PyTorch wrapper
    "torch": (None, None),
    "onnx-fp32": ("bge-m3-fp32", "chinese-clip-l336-fp32"),
    "onnx-q8": ("bge-m3-q8", "chinese-clip-l336-q8"),
}  # the other rows of results/onnx.md came from earlier quantization recipes, described there
TORCH_MODELS = ("BAAI/bge-m3", "OFA-Sys/chinese-clip-vit-large-patch14-336px")


def rss_mb() -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return float("nan")


def load(variant: str, onnx_dir: Path, threads: int):
    text, image = VARIANTS[variant]
    if text is None:
        import torch

        torch.set_num_threads(threads)
        from memeseeks.models.clip import ChineseClip
        from memeseeks.models.textembed import BgeM3

        return BgeM3(device="cpu"), ChineseClip(device="cpu")
    from memeseeks.models.onnx import OnnxBge, OnnxClip

    return OnnxBge(onnx_dir / text, threads=threads), OnnxClip(onnx_dir / image, threads=threads)


def run_variant(variant: str, args) -> dict:
    """Runs in its own process: embed the library, score the queries, time it; vectors go to the work folder."""
    from memeseeks.images import load_image
    from memeseeks.index import build_text_vectors, load_index, load_text_vectors, route_texts
    from memeseeks.library import Library, Models
    from memeseeks.search import Searcher

    work = args.work / variant.replace(", ", "-").replace(" ", "-")
    shutil.rmtree(work, ignore_errors=True)
    (work / "index").mkdir(parents=True)
    src = args.lib / "index"
    for name in ("ocr.jsonl", "tidy.jsonl", "notes.jsonl", "relpaths.json"):
        if (src / name).exists():
            shutil.copy(src / name, work / "index" / name)
    relpath = json.loads((src / "relpaths.json").read_text(encoding="utf-8"))
    found = {p.name: p for d in args.images for p in Path(d).iterdir() if p.is_file()}
    paths = {i: str(found[Path(r).name]) for i, r in relpath.items() if Path(r).name in found}
    (work / "index" / "paths.json").write_text(json.dumps(paths, ensure_ascii=False), encoding="utf-8")
    (work / "library.json").write_text(json.dumps({"sources": [], "vlm": False}), encoding="utf-8")

    out = {"variant": variant, "images": len(paths), "missing_images": len(relpath) - len(paths)}
    base = rss_mb()
    t = time.perf_counter()
    bge, clip = load(variant, args.onnx, args.threads)
    out["load_s"], out["rss_after_load_mb"] = time.perf_counter() - t, rss_mb() - base

    idx = load_index(work / "index")
    t = time.perf_counter()
    build_text_vectors(idx, work / "index", bge, log=lambda *_: None)
    n_texts = len(route_texts(idx)["ocr"])
    out["text_ms_per_meme"] = (time.perf_counter() - t) * 1000 / max(n_texts, 1)

    ids = sorted(paths)
    t = time.perf_counter()
    vecs = np.concatenate([clip.embed_images([load_image(paths[i]) for i in ids[k:k + 16]])
                           for k in range(0, len(ids), 16)])
    out["image_ms_per_meme"] = (time.perf_counter() - t) * 1000 / len(ids)
    np.save(work / "index" / "clip.npy", vecs)
    (work / "index" / "clip_ids.json").write_text(json.dumps(ids), encoding="utf-8")

    searcher = Searcher(Library(work), Models(clip=clip, bge=bge))
    result = searcher.evaluate(args.queries)
    out["n_queries"], out["scores"], out["split"] = result["n_queries"], result["scores"], result["split"]

    queries = [row.split(",", 1)[0].strip() for row in args.queries.read_text(encoding="utf-8-sig").splitlines()[1:]
               if row.strip()]
    searcher.split_search(queries[0])  # warm
    q_text, q_image, q_search = [], [], []
    for q in queries:
        t = time.perf_counter(); bge.embed([q]); q_text.append(time.perf_counter() - t)
        t = time.perf_counter(); clip.embed_texts([q]); q_image.append(time.perf_counter() - t)
        t = time.perf_counter(); searcher.split_search(q); q_search.append(time.perf_counter() - t)
    out["query_ms"] = {"text model": 1000 * float(np.median(q_text)), "CLIP text": 1000 * float(np.median(q_image)),
                       "whole search": 1000 * float(np.median(q_search))}
    out["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    # for comparing variants: query vectors and what each search shows (kept in the work folder, not printed)
    np.save(work / "q_text.npy", bge.embed(queries))
    np.save(work / "q_clip.npy", clip.embed_texts(queries))
    shown = {q: {"top10": [h.id for h in searcher.search(q, k=10)],
                 "matches": sorted(h.id for h in searcher.split_search(q, maybe_k=0)[0])} for q in queries}
    (work / "shown.json").write_text(json.dumps(shown, ensure_ascii=False), encoding="utf-8")
    ids_text, _ = load_text_vectors(work / "index", "ocr")
    out["text_ids"] = len(ids_text)
    return out


def folder_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def torch_download_mb() -> float:
    """What the app downloads today: the files the two models' repos put in the Hugging Face cache."""
    from huggingface_hub import scan_cache_dir

    repos = {r.repo_id: r for r in scan_cache_dir().repos}
    total = 0
    for repo_id in TORCH_MODELS:
        files = {f.file_name: f.size_on_disk for rev in repos[repo_id].revisions for f in rev.files
                 if not f.file_path.as_posix().split("/snapshots/", 1)[1].split("/", 1)[1].startswith("onnx/")}
        if "model.safetensors" in files and "pytorch_model.bin" in files:
            files.pop("model.safetensors")  # transformers takes one of them, the .bin for these repos
        total += sum(files.values())
    return total / 1e6


def compare(work: Path, variant: str, baseline: str = "torch") -> dict:
    """How close a variant's vectors and results come to the baseline's, over the same memes and queries."""
    def folder(v):
        return work / v.replace(", ", "-").replace(" ", "-")

    a, b = folder(baseline), folder(variant)
    out = {}
    for name, rel in (("meme text", "index/text_ocr.npy"), ("image", "index/clip.npy"),
                      ("query, text model", "q_text.npy"), ("query, CLIP", "q_clip.npy")):
        x, y = np.load(a / rel), np.load(b / rel)
        if x.shape != y.shape:
            out[name] = None  # a different model (CLIP base): its vectors are not comparable
            continue
        cos = (x * y).sum(axis=1)
        out[name] = {"mean_cos": float(cos.mean()), "min_cos": float(cos.min())}
    sa, sb = (json.loads((f / "shown.json").read_text(encoding="utf-8")) for f in (a, b))
    out["top10_overlap"] = float(np.mean([len(set(sa[q]["top10"]) & set(sb[q]["top10"])) / 10 for q in sa]))
    out["same_matches"] = sum(sa[q]["matches"] == sb[q]["matches"] for q in sa)
    out["same_top1"] = sum(sa[q]["top10"][:1] == sb[q]["top10"][:1] for q in sa)
    return out


def tokenizer_check(onnx_dir: Path, texts: list[str]) -> dict:
    """Do the tokenizers-library tokenizers give the ids the transformers ones do?"""
    from tokenizers import BertWordPieceTokenizer, Tokenizer
    from transformers import AutoTokenizer, ChineseCLIPProcessor

    ours_bge = Tokenizer.from_file(str(onnx_dir / "bge-m3-q8" / "tokenizer.json"))
    ours_bge.enable_truncation(512)
    ref_bge = AutoTokenizer.from_pretrained(TORCH_MODELS[0])
    ours_clip = BertWordPieceTokenizer(str(onnx_dir / "chinese-clip-l336-q8" / "vocab.txt"), lowercase=True)
    ours_clip.enable_truncation(52)
    ref_clip = ChineseCLIPProcessor.from_pretrained(TORCH_MODELS[1]).tokenizer
    return {
        "texts": len(texts),
        "text model differs": sum(ours_bge.encode(t).ids != ref_bge(t, truncation=True, max_length=512)["input_ids"]
                                  for t in texts),
        "CLIP differs": sum(ours_clip.encode(t).ids != ref_clip(t, truncation=True, max_length=52)["input_ids"]
                            for t in texts),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("lib", type=Path)
    ap.add_argument("onnx", type=Path)
    ap.add_argument("queries", type=Path)
    ap.add_argument("--images", type=Path, nargs="+", required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--variant", help=argparse.SUPPRESS)  # set when run as one variant's process
    ap.add_argument("--only", nargs="*", choices=list(VARIANTS))
    ap.add_argument("--redo", action="store_true", help="run variants again even if they have results")
    args = ap.parse_args()
    if args.variant:
        print(json.dumps(run_variant(args.variant, args)))
        return

    args.work.mkdir(parents=True, exist_ok=True)
    results = {}
    for variant in args.only or list(VARIANTS):
        saved = args.work / variant.replace(", ", "-").replace(" ", "-") / "result.json"
        if saved.exists() and not args.redo:
            results[variant] = json.loads(saved.read_text(encoding="utf-8"))
            continue
        cmd = [sys.executable, __file__, str(args.lib), str(args.onnx), str(args.queries), "--work", str(args.work),
               "--threads", str(args.threads), "--variant", variant, "--images", *map(str, args.images)]
        done = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "TQDM_DISABLE": "1"})
        if done.returncode:
            sys.exit(f"{variant} failed:\n{done.stderr[-3000:]}")
        results[variant] = json.loads(done.stdout.strip().splitlines()[-1])
        saved.write_text(json.dumps(results[variant]), encoding="utf-8")
        print(variant, "done", flush=True)
    for variant, r in results.items():
        text, image = VARIANTS[variant]
        r["download_mb"] = torch_download_mb() if text is None else folder_mb(args.onnx / text) + folder_mb(args.onnx / image)
        if variant != "torch" and "torch" in results:
            r["vs_torch"] = compare(args.work, variant)

    from memeseeks.index import load_index, route_texts

    texts = list(route_texts(load_index(args.lib / "index"))["ocr"].values())
    texts += [row.split(",", 1)[0].strip() for row in args.queries.read_text(encoding="utf-8-sig").splitlines()[1:]
              if row.strip()]
    report = {"threads": args.threads, "variants": results, "tokenizers": tokenizer_check(args.onnx, texts)}
    (args.work / "results.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
