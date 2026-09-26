# Tidying a meme's text with a vision-language model (2026-09-26)

The rules in `maintext.py` drop what is not the meme's own words, but they cannot put right what OCR misread, tell a
dialogue from a comment under it, or leave out an original next to its translation. `tidy.py` asks a
vision-language model to write the text out, then checks its answer. Run on the maintainer's collection (128
memes; only aggregate numbers here) on one RTX 5090.

**Models and prompts.** On 9 hand-checked memes (targets written from the pictures), Qwen2.5-VL-7B followed the
format poorly (every line bulleted, originals and watermarks kept) and once "corrected" a pun away (考阎 → 考砸).
Qwen3-VL-8B got about 6 of 9 right with the first prompt and the maintainer's example exactly right with the
second; later rewordings moved its answers on a quarter of the memes without doing better (fewer comments found,
an original kept again), so the second prompt stays, and what it misses is checked in code (`clean()`): a copy of
the prompt's example on a meme with no text, credits and times it let through (the rules of `maintext.py`), a
reply written twice, a line written twice. About 0.6 s a meme, 19 GB of video memory.

**What it gets right that rules cannot:** misread characters (那今地忘 → 那个地方, 很区 → 很凶), words OCR lost
(我的今天死了 → 我的鸚鵡今天死了), dialogues and comments (`- …`, `【评论】名字：…`), translations kept without
their originals. **Still wrong sometimes:** a sentence broken where the picture breaks the line, a description of
the picture instead of text, a comment not recognised as one.

**Search.** Same images, only the text for search changed (25 labeled queries):

| text used for search | R@1 / R@5 | confident matches (0.57): right / wrong per query |
|---|---|---|
| rules (`maintext.py`) | 0.96 / 1.00 | 24/25 / 0.92 |
| tidied (`tidy.py`) | 0.96 / 1.00 | 23/25 / 1.00 |

No threshold from 0.53 to 0.59 made the tidied text better for search (it drops originals and wording the
queries use). So the meme page shows the tidied text, and search and 相似的梗 keep the rules' text.
