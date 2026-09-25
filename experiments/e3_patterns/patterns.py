"""Pure helpers for E3: dataset loading, pair labels, pattern normalization."""

from __future__ import annotations

import re
from itertools import combinations
from pathlib import Path

import yaml

CANON_PROMPT = (
    "下面这句话可能套用了某个流行句式（snowclone）：句子里有固定不变的骨架，也有可以随意替换的部分。"
    "请把可替换的部分换成 {X}、{Y}、{Z}（按出现顺序），保留固定骨架，输出这个句式。"
    "如果这句话没有套用任何流行句式，就原样输出这句话。只输出结果，不要解释。\n\n句子：{s}"
)

_SLOT = re.compile(r"[\{\[【［]\s*[XYZxyz]\s*[\}\]】］]|(?<![A-Za-z])[XYZ](?![A-Za-z])")
_NOISE = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_pattern(p: str) -> str:
    return "{S}".join(_NOISE.sub("", part).lower() for part in _SLOT.split(p))


def load_items(path: Path) -> list[tuple[str, str]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items = [(s, group) for group, variants in data["snowclones"].items() for s in variants]
    items += [(s, f"d{i}") for i, s in enumerate(data["distractors"])]
    return items


def pair_labels(items: list[tuple[str, str]]) -> list[tuple[int, int, bool]]:
    return [(i, j, items[i][1] == items[j][1]) for i, j in combinations(range(len(items)), 2)]


# Fallback named in the spec (§7 E3): few-shot examples. None of these snowclones is in the test set.
FEWSHOT_PROMPT = (
    "判断一句话是否套用了流行句式（snowclone）。如果是，只把可替换的部分换成 {X}、{Y}（按出现顺序），"
    "固定骨架一字不改；如果不是流行句式，就原样输出。只输出结果。\n\n"
    "例子：\n"
    "句子：学习使我快乐 → {X}使我快乐\n"
    "句子：外卖界的爱马仕 → {X}界的{Y}\n"
    "句子：Winter is coming → {X} is coming\n"
    "句子：Say hello to my little friend → Say hello to my little friend\n"
    "句子：今天天气很好，适合出去走走 → 今天天气很好，适合出去走走\n"
    "句子：我们的口号是加班 → 我们的口号是{X}\n\n"
    "句子：{s} →"
)


def _best_threshold(labels, sims) -> float:
    from memeseeks.evalkit import balanced_accuracy

    return max((t / 100 for t in range(50, 100)),
               key=lambda t: balanced_accuracy(labels, [s >= t for s in sims]))


def heldout_bal_acc(items, pairs, sims) -> float:
    """Pick the threshold on one half of the groups, score on the other half, average both ways."""
    from memeseeks.evalkit import balanced_accuracy

    groups = sorted({g for _, g in items})
    halves = [set(groups[0::2]), set(groups[1::2])]
    scores = []
    for train, test in (halves, halves[::-1]):
        def subset(side):
            idx = [k for k, (i, j, _) in enumerate(pairs) if items[i][1] in side and items[j][1] in side]
            return [pairs[k][2] for k in idx], [sims[k] for k in idx]
        t = _best_threshold(*subset(train))
        labels, s = subset(test)
        scores.append(balanced_accuracy(labels, [x >= t for x in s]))
    return sum(scores) / len(scores)
