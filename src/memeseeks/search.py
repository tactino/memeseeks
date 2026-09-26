"""Query a Library: per-route rankings fused with reciprocal rank fusion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .evalkit import load_qrels, rrf_scores, score_methods
from .index import load_index, load_text_vectors, route_texts
from .retrieval import rank_by_vectors


class EmptyLibrary(Exception):
    pass


# Text-route cosine (query vs the meme's OCR text or VLM description) needed to call a hit a match.
# Calibrated on the maintainer's 25 labeled queries. On the raw OCR text the right meme scored 0.76 on average
# (min 0.51) and the best wrong one 0.53, so 0.55 kept the right meme for 96% of queries. On the meme's own words
# (maintext.py: no watermarks or accounts, which diluted every vector) all scores rise a little: 0.57 keeps the
# same 96% with fewer wrong ones (0.92 per query instead of 1.24). The CLIP route barely separates right from
# wrong (0.36 vs 0.32), so it only orders results, never qualifies one.
MATCH_THRESHOLD = 0.57  # on the meme's own words (maintext.py); experiments/results/maintext.md

# 相似的梗: another meme counts as similar when its text vector is this close (cosine), or its image is.
# On the maintainer's 109 memes: 0.95 is the same meme twice, 0.73-0.74 are memes on the same theme
# ("a song from childhood comes on"), and around 0.70 unrelated memes that only share a layout or a
# watermark creep in. CLIP scores of different memes reach 0.88 easily; only the same template passes 0.93.
SIMILAR_TEXT = 0.72
SIMILAR_IMAGE = 0.93


@dataclass
class Hit:
    id: str
    path: str
    relpath: str
    score: float
    text: str
    match: float | None = None  # best text-route similarity, None when the meme has no text


def rank_route(query_vec, route_ids: list[str], route_vecs: np.ndarray, all_ids: list[str]) -> list[str]:
    """Ids with a vector on this route by similarity, then every other id (no text, failed step)."""
    ranked = rank_by_vectors(query_vec, route_ids, route_vecs) if route_ids else []
    seen = set(ranked)
    return ranked + [i for i in all_ids if i not in seen]


class Searcher:
    def __init__(self, library, models):
        self.library, self.models = library, models
        self.paths = library.paths()
        if not self.paths:
            raise EmptyLibrary("the library is empty: run `memeseeks add <folder>` first")
        idx = load_index(library.index_dir)
        self.ids = sorted(self.paths)
        current = set(self.ids)
        self.relpath = {i: idx.relpath.get(i, Path(self.paths[i]).name) for i in self.ids}
        self.text = {i: t for i, t in route_texts(idx)["ocr"].items() if i in current}
        keep = [k for k, i in enumerate(idx.clip_ids) if i in current]
        self.clip_ids = [idx.clip_ids[k] for k in keep]
        self.clip = idx.clip[keep] if keep else np.zeros((0, 0), np.float32)
        self.text_vecs: dict[str, tuple[list[str], np.ndarray]] = {}
        for route in ["ocr"] + (["vlm"] if library.config()["vlm"] else []):
            ids, vecs = load_text_vectors(library.index_dir, route)
            keep = [k for k, i in enumerate(ids) if i in current]
            if keep:
                self.text_vecs[route] = ([ids[k] for k in keep], vecs[keep])
        if not self.clip_ids and not self.text_vecs:
            raise EmptyLibrary("no images are indexed yet: run `memeseeks add <folder>` (it resumes where it stopped)")

    def _scored(self, query: str) -> tuple[dict[str, list[str]], dict[str, float]]:
        """Per-route rankings, plus each meme's best text-route similarity."""
        out, best_text = {}, {}
        if self.text_vecs:
            q = self.models.get("bge").embed([query])[0]
            for route, (ids, vecs) in self.text_vecs.items():
                out[route] = rank_route(q, ids, vecs, self.ids)
                for i, sim in zip(ids, (vecs @ q).tolist()):
                    best_text[i] = max(best_text.get(i, -1.0), sim)
        if self.clip_ids:
            q = self.models.get("clip").embed_texts([query])[0]
            out["clip"] = rank_route(q, self.clip_ids, self.clip, self.ids)
        return out, best_text

    def similar(self, image_id: str) -> list[tuple[str, float]]:
        """Memes like this one, best first: (id, score); score is on the text scale (see SIMILAR_TEXT)."""
        best: dict[str, float] = {}
        if "ocr" in self.text_vecs:
            ids, vecs = self.text_vecs["ocr"]
            if image_id in ids:
                for j, sim in zip(ids, (vecs @ vecs[ids.index(image_id)]).tolist()):
                    if sim >= SIMILAR_TEXT:
                        best[j] = max(best.get(j, -1.0), sim)
        if image_id in self.clip_ids:
            shift = SIMILAR_IMAGE - SIMILAR_TEXT  # put an image match on the same scale as a text match
            for j, sim in zip(self.clip_ids, (self.clip @ self.clip[self.clip_ids.index(image_id)]).tolist()):
                if sim >= SIMILAR_IMAGE:
                    best[j] = max(best.get(j, -1.0), sim - shift)
        best.pop(image_id, None)
        return sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))

    def rankings(self, query: str) -> dict[str, list[str]]:
        return self._scored(query)[0]

    def _fused(self, query: str) -> tuple[list[Hit], dict[str, float]]:
        rankings, best_text = self._scored(query)
        scores = rrf_scores(list(rankings.values()))
        order = sorted(scores, key=lambda i: (-scores[i], i))
        hits = [Hit(i, self.paths[i], self.relpath[i], scores[i], self.text.get(i, ""), best_text.get(i))
                for i in order]
        return hits, best_text

    def search(self, query: str, k: int = 10) -> list[Hit]:
        return self._fused(query)[0][:k]

    def split_search(self, query: str, maybe_k: int = 12) -> tuple[list[Hit], list[Hit]]:
        """Confident matches (text similarity >= MATCH_THRESHOLD), then a few best-ranked others."""
        hits, _ = self._fused(query)
        matches = [h for h in hits if h.match is not None and h.match >= MATCH_THRESHOLD]
        chosen = {h.id for h in matches}
        return matches, [h for h in hits if h.id not in chosen][:maybe_k]

    def evaluate(self, qrels_csv) -> dict:
        qrels = load_qrels(qrels_csv, self.relpath.values())
        by_method: dict[str, dict[str, list[str]]] = {}
        found, filler = 0, 0
        for q in qrels.queries:
            ranked = self.rankings(q.text)
            ranked["hybrid"] = [h.id for h in self.search(q.text, k=len(self.ids))]
            for method, ids in ranked.items():
                by_method.setdefault(method, {})[q.text] = [self.relpath[i] for i in ids]
            matches, _ = self.split_search(q.text, maybe_k=0)
            shown = {self.relpath[h.id] for h in matches}
            found += bool(shown & q.relevant)
            filler += len(shown - q.relevant)
        n = len(qrels.queries)
        split = {"match_recall": found / n, "filler_per_query": filler / n} if n else {}
        return {"n_queries": n, "unlabeled": qrels.unlabeled, "unknown_files": qrels.unknown_files,
                "scores": score_methods(by_method, qrels.queries) if qrels.queries else {}, "split": split}
