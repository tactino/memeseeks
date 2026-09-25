"""Multilingual text embeddings with BGE-M3 (dense vectors)."""

from __future__ import annotations

import numpy as np


class BgeM3:
    def __init__(self, model_id: str = "BAAI/bge-m3", device: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.model_id = model_id
        self.model = SentenceTransformer(model_id, device=device)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.model.get_sentence_embedding_dimension()), np.float32)
        vecs = self.model.encode(list(texts), batch_size=32, normalize_embeddings=True, convert_to_numpy=True)
        return vecs.astype(np.float32)
