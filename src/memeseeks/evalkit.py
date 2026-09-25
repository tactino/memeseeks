"""Evaluation helpers shared by the P0 experiments: qrels, ranking metrics, fusion, AUC."""

from __future__ import annotations

import csv
from collections import Counter
import re
from dataclasses import dataclass, field
from pathlib import Path

_SPLIT = re.compile(r"[;；]")


@dataclass
class Query:
    text: str
    relevant: set[str] = field(default_factory=set)


@dataclass
class QrelsResult:
    queries: list[Query]
    unlabeled: list[str]
    unknown_files: dict[str, list[str]]


def load_qrels(csv_path: str | Path, known_relpaths) -> QrelsResult:
    """Rows are `query,file1;file2`. Files may be relpaths or unique basenames.

    Queries with no resolvable file are listed in `unlabeled` and never scored.
    """
    all_rel = list(known_relpaths)
    # A relpath shared by two images (e.g. two sources with IMG_0001.jpg) cannot say which one is meant.
    counts = Counter(all_rel)
    known = {rel for rel, n in counts.items() if n == 1}
    by_basename: dict[str, list[str]] = {}
    for rel in all_rel:
        by_basename.setdefault(rel.rsplit("/", 1)[-1], []).append(rel)
    queries, unlabeled, unknown = [], [], {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        text = row[0].strip()
        names = [n.strip().replace("\\", "/") for n in _SPLIT.split(row[1])] if len(row) > 1 else []
        relevant = set()
        for name in filter(None, names):
            if name in known:
                relevant.add(name)
            elif len(by_basename.get(name, [])) == 1:
                relevant.add(by_basename[name][0])
            else:
                unknown.setdefault(text, []).append(name)
        if relevant:
            queries.append(Query(text, relevant))
        else:
            unlabeled.append(text)
    return QrelsResult(queries, unlabeled, unknown)


def recall_at_k(ranked: dict[str, list[str]], queries: list[Query], k: int) -> float:
    if not queries:
        raise ValueError("no labeled queries to score")
    hits = sum(1 for q in queries if q.relevant & set(ranked[q.text][:k]))
    return hits / len(queries)


def mean_reciprocal_rank(ranked: dict[str, list[str]], queries: list[Query]) -> float:
    if not queries:
        raise ValueError("no labeled queries to score")
    total = 0.0
    for q in queries:
        for i, item in enumerate(ranked[q.text], 1):
            if item in q.relevant:
                total += 1.0 / i
                break
    return total / len(queries)


def score_methods(ranked_by_method, queries) -> dict[str, dict[str, float]]:
    return {
        name: {
            "recall@1": recall_at_k(ranked, queries, 1),
            "recall@5": recall_at_k(ranked, queries, 5),
            "mrr": mean_reciprocal_rank(ranked, queries),
        }
        for name, ranked in ranked_by_method.items()
    }


def rrf_scores(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for i, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + i)
    return scores


def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores = rrf_scores(rankings, k)
    return sorted(scores, key=lambda item: (-scores[item], item))


def auc(pos, neg) -> float:
    """Probability a random positive outscores a random negative; ties count half."""
    pos, neg = list(pos), list(neg)
    if not pos or not neg:
        raise ValueError("need at least one positive and one negative score")
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def balanced_accuracy(labels: list[bool], preds: list[bool]) -> float:
    tp = sum(1 for l, p in zip(labels, preds) if l and p)
    fn = sum(1 for l, p in zip(labels, preds) if l and not p)
    tn = sum(1 for l, p in zip(labels, preds) if not l and not p)
    fp = sum(1 for l, p in zip(labels, preds) if not l and p)
    if tp + fn == 0 or tn + fp == 0:
        raise ValueError("need both classes present")
    return (tp / (tp + fn) + tn / (tn + fp)) / 2


_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def quote_overlap(query: str, text: str) -> float:
    """Share of the query's character bigrams that also occur in `text` (1.0 = the query is copied text)."""
    q = _NON_WORD.sub("", query).lower()
    t = _NON_WORD.sub("", text).lower()
    if not q:
        return 0.0
    grams = [q[i:i + 2] for i in range(len(q) - 1)] or [q]
    return sum(1 for g in grams if g in t) / len(grams)
