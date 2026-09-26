"""A meme's own words among everything OCR read on it (docs/design.md, "Meme text").

OCR reads every piece of text in the image: platform watermarks (小红书号：…), the account and the time of a
screenshotted post (@handle, Follow, 4:25 AM, 6小时), counters (1/9, 1,537), share buttons, and noise. Each line
is dropped when it looks like one of those, or when the same line is on 3 or more memes in the library (a
watermark nobody listed); what is left is joined back into sentences where OCR had split a wrapped line.

The size of the text does not decide anything: a title is sometimes half the size of a sign in the photo.
"""

from __future__ import annotations

import re
from collections import Counter

COMMON_IN = 3  # a line on this many memes is a watermark
_CJK = re.compile(r"[㐀-鿿豈-﫿]")
_LETTER = re.compile(r"[A-Za-z]")
_ENDS = "。！？!?…；;"

_PLATFORMS = {"小红书", "红书", "抖音", "快手", "微博", "知乎", "bilibili", "哔哩哔哩", "b站", "微信", "豆瓣", "贴吧",
              "tiktok", "instagram", "twitter", "weibo", "xiaohongshu"}
_ACCOUNT_ID = re.compile(r"(书号|红号|抖音号|快手号|微信号|微博号|视频号|b站号|uid)\s*[:：]?|(微博|微信|b站|id|小红书|红书|抖音|快手|哔哩哔哩)\s*[:：]", re.I)
_ACCOUNT = re.compile(r"@\S|[\w.+-]+@[\w-]+\.\w+|https?://|www\.|\b[\w-]+\.(?:com|org|net|cn|io|me)\b", re.I)
_CHROME = re.compile(r"^(follow|following|关注|已关注|\+关注|跟隨|跟随|translate ?tweet|翻译推文|查看翻译|share|分享|转发|评论|点赞|"
                     r"收藏|回复|显示回复|查看回复|查看动态>?|热门|简介|帖子|貼文|更多|reply|retweet|repost|like|likes|"
                     r"sign this petition|展开|收起|全文|resolved question|report ?it|reportlt|best ?answer.*|replying to.*)$|"
                     r"\s(follow|关注)$", re.I)
# 20,108 notes / 99Retweets181Likes / 59萬次查看
_COUNTS = re.compile(r"\d[\d,.]*\s*(?:[万萬千kKwW])?\s*(?:notes?|retweets?|likes?|views?|comments?|replies|次查看|次播放|次观看|人看过)", re.I)
# credits for whoever translated or reposted it: 翻/製：… / 译@…
_CREDIT = re.compile(r"^(翻译|翻譯|翻/製|翻/制|翻制|翻製|译|譯|搬运|搬運|转载|轉載|来源|出处|via|cr|credit)\s*[:：@]|^[:：]\s*\S{1,8}$|^(photo|photos|odai|art|illustration|drawn|video|image|source)\s+by\b", re.I)
_MONTH = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?[\s\d,]*", re.I)
# what OCR makes of 小红书 when it misreads it: 小红节, 小红书具, 红书
_XHS = re.compile(r"^小?红.?书.?$|^小红.$")
_TIME = re.compile(r"\d{1,2}:\d{2}|\d{3,4}\s*[ap]m|\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{2,4}|\d+\s*(?:秒|分钟|小时|小時|天|周|個月|个月|年)前?|"
                   r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d|\d{1,4}[/-]\d{1,2}[/-]\d{2,4}|"
                   r"\d+\s*(?:seconds?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\s*ago", re.I)
_COUNTER = re.compile(r"[\d\s,.，。万萬千kKwW+↑↓/·•|:：\-]*")


def norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).lower()


def common_lines(ocr_rows, at_least: int = COMMON_IN) -> set[str]:
    """Lines (normalized) found on `at_least` memes or more: watermarks. Single characters (我, 有) are
    ordinary words in many memes, so they never count."""
    seen = Counter()
    for lines in ocr_rows:
        seen.update({n for n in (norm(line.text) for line in lines) if len(n) >= 2})
    return {n for n, count in seen.items() if count >= at_least}


def is_noise(text: str, score: float, common: "set[str] | frozenset[str]" = frozenset()) -> bool:
    t, n = text.strip(), norm(text)
    cjk, letters = len(_CJK.findall(t)), len(_LETTER.findall(t))
    if not n or n in common or n in _PLATFORMS or _XHS.match(n):
        return True
    if len(n) <= 2 and letters and cjk:             # 品o: two strokes of noise, not a word
        return True
    if _COUNTER.fullmatch(t):                      # 1/9, 109, ↓54, 1,537
        return True
    if _ACCOUNT_ID.search(t) or _ACCOUNT.search(t) or _CHROME.search(t) or _CREDIT.search(t) or _MONTH.fullmatch(t):
        return True
    if (_TIME.search(t) or _COUNTS.search(t)) and len(_CJK.findall(_COUNTS.sub("", _TIME.sub("", t)))) <= 4:
        return True                                  # 4:25AM·Oct13,2020 / 16小时前江苏 (not 7:59醒来关掉了闹钟)
    if cjk == 0 and (letters <= 2 or score < 0.65):  # share buttons (f, in), OCR noise
        return True
    return cjk > 0 and score < 0.5


