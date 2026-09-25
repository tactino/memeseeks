import pytest

from memeseeks.evalkit import (
    Query, auc, balanced_accuracy, load_qrels, mean_reciprocal_rank, recall_at_k, rrf, score_methods,
)


def test_load_qrels_handles_bom_fullwidth_semicolons_basenames_and_unknowns(tmp_path):
    csv_path = tmp_path / "queries.csv"
    csv_path.write_text(
        "搜索词,期望的图\n"
        "无语,sub/无语猫.jpg；doge.png\n"   # full-width semicolon, basename-only second file
        "阴阳怪气,不存在.jpg\n"             # unknown file -> unlabeled + reported
        "我太难了,\n"                       # blank -> unlabeled
        "只有一列\n"                        # no comma at all -> unlabeled
        "\n",
        encoding="utf-8-sig",
    )
    res = load_qrels(csv_path, ["sub/无语猫.jpg", "x/doge.png"])
    assert [(q.text, q.relevant) for q in res.queries] == [("无语", {"sub/无语猫.jpg", "x/doge.png"})]
    assert res.unlabeled == ["阴阳怪气", "我太难了", "只有一列"]
    assert res.unknown_files == {"阴阳怪气": ["不存在.jpg"]}


def test_ambiguous_basename_is_reported_not_guessed(tmp_path):
    csv_path = tmp_path / "q.csv"
    csv_path.write_text("q,f\n猫,cat.jpg\n", encoding="utf-8")
    res = load_qrels(csv_path, ["a/cat.jpg", "b/cat.jpg"])
    assert res.queries == [] and res.unknown_files == {"猫": ["cat.jpg"]}


def test_recall_mrr_and_score_methods():
    queries = [Query("a", {"x"}), Query("b", {"z"})]
    ranked = {"a": ["y", "x", "z"], "b": ["y", "w", "q", "r", "s", "z"]}
    assert recall_at_k(ranked, queries, 1) == 0.0
    assert recall_at_k(ranked, queries, 5) == 0.5
    assert mean_reciprocal_rank(ranked, queries) == pytest.approx((1 / 2 + 1 / 6) / 2)
    scores = score_methods({"m": ranked}, queries)
    assert scores["m"]["recall@5"] == 0.5


def test_recall_requires_labeled_queries():
    with pytest.raises(ValueError):
        recall_at_k({}, [], 5)


def test_rrf_rewards_agreement_and_breaks_ties_by_id():
    assert rrf([["a", "b", "c"], ["b", "a", "c"]])[:2] == ["a", "b"]
    assert rrf([["b", "a"], ["b", "c"]])[0] == "b"


def test_auc_and_balanced_accuracy():
    assert auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert auc([0.5], [0.5]) == 0.5
    assert balanced_accuracy([True, True, False, False], [True, False, False, False]) == pytest.approx(0.75)


def test_quote_overlap_measures_how_much_of_query_is_copied_text():
    from memeseeks.evalkit import quote_overlap
    # Invented strings only: never put the maintainer's real queries or meme text in the repo.
    assert quote_overlap("周一的咖啡比周五的更苦", "冷知识\n周一的咖啡比周五的更苦") == 1.0
    assert quote_overlap("鸽子开会", "今天的晚饭是番茄炒蛋") == 0.0
    assert quote_overlap("", "任何文字") == 0.0
    assert quote_overlap("Good Morning", "good morning sunshine") == 1.0


def test_rrf_scores_match_rrf_order():
    from memeseeks.evalkit import rrf, rrf_scores
    rankings = [["a", "b"], ["b", "c"]]
    s = rrf_scores(rankings)
    assert s["b"] == pytest.approx(1 / 62 + 1 / 61) and rrf(rankings) == sorted(s, key=lambda x: (-s[x], x))


def test_a_relpath_shared_by_two_images_is_ambiguous_not_merged(tmp_path):
    csv_path = tmp_path / "q.csv"
    csv_path.write_text("q,f\n猫,same.png\n狗,other.png\n", encoding="utf-8")
    res = load_qrels(csv_path, ["same.png", "same.png", "other.png"])
    assert [q.text for q in res.queries] == ["狗"] and res.unknown_files == {"猫": ["same.png"]}
