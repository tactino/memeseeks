# The meme's own words (2026-09-26)

OCR reads everything printed on a meme: platform watermarks (小红书号：…), the account, time and counters of a
screenshotted post, share buttons, noise. `src/memeseeks/maintext.py` drops those lines (by pattern, and any line
found on 3+ memes of the library) and joins wrapped lines back into sentences. The search, 相似的梗 and the
meme page now use that text. Checked on the maintainer's collection (139 memes, 25 labeled queries; only
aggregate numbers here), with the same images and only the text changed:

| | raw OCR text | the meme's own words |
|---|---|---|
| hybrid R@1 / R@5 / MRR | 0.96 / 1.00 / 0.97 | 0.96 / 1.00 / 0.97 |
| confident matches: right meme shown | 24 / 25 (threshold 0.55) | 24 / 25 (threshold 0.57) |
| confident matches: wrong ones per query | 1.24 | 0.92 |
| 相似的梗 pairs between real memes | 4 | 2 |

- Rankings do not change. Scores rise a little on the cleaner text (watermarks diluted every vector), so the
  confident-match threshold moves from 0.55 to 0.57: the same recall with a quarter fewer wrong matches.
- The two 相似的梗 pairs that go away were different memes by the same account, similar only through its
  watermark (小红书号：…). No pair of real memes was added. (Five more pairs appear among test images made
  for the collector, which are the same template.)
- 83 of 128 memes with text changed. Left in: a channel name printed like a caption until it is on 3 memes,
  and OCR's own misreadings.
- 25 queries are few; the threshold should be checked again with more.
