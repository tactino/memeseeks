import numpy as np

from experiments.e1_retrieval.evaluate import decisions, rank_all


def test_rank_all_methods_and_fusion():
    ids = ["a", "b"]
    eye = np.eye(2, dtype=np.float32)
    ranked = rank_all(eye[0], eye[0], ids, eye, eye[::-1], eye, no_text={"b"})
    assert ranked["ocr"] == ["a", "b"] and ranked["vlm"] == ["b", "a"] and ranked["clip"] == ["a", "b"]
    assert ranked["hybrid"][0] == "a" and set(ranked) == {"ocr", "clip", "vlm", "hybrid_no_vlm", "hybrid"}


def test_decisions_follow_spec_thresholds():
    d = decisions({"hybrid": {"recall@5": 0.72}, "vlm": {"recall@5": 0.60}, "ocr": {"recall@5": 0.50}})
    assert d == {"hybrid_passes": True, "vlm_gain_points": 10.0, "ship_vlm_in_p1": False}


def test_split_by_quote_threshold():
    from experiments.e1_retrieval.evaluate import split_by_quote
    from memeseeks.evalkit import Query
    qs = [Query("a", {"x"}), Query("b", {"y"}), Query("c", {"z"})]
    quote, desc = split_by_quote(qs, {"a": 0.9, "b": 0.5, "c": 0.1})
    assert [q.text for q in quote] == ["a", "b"] and [q.text for q in desc] == ["c"]
