# Design

How 迷因捕手 looks and moves. When changing the UI, change this file first, then the code. Values live in
`src/memeseeks/web/tokens.css`; components use the tokens, never raw values.

## Character

A meme lover's treasury: a text search engine for memes and a pleasant place to read them, like a
wallpaper site for memes. It is a personal meme collection, the way a music app is a personal music
collection: memes are gathered into named collections (图集, like playlists) and can be browsed full
screen one after another (刷梗, like listening). It runs on your own computer; nothing is shared with
other people (a public, social side is out of scope for now).

## Scope: clean feature groups, no filler

Every feature and button must answer "why would someone press this?". If it cannot, it is not built.
Options that only restate a default, or exist so a screen looks full, are left out.

| group | what it does |
|---|---|
| 找 search | describe a meme in words; confident matches first, a folded 可能相关; optional web results in their own section |
| 收 collect | the browser collector (采集 meme), uploading from the web app (drag and drop, or the phone's photo picker), watched folders, 待确认 for collected images that may be stickers |
| 藏 keep | 全部, 我喜欢 and your own 图集: create, rename, delete, add and remove memes; remove a meme from the library |
| 看 view | the meme page (text, source, the 图集 it is in, 喜欢 / 加入图集 / 复制 / 保存 / 分享, 相似的梗), 刷梗 full screen, 旧梗重温 on the home page |
| 设置 settings | appearance, motion, web search, source folders, connecting the browser |

相似梗 has no entry of its own: it is a row on the meme page (shown only when something is really
similar) and it is what 刷梗 continues with when started from a meme.

## Pages and navigation

- **首页**: the search box, 今日一梗, your 图集 (covers, 我喜欢 first), 旧梗重温.
- **搜索结果**, **图集** (also 全部 and 我喜欢: name, count, 刷梗 from here, sort 最新 / 最早, rename, delete),
  **梗图** (the meme page), **刷梗** (full screen, over any page), **待确认**, **设置**.
- Header: the logo (home), the search box, 图集, 刷梗, 待确认 (only when something waits, with its count),
  设置. Phones: the search box on top and a bottom bar of 首页 / 图集 / 刷梗 / 设置.

刷梗 order: from a 图集 (or 全部, 我喜欢; its 刷梗 button) its own order, or shuffled (顺序 / 随机 inside
刷梗); from a meme (tap its picture), the memes similar to it, then the rest shuffled; from the header, the
memes not seen for longest. Swipe up and down, the wheel, arrow keys or ↑ ↓; Esc or × closes. 喜欢, 加入图集
and 详情 are one tap away. A 图集 remembers where you stopped (in this browser; a shuffle keeps its order),
and starts over once you reached the end. 刷梗 is always dark, whatever the theme.

On the home page, which has its own big logo and search box, the header keeps only its links.

## Data

Everything is in the library folder, as small JSON files written atomically, each with a `version`:

| file | holds |
|---|---|
| `index/`, `library.json` | images (id = the first 16 hex digits of the file's SHA-256), text, vectors; source folders |
| `provenance.jsonl`, `review.jsonl` | where collected memes came from; 待确认 decisions |
| `collections.json` | the 图集: id, name, created, items (image id and when added) in order; `liked` (我喜欢) always exists |
| `removed.json` | memes removed from the library. Files in your own folders are never deleted; they are only hidden. Collected ones are moved to `rejected/`. |
| `settings.json` | the settings below, shared by every device that opens this library |
| `seen.json` | when each meme was last shown (旧梗重温, 刷梗 order) |

A 图集 holds image ids, not copies: a meme in five 图集 is stored once. Deleting a 图集 never deletes memes.

## Settings

Kept to what changes the experience; each has a sensible default.

| setting | options (default first) |
|---|---|
| 主题 | 纸色 / 夜间 |
| 蒙德里安边框 | 开 / 关 |
| 开场动画 | 开 / 关 (it plays once per visit, not on every page, and never when opening straight into 刷梗) |
| 动效 | 完整 / 减少: no cat animations, no slides (the system's reduce-motion setting always wins) |
| 网上搜索 | 开 / 关 (shown only when the server was started with a web source, which is itself off by default) |
| 来源文件夹 | the watched folders: add (a path on the computer running the server), remove; the collector's inbox stays |
| 连接浏览器 | install the collector (the steps live here, not on the home page) |

Uploading is on 全部 and every 图集 page (a 上传 button; on phones it opens the photo picker) and by dropping
files anywhere on the page; into the 图集 on screen, if any. Uploaded memes skip 待确认 (you chose them).

Where to put a new meme (the collector's target 图集) is chosen where it happens and remembered there,
not in settings. For deeper changes, a `custom.css` in the library folder is loaded after the app's styles.
The cat, the name and the logo are not customisable.

- **Is:** a collector, dry humour, fond of sources and provenance.
- **Is not:** flashy, childish, sticker-pack style.

It is recognisable from three things used everywhere: the Pop Cat logo, the brand yellow, and black
Mondrian lines on warm paper.

## Colour

| token | value | use |
|---|---|---|
| `--paper` | `#F3EFE4` | page background |
| `--card` | `#FFFFFF` | cards, inputs, the meme's mat |
| `--ink` | `#161411` | text, all lines, hard shadows |
| `--muted` | `#6E685C` | secondary text |
| `--rule`, `--rule-soft` | `#CFC6B2`, `#E2DACA` | hairlines, card outlines |
| `--accent` | `#FFD21F` | the one loud colour: primary buttons, selection, focus ring, 今日一梗 |
| `--red`, `--blue` | `#DE3B2E`, `#1F4FA3` | Mondrian blocks only; red also marks failures |

夜间 swaps paper and ink (`:root[data-theme="night"]` in `tokens.css`); the yellow, the Mondrian colours and
the cat stay. Text on yellow is always dark (`--on-accent`); dark blocks with light text (toasts, badges)
use `--inverse-bg` / `--inverse-fg`, which flip with the theme.

## Type

- **Serif** (`--font-serif`, bundled *Noto Serif SC* subset, weights 600–900): the wordmark, headings,
  tabs, labels. It contains only the UI's own characters (`tools/fonts/subset.py`), so it must never be
  used for meme text. Meme text uses `--font-content-serif` or `--font-sans`, the reader's system fonts.
- **Sans** (`--font-sans`, system): body text.
- **Mono** (`--font-mono`, bundled *JetBrains Mono* subset): MEMESEEKS, numbers (No.0024), meta lines.
- The English name under 迷因捕手 is MEMESEEKS in mono caps, **justified to the width of the Chinese name**.

## Lines, blocks and the frame

The frame around the window follows Mondrian's rules, and so does every other Mondrian element:

1. Lines are black and straight and run until they meet another line or an edge. There are no loose ends
   and no gaps between a line and a block.
2. Colour fills whole cells, between lines.
3. Rhythm comes from line weight (2–6 px) and cell proportions, never from misaligned lines.
4. Planes are drawn first and lines on top, so seams cannot appear. The frame is one SVG computed for
   the window size.

Elsewhere: cards are white on paper with a hairline; primary buttons are yellow with a black border and a
hard shadow (`--shadow-hard`); shadows are never blurred.

## Components

Primary / secondary / dark buttons, chips, cards with a provenance label (No., source, date), the toast
(black with a yellow block; red block on failure), the 待确认 card, the progress bar in Mondrian cells,
the loading skeleton (paper with a fine grid), scrollbars (paper track, framed yellow thumb), selection
(yellow), the focus ring (black outline plus a yellow halo), back-to-top (framed yellow block).

## The cat

The logo is the Pop Cat: the silhouette and eyes traced from the classic open-mouth frame, the mouth an
ellipse fitted to it, and a chat bubble inside the mouth (a line of memes being swallowed). All the cat's
shapes are in `web/popcat.js`, generated by `tools/logo/` (see its README). The closed and the open state
use the same command list for every shape, so every animation is just interpolation:

| where | what happens | timing |
|---|---|---|
| loading | closed ↔ logo, played forward then back | 3.2 s loop |
| entrance | logo and name appear together; pop, pop (two quick half-opens); the mouth opens; the bubble pops; the lockup glides to its place while the page fades in | about 2.9 s; a click skips it |
| click the cat | swallows the bubble, shuts, opens, spits it out; the name next to it still goes home | 0.86 s |
| click it quickly | a counter "POP ×n" (a nod to popcat.click), a shorter gulp each click | 0.34 s per click |
| pull to refresh (touch) | open by default; pulling swallows the bubble and shuts the mouth, it stays shut while held; letting go opens it and spits the bubble out | |
| empty results | the cat with its mouth shut: 这里还没有梗 | still |
| 404 | the cat with its mouth wide open and nothing inside: 这张梗被吃掉了 | still |

The nose rises and shrinks as the mouth opens and disappears at half its size (no dot is left behind).

## Motion

- Page changes slide like presentation slides: the logo, the wordmark, the search box and an opened meme
  fly between pages (shared elements; a card's picture grows into its meme page and shrinks back into
  the card on 返回); the frame, the header links and the phone bar stay put; the rest slides left, or right
  when going back. Uses View Transitions and falls back to an instant change. Reloading a page in place
  (pull to refresh, new memes indexed) does not slide.
- The entrance hides the page from the first paint (the last known settings are kept in the browser for
  that) and fades it in while the lockup glides to the logo's place on the page.
- `--dur-fast` 150 ms for feedback, `--dur` 350 ms for small moves, `--dur-slow` 550 ms for page changes;
  `--ease` for moves, `--ease-out` for things appearing.
- `prefers-reduced-motion`: no entrance, no slides, no cat animations; everything still works.

## The browser collector (采集 meme)

It runs on other people's sites, so it stays small and isolated: a shadow root, system fonts only, short
animations. The button is the cat on a paper tile with a hard shadow; it can be dragged anywhere and
remembers its place per site (menu: 猫头回到右下角). The panel opens towards the middle of the screen. While
collecting, each ticked thumbnail flies into the cat's mouth and the cat gulps once per meme; it never
lags behind the last one. Done: it spits the bubble out. Failed: the mouth stays shut and a red block says
why.

## Regenerating assets

- UI text changed: `python tools/fonts/subset.py` (`tests/test_design_assets.py` tells you when).
- The cat changed: run the pipeline in `tools/logo/`, then `tools/logo/export.py`, which rewrites
  `web/popcat.js`, `web/icons/*` and the launcher's `memeseeks.ico`.
