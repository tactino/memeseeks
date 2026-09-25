from pathlib import Path

from experiments.e3_patterns.patterns import load_items, normalize_pattern, pair_labels


def test_normalize_unifies_slots_and_punctuation():
    assert normalize_pattern("{X}一时爽，一直{X}一直爽") == normalize_pattern("X 一时爽 一直 X 一直爽！")
    assert normalize_pattern("{X} is the new {Y}.") == normalize_pattern("[X] Is The New 【Y】")


def test_dataset_shape_and_pairs():
    items = load_items(Path("experiments/e3_patterns/snowclones.yaml"))
    groups = {g for _, g in items}
    assert len(items) == 60 and len(groups) == 20  # 10 snowclones + 10 distractor singletons
    pairs = pair_labels(items)
    assert len(pairs) == 60 * 59 // 2
    assert sum(1 for *_, same in pairs if same) == 10 * (5 * 4 // 2)


def test_heldout_threshold_uses_other_half_only():
    import pytest
    from experiments.e3_patterns.patterns import heldout_bal_acc
    # Halves by sorted parity: {a, c} and {b, d}. In {a, c} same-group pairs score 0.9 and cross pairs 0.7;
    # in {b, d} same-group 0.6, cross 0.1. Each half's best threshold is wrong for the other half, so an
    # honest held-out score is 0.5; a threshold picked on the test half would score 1.0.
    items = [("s", g) for g in "aabbccdd"]
    pairs = [(i, j, items[i][1] == items[j][1]) for i in range(8) for j in range(i + 1, 8)]

    def sim(i, j, same):
        gi, gj = items[i][1], items[j][1]
        if same:
            return 0.9 if gi in "ac" else 0.6
        return 0.7 if gi in "ac" and gj in "ac" else 0.1

    sims = [sim(i, j, same) for i, j, same in pairs]
    assert heldout_bal_acc(items, pairs, sims) == pytest.approx(0.5)


def test_fewshot_prompt_keeps_sentence_slot_and_has_no_test_snowclones():
    from experiments.e3_patterns.patterns import FEWSHOT_PROMPT, load_items
    assert "{s}" in FEWSHOT_PROMPT
    for sentence, _ in load_items(Path("experiments/e3_patterns/snowclones.yaml")):
        assert sentence not in FEWSHOT_PROMPT
