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


@dataclass
class Hit:
    id: str
    path: str
    relpath: str
    score: float
    text: str


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

    def rankings(self, query: str) -> dict[str, list[str]]:
        out = {}
        if self.text_vecs:
            q = self.models.get("bge").embed([query])[0]
            for route, (ids, vecs) in self.text_vecs.items():
                out[route] = rank_route(q, ids, vecs, self.ids)
        if self.clip_ids:
            q = self.models.get("clip").embed_texts([query])[0]
            out["clip"] = rank_route(q, self.clip_ids, self.clip, self.ids)
        return out

    def search(self, query: str, k: int = 10) -> list[Hit]:
        scores = rrf_scores(list(self.rankings(query).values()))
        order = sorted(scores, key=lambda i: (-scores[i], i))[:k]
        return [Hit(i, self.paths[i], self.relpath[i], scores[i], self.text.get(i, "")) for i in order]

    def evaluate(self, qrels_csv) -> dict:
        qrels = load_qrels(qrels_csv, self.relpath.values())
        by_method: dict[str, dict[str, list[str]]] = {}
        for q in qrels.queries:
            ranked = self.rankings(q.text)
            ranked["hybrid"] = [h.id for h in self.search(q.text, k=len(self.ids))]
            for method, ids in ranked.items():
                by_method.setdefault(method, {})[q.text] = [self.relpath[i] for i in ids]
        return {"n_queries": len(qrels.queries), "unlabeled": qrels.unlabeled, "unknown_files": qrels.unknown_files,
                "scores": score_methods(by_method, qrels.queries) if qrels.queries else {}}
