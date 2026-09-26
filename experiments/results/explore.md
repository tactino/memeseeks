# What else Qwen3-VL-8B can read off a meme (2026-09-26)

Zero-shot, no training: the model answered one JSON prompt per image (type, the meme's name, a description, mood,
a translation, who speaks), and its answers were checked against what the images are known to be. 109 of the
maintainer's memes, 150 ChineseBQB stickers (10 per pack; used internally, never redistributed) and the 10
images the maintainer turned down in 待确认.

| field | result | used |
|---|---|---|
| 梗图 or 表情包 | memes: 108/109 called 梗图; stickers: 107/157 called 表情包, but only 5/10 of the maintainer's own rejects | no: it would let half of what the maintainer rejects into the library; 待确认 keeps its rule |
| the meme's name | named 3 memes (电车难题, Pop猫, 两只狼), all right; stays silent otherwise | yes: shown on the meme page, and searchable |
| translation | 2 English memes translated; the sense is right, puns are lost | yes, shown as 【译】 under the original |
| who speaks | mostly right (撒旦 / 我, 秦始皇 / 村民) | not yet: no use that is not filler |
| description, mood | specific and plausible | stored for later: the collection is almost all text, so their use for search cannot be measured yet |

About 1 s an image on one RTX 5090.

**On the whole collection** (128 memes, run through `memeseeks tidy-remote`): 5 names and 5 translations. Two
answers were not what they claim, and are now filtered: a kind of image given as a name (猫猫表情包: a name
ending in 表情包, 表情 or 梗图 is dropped), and a "translation" of a meme with no text at all (a translation is
shown only under text that is mostly not Chinese).

**Search with the names in it** (same 25 labeled queries as `tidy.md`): unchanged, R@1 0.96, R@5 1.00, 24/25
right among the confident matches, 0.92 wrong per query. Searching a name finds its meme first with or without
it; with it, 4 of 4 are confident matches instead of 3.