# where a line is; a line without a box (an older index, a test) has none, so nothing is joined to it
def _height(line) -> float:
    return _bottom(line) - _top(line)


def _top(line) -> float:
    return min((p[1] for p in line.box), default=0.0)


def _bottom(line) -> float:
    return max((p[1] for p in line.box), default=0.0)


def main_lines(lines, common: "set[str] | frozenset[str]" = frozenset()) -> list:
    """The lines worth reading, in OCR's order."""
    def near(a, b) -> bool:  # b right below a, or on the same row
        return _top(b) - _bottom(a) < max(_height(a), _height(b))

    drop = set()
    for k, line in enumerate(lines):
        t = line.text.strip()
        handle, chrome = t.startswith("@"), bool(_ACCOUNT.search(t) or _CHROME.search(t))
        if k and (handle or chrome) and near(lines[k - 1], line):
            # the line just above is the account's display name: any Latin one; a Chinese one only above an
            # @handle, short and ending no sentence (the line below is often the post itself: that one stays)
            name = lines[k - 1].text.strip()
            if not _CJK.search(name) and len(name) <= 40 or handle and len(name) <= 12 and name[-1:] not in _ENDS + "，,：:":
                drop.add(k - 1)
        if _ACCOUNT_ID.search(t):
            # what is left of a misread platform mark sits right next to its account line: 书, 小幼, 0793
            for j in (k - 1, k + 1):
                if 0 <= j < len(lines) and len(norm(lines[j].text)) <= 3 and near(*sorted((lines[j], line), key=_top)):
                    drop.add(j)
    return [line for k, line in enumerate(lines) if k not in drop and not is_noise(line.text, line.score, common)]


def _left(line) -> float:
    return min((p[0] for p in line.box), default=0.0)


def _right(line) -> float:
    return max((p[0] for p in line.box), default=0.0)


class _Row:
    """One line of the image: OCR sometimes cuts it into pieces side by side."""

    def __init__(self, line):
        self.text, self.left, self.right = line.text.strip(), _left(line), _right(line)
        self.top, self.bottom = _top(line), _bottom(line)

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def em(self) -> float:  # the size of one character: steadier than the box's height
        cjk = len(_CJK.findall(self.text))
        return (self.right - self.left) / max(1.0, cjk + 0.55 * (len(self.text) - cjk))

    def same_row(self, line) -> bool:  # beside it, level with it, and the same size of type
        h1, h2 = self.height, _height(line)
        overlap = min(self.bottom, _bottom(line)) - max(self.top, _top(line))
        return (overlap >= 0.5 * min(h1, h2) and min(h1, h2) >= 0.6 * max(h1, h2)
                and _left(line) >= self.right - 0.5 * h1)

    def add(self, line) -> None:
        text = line.text.strip()
        apart = _left(line) - self.right > 0.5 * self.height  # labels side by side, not one line cut in two
        self.text += (" " if apart else _glue(self.text, text)) + text
        self.left, self.right = min(self.left, _left(line)), max(self.right, _right(line))
        self.top, self.bottom = min(self.top, _top(line)), max(self.bottom, _bottom(line))


def _glue(a: str, b: str) -> str:
    cjk_a = bool(_CJK.match(a[-1:])) or (a[-1:] and not a[-1:].isascii())
    return "" if cjk_a and _CJK.match(b[:1]) else " "  # 中文 joins as is; anything with Latin keeps a space


def _continues(prev: _Row, row: _Row) -> bool:
    """Whether `row` is the rest of a sentence OCR split at a line break: right below `prev`, the same size of
    type, lined up with it, and `prev` full (a line only wraps once it reaches the edge) and not ending a
    sentence."""
    h = max(prev.height, row.height)
    close = 0 <= row.top - prev.bottom < 1.0 * h
    same = min(prev.em, row.em) >= 0.8 * max(prev.em, row.em)
    centre = lambda r: (r.left + r.right) / 2
    aligned = abs(row.left - prev.left) < 1.5 * h or abs(centre(row) - centre(prev)) < 1.5 * h
    full = prev.right - prev.left >= 0.8 * (row.right - row.left)
    return close and same and aligned and full and prev.text[-1:] not in _ENDS


def _rows(lines, kept) -> list:
    """The image's lines, pieces side by side joined; None where a dropped line was."""
    rows, current = [], None
    for k, line in enumerate(lines):
        if kept is not None and not kept[k]:
            rows += [current, None] if current else [None]
            current = None
        elif current is not None and current.same_row(line):
            current.add(line)
        else:
            if current:
                rows.append(current)
            current = _Row(line)
    return rows + ([current] if current else [])


def join_lines(lines, kept=None) -> str:
    """Lines back into sentences; `kept[k]` says whether line k was kept (nothing is joined across a line that
    was dropped)."""
    out: list[str] = []
    prev = None
    for row in _rows(lines, kept):
        if row is not None and prev is not None and _continues(prev, row):
            out[-1] += _glue(out[-1], row.text) + row.text
        elif row is not None:
            out.append(row.text)
        prev = row
    return "\n".join(out)


def main_text(lines, common: "set[str] | frozenset[str]" = frozenset()) -> str:
    keep = set(map(id, main_lines(lines, common)))
    return join_lines(lines, [id(line) in keep for line in lines])
