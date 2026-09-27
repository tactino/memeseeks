"""Matching a query's words as written: 考试 finds the meme that says 考试, however short the query.

The text vectors (BGE-M3) match by meaning, and a query of a word or two sits far from a long text in that space:
on the maintainer's collection 考试 and 生活 found no confident match, though memes plainly say them. This scores how
much of the query's wording a meme's text contains. Chinese is read a character at a time and other scripts a word
at a time, in pairs (生活 is not 生 and 活 apart), each pair weighted by how rare it is in the library; 繁体 counts as
简体, full-width as half-width, case is ignored.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict

# a run of latin letters and digits, or any other single letter (a Chinese character, a kana...)
_UNIT = re.compile(r"[a-z0-9]+|[^\W\d_a-z]")
_t2s = None


def units(text: str) -> list[str]:
    global _t2s
    if _t2s is None:
        from opencc import OpenCC

        _t2s = OpenCC("t2s")
    return _UNIT.findall(_t2s.convert(unicodedata.normalize("NFKC", text).lower()))


def _pairs(us: list[str]) -> set:
    return set(zip(us, us[1:]))


class LexicalIndex:
    def __init__(self, texts: dict[str, str]):
        grams = {}
        for i, text in texts.items():
            us = units(text)
            grams[i] = set(us) | _pairs(us)
        df = Counter(g for gs in grams.values() for g in gs)
        n = len(grams)
        self.idf = {g: math.log((n + 1) / (c + 0.5)) for g, c in df.items()}
        self.unseen = math.log((n + 1) / 0.5)  # a word no meme has: the query asks for something none of them says
        self.postings: dict[object, list[str]] = defaultdict(list)
        for i, gs in grams.items():
            for g in gs:
                self.postings[g].append(i)

    def scores(self, query: str) -> dict[str, float]:
        """The share of the query's wording (weighted by rarity) each meme's text contains: 1.0 is all of it."""
        us = units(query)
        wanted = {us[0]} if len(us) == 1 else _pairs(us)
        total = sum(self.idf.get(g, self.unseen) for g in wanted)
        if not total:
            return {}
        found: dict[str, float] = defaultdict(float)
        for g in wanted:
            for i in self.postings.get(g, ()):
                found[i] += self.idf[g]
        return {i: s / total for i, s in found.items()}
