import numpy as np

from memeseeks.retrieval import rank_by_vectors


def test_rank_by_cosine():
    vecs = np.array([[1, 0], [0, 1], [0.7, 0.7]], np.float32)
    assert rank_by_vectors(np.array([1, 0], np.float32), ["a", "b", "c"], vecs) == ["a", "c", "b"]


def test_empty_docs_rank_last():
    vecs = np.array([[1, 0], [0.1, 0.9]], np.float32)
    ranked = rank_by_vectors(np.array([1, 0], np.float32), ["no_text", "has_text"], vecs, empty={"no_text"})
    assert ranked == ["has_text", "no_text"]
