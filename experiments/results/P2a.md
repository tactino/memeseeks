# P2a verification (2026-09-25)

`memeseeks serve` over the CPU library from P1 (109 memes), Windows laptop, i7-1360P, torch 2.11.0+cpu.

## Speed

| Step | Before P2a | After P2a |
|---|---|---|
| OCR per image (10-image sample) | 3.78 s | 1.86 s (RapidOCR angle classifier off; identical text) |
| Server ready after start | — | 21 s (index + BGE-M3 + Chinese-CLIP loaded up front) |
| First search after ready | 64 s from start (models loaded lazily) | 0.20 s |
| Warm search (`/api/search`, k = 30) | ≈ 15 s per CLI call | 0.15 s |

Rejected on the way: Chinese-CLIP base-16 on CPU (0.20 vs 1.64 s/image) — CLIP route R@1 0.88 → 0.72 and
hybrid R@1 0.96 → 0.92 on the 25 labeled queries.

## Browser check (Playwright, Chromium)

- Home: 旧梗重温 shows 12 thumbnails, all load; 换一批 serves the least recently shown memes next.
- Search 「关于熬夜的」: 30 results; opening one shows the full image and its OCR text.
- 复制 on `http://127.0.0.1` (secure context): copies the image as PNG ("已复制"); 保存 links to `?download=1`; 分享 offered.
- 390 × 844 (phone): two-column masonry, page width 375 px inside the viewport, no horizontal overflow; viewer
  actions reachable at the bottom.
- No console errors; the page makes no external requests (checked by a test).
