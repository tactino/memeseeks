from memeseeks import search
from memeseeks.lexical import LexicalIndex, units
from memeseeks.library import Library, Models
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def test_a_word_the_meme_says_is_all_of_the_query_however_long_the_text():
    lex = LexicalIndex({"exam": "你在考试时成功想起了那张ppt，但是你没有开记忆会员", "life": "如果生活给你泼了盆水"})
    assert lex.scores("考试") == {"exam": 1.0}
    assert lex.scores("生活") == {"life": 1.0}
    assert lex.scores("PPT") == {"exam": 1.0}  # case, and a latin word is one unit


def test_traditional_and_full_width_count_as_simplified_and_half_width():
    assert units("你知道嗎？ＰＯＰ貓") == ["你", "知", "道", "吗", "pop", "猫"]
    lex = LexicalIndex({"banana": "你知道嗎 人類和香蕉的基因"})
    assert lex.scores("你知道吗") == {"banana": 1.0}


def test_part_of_the_wording_scores_part_and_a_rare_pair_weighs_more_than_a_common_one():
    lex = LexicalIndex({"a": "上班的时候想下班", "b": "下班的时候想辞职", "c": "我的猫", "d": "我的狗"})
    both, half = lex.scores("想下班"), lex.scores("想辞职了")
    assert both["a"] == 1.0 and 0 < half["b"] < 1.0
    common = lex.scores("我的狗")  # 我的 is in two memes, 的狗 only in d: d wins, c gets the common part only
    assert common["d"] == 1.0 and common["c"] < 0.5
    assert lex.scores("？！") == {} and lex.scores("熊猫") == {}


def test_a_meme_that_says_the_word_is_a_confident_match_even_when_the_vectors_are_unsure(tmp_path, monkeypatch):
    src = tmp_path / "memes"
    solid(src, "red.png", (255, 0, 0)), solid(src, "blue.png", (0, 0, 255))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    monkeypatch.setattr(search, "MATCH_THRESHOLD", 2.0)  # no vector can qualify a meme now
    s = search.Searcher(lib, models)
    matches, maybe = s.split_search("猫猫")  # the red image reads 猫猫
    assert [h.relpath for h in matches] == ["red.png"] and matches[0].lex == 1.0
    assert "blue.png" in [h.relpath for h in maybe]
    assert s.split_search("熊猫")[0] == []  # only 猫 in common: not a match
