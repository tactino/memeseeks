# Matching the query's words as written (2026-09-27)

Search matched a meme's text only by meaning (BGE-M3 vectors, a confident match at cosine 0.57). A query of a word
or two sits far from a long text in that space, so a meme that plainly says the word could miss the bar: in the
demo library 考试 and 生活 found nothing confident, though a meme says each. `lexical.py` adds a route that scores
how much of the query's wording a meme's text contains (the rules' text, its name and the tidied text): Chinese a
character at a time and other scripts a word at a time, in pairs, each pair weighted by how rare it is in the
library; 繁体 counts as 简体. A meme with at least 0.8 of it is a confident match; one with at least 0.5 is ranked
on that route and fused with the others.

On the maintainer's collection (128 memes; aggregate numbers only):

| | 25 labeled queries: R@1 / R@5 / MRR | right among confident matches / wrong per query | 30 words taken from the memes (32 memes say one) |
|---|---|---|---|
| before | 0.96 / 1.00 / 0.968 | 96% / 0.92 | 8 of 32 found |
| with the route (0.8, 0.5) | 0.96 / 1.00 / 0.968 | 96% / 0.92 | 32 of 32 found, no other meme added |

The 30 words are 2-4 characters that 1 to 5 memes contain, drawn at random. Ranking on the route from 0.3 instead
of 0.5 cost one query its place in the top five (R@5 0.96); a bar of 0.7 or 1.0 for a match changed nothing else.
The route takes about 0.04 ms a query.
