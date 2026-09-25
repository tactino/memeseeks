"""Rank documents by cosine similarity (vectors are pre-normalized)."""

from __future__ import annotations

import numpy as np


def rank_by_vectors(query_vec: np.ndarray, ids: list[str], vecs: np.ndarray, empty=frozenset()) -> list[str]:
    """Highest similarity first; ids in `empty` (e.g. memes with no text) always rank last."""
    scores = vecs @ query_vec
    order = sorted(range(len(ids)), key=lambda i: (ids[i] in empty, -float(scores[i]), ids[i]))
    return [ids[i] for i in order]
