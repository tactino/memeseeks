"""E1 step 2 (GPU box): score OCR / CLIP / VLM / hybrid retrieval against the user's queries."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from memeseeks.evalkit import load_qrels, quote_overlap, rrf, score_methods
from memeseeks.retrieval import rank_by_vectors

HYBRID_MIN_RECALL5 = 0.70
VLM_MIN_GAIN_POINTS = 15.0
QUOTE_THRESHOLD = 0.5  # a query sharing >= half its character bigrams with the image text counts as quoting it


def split_by_quote(queries, overlaps: dict[str, float], threshold: float = QUOTE_THRESHOLD):
    quote = [q for q in queries if overlaps[q.text] >= threshold]
    return quote, [q for q in queries if overlaps[q.text] < threshold]


def rank_all(q_bge, q_clip, ids, ocr_vecs, desc_vecs, clip_vecs, no_text) -> dict[str, list[str]]:
    ranked = {
        "ocr": rank_by_vectors(q_bge, ids, ocr_vecs, empty=no_text),
        "clip": rank_by_vectors(q_clip, ids, clip_vecs),
        "vlm": rank_by_vectors(q_bge, ids, desc_vecs),
    }
    ranked["hybrid_no_vlm"] = rrf([ranked["ocr"], ranked["clip"]])
    ranked["hybrid"] = rrf([ranked["ocr"], ranked["clip"], ranked["vlm"]])
    return ranked


def decisions(scores: dict[str, dict[str, float]]) -> dict:
    gain = round((scores["vlm"]["recall@5"] - scores["ocr"]["recall@5"]) * 100, 1)
    return {
        "hybrid_passes": scores["hybrid"]["recall@5"] >= HYBRID_MIN_RECALL5,
        "vlm_gain_points": gain,
        "ship_vlm_in_p1": gain >= VLM_MIN_GAIN_POINTS,
    }


def main(qrels_name: str, vlm_file: str = "vlm.jsonl") -> None:
    from memeseeks.index import load_index
    from memeseeks.models.clip import ChineseClip
    from memeseeks.models.ocr import OcrLine, ocr_text
    from memeseeks.models.textembed import BgeM3
    from memeseeks.models.vlm import description_text

    data, runs = Path(os.environ["MEMESEEKS_DATA"]), Path(os.environ["MEMESEEKS_RUNS"])
    idx = load_index(runs / "e1" / "index", vlm_file=vlm_file)
    ids = [i for i in idx.clip_ids if i in idx.ocr and i in idx.vlm]
    clip_vecs = idx.clip[[idx.clip_ids.index(i) for i in ids]]
    texts = {i: ocr_text([OcrLine(**l) for l in idx.ocr[i]]) if isinstance(idx.ocr[i], list) else "" for i in ids}
    no_text = {i for i, t in texts.items() if not t.strip()}
    qrels = load_qrels(data / qrels_name, [idx.relpath[i] for i in ids])
    if qrels.unknown_files:
        print("WARNING: files not found, those rows are not scored:", qrels.unknown_files)
    print(f"{len(qrels.queries)} labeled queries, {len(qrels.unlabeled)} unlabeled (not scored), "
          f"{len(ids)} images, {len(no_text)} with no OCR text")

    bge, clip = BgeM3(), ChineseClip()
    ocr_vecs = bge.embed([texts[i] or " " for i in ids])
    desc_vecs = bge.embed([description_text(idx.vlm[i]) or " " for i in ids])
    q_texts = [q.text for q in qrels.queries]
    q_bge, q_clip = bge.embed(q_texts), clip.embed_texts(q_texts)

    by_method: dict[str, dict[str, list[str]]] = {}
    for qi, q in enumerate(qrels.queries):
        ranked = rank_all(q_bge[qi], q_clip[qi], ids, ocr_vecs, desc_vecs, clip_vecs, no_text)
        for method, order in ranked.items():
            by_method.setdefault(method, {})[q.text] = [idx.relpath[i] for i in order]
    scores = score_methods(by_method, qrels.queries)
    id_of = {rel: i for i, rel in idx.relpath.items()}
    overlaps = {q.text: max(quote_overlap(q.text, texts.get(id_of.get(r, ""), "")) for r in q.relevant)
                for q in qrels.queries}
    quote_q, desc_q = split_by_quote(qrels.queries, overlaps)
    subsets = {name: {"n": len(qs), "scores": score_methods(by_method, qs)}
               for name, qs in (("quote_like", quote_q), ("descriptive", desc_q)) if qs}
    report = {"qrels": qrels_name, "vlm_file": vlm_file, "n_queries": len(qrels.queries), "n_images": len(ids),
              "n_no_text": len(no_text), "scores": scores, "decisions": decisions(scores), "subsets": subsets,
              "overlaps": overlaps,
              "top5": {m: {q: r[:5] for q, r in rk.items()} for m, rk in by_method.items()}}
    out = runs / "e1" / f"report-{Path(qrels_name).stem}-{Path(vlm_file).stem}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("| method | R@1 | R@5 | MRR |\n|---|---|---|---|")
    for m, s in scores.items():
        print(f"| {m} | {s['recall@1']:.2f} | {s['recall@5']:.2f} | {s['mrr']:.2f} |")
    print(json.dumps(report["decisions"], ensure_ascii=False))
    for name, sub in subsets.items():
        print(f"{name} (n={sub['n']}): " + ", ".join(f"{m} R@5 {v['recall@5']:.2f}" for m, v in sub["scores"].items()))
    print(f"full report (private): {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "queries.csv", sys.argv[2] if len(sys.argv) > 2 else "vlm.jsonl")
