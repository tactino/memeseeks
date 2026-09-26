# 迷因捕手 · memeseeks

[中文](README.md)

Describe what you remember about a meme, get it back from your own collection. Works across Chinese and English, runs on your machine; searching the web as well is optional and off by default. It is also a personal meme collection: 图集 (like playlists), 我喜欢, 刷梗 (full screen, one meme after another), and collecting from community pages as you read them.

**Status:** v0.3 — a local web app, the command line, one-line installers and a Docker image. A cross-language meme graph and re-making translated memes are on the roadmap.

## How it finds memes

Every image is read in up to three ways and the results are fused (reciprocal rank fusion):

| Route | What it uses | Needs a GPU? |
|---|---|---|
| OCR text | text printed on the meme ([RapidOCR](https://github.com/RapidAI/RapidOCR)), matched by meaning with [BGE-M3](https://huggingface.co/BAAI/bge-m3) | no |
| Picture | [Chinese-CLIP](https://github.com/OFA-Sys/Chinese-CLIP) image–text similarity | no |
| Description (optional) | a local vision-language model ([Qwen2.5-VL-7B](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)) writes topic / punchline | yes, ~16 GB VRAM |

On the maintainer's text-heavy collection the first two routes already find every query in the top 5, so the description route is off by default (numbers in `experiments/results/`).

## Install

**Windows** — open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.ps1 | iex
```

**macOS / Linux:**

```bash
curl -LsSf https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.sh | sh
```

It installs into one folder with its own Python (Windows `%LOCALAPPDATA%\memeseeks`, macOS `~/Library/Application Support/memeseeks`, Linux `~/.local/share/memeseeks`), adds a 迷因捕手 shortcut and starts it. The first start downloads about 3.9 GB of models; the web app shows the progress. From China it switches to mirrors by itself (PyPI, Python and the models). Nothing is added to PATH; to uninstall, delete that folder and the shortcut — your library, in `~/.memeseeks`, stays. Run the same line again to update.

To keep everything off drive C: (or install elsewhere), on Windows:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/tactino/memeseeks/main/scripts/install.ps1))) -Dir D:\memeseeks -Library D:\memeseeks-library
```

`-Dir` is the program, its Python and the models; `-Library` is your library (index, 图集, collected images); `-Models D:\some\hf-cache` reuses a Hugging Face cache you already have instead of downloading the models again. On macOS / Linux the same are `MEMESEEKS_DIR`, `MEMESEEKS_LIBRARY` and `MEMESEEKS_MODELS` in front of `sh`.

### By hand

Python 3.10 or newer.

```bash
git clone https://github.com/tactino/memeseeks && cd memeseeks
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # or the CUDA build for your GPU
pip install -e ".[ml,serve]"
```

The first run downloads about 3.9 GB of models into the Hugging Face cache (`HF_HOME`); the web app is up at once and shows the progress, and search works as soon as the download is done. **From China**, set `HF_ENDPOINT=https://hf-mirror.com` before starting. Indexing on a laptop CPU takes about 3.5 s per image (roughly an hour per 1,000 memes); only new images are processed on later runs.

**Windows + Anaconda:** don't build the venv from Anaconda's Python if you use torch ≥ 2.9 — Anaconda ships an older MSVC runtime next to `python.exe` and torch fails with `WinError 1114 … c10.dll`. Use a python.org or `uv`-managed Python instead (`uv venv --managed-python --python 3.12`).

## Run with Docker

No Python setup needed; CPU only.

```bash
git clone https://github.com/tactino/memeseeks && cd memeseeks
cp .env.example .env        # then set MEMES_DIR and a token (the file shows how to generate one)
docker compose up -d
docker compose logs -f      # wait for "memeseeks is at http://…"
```

- The first start downloads about 3.9 GB of models into the `models` volume and indexes your folder (≈ 3.5 s per image on a laptop CPU). **Nothing listens on port 8765 until indexing has finished** — follow the logs.
- Then open `http://<this machine's LAN address>:8765/?token=<your token>` once on each device; the browser remembers it.
- Later starts only index new images. After updating the code run `docker compose up -d --build`; `docker compose down -v` deletes the library and the downloaded models.
- The meme folder is mounted read-only. The container runs as uid 1000, so if you replace the `library` volume with a bind mount, make that folder writable by uid 1000.

## Use

```bash
memeseeks add ~/Pictures/memes            # index a folder; re-run any time, only new images are processed
memeseeks serve                           # web app at http://127.0.0.1:8765/
memeseeks serve --open                    # ... and open it in the browser (or just open it if it already runs)
memeseeks search "关于熬夜的"              # or search from the terminal
memeseeks status                          # what is in the library, and any images that failed a step
```

More:

```bash
memeseeks add ~/Pictures/memes --vlm      # also describe images with the local VLM (GPU); --no-vlm turns it off
memeseeks add ~/Pictures/memes --retry-failed   # redo images that failed a step last time
memeseeks search "cat judging you" -k 5 --json
memeseeks eval queries.csv                # score your own queries (see below)
memeseeks --lib D:\memes-lib status       # global options such as --lib go before the command
```

The library lives in `~/.memeseeks` (override with `--lib DIR` or `MEMESEEKS_HOME`). Nothing leaves your machine unless you turn on online search.

### The web app

It is a personal meme collection, a little like a music app is for songs:

- **Search** by what you remember; confident matches first, the rest folded under 可能相关.
- **图集** (like playlists): 全部, 我喜欢 and your own. Add a meme from its page with 加入图集; 上传 on any 图集 page, or drop images anywhere on the page.
- **刷梗**: full screen, one meme after another — a 图集 in order or shuffled, the memes similar to the one you tapped, or (from the header) the ones you have not seen for longest. Swipe, scroll or use the arrow keys.
- The home page has 今日一梗, your 图集 and 旧梗重温. Tap a meme for 复制 / 保存 / 分享 and its source.
- **设置**: 纸色 / 夜间, the Mondrian frame, the entrance animation, less motion, web search, your folders and connecting the browser. Settings live in the library, so every device sees them; a `custom.css` in the library folder is loaded after the app's styles.

On the computer running it (`localhost`) it also installs as an app from the browser menu.

**New memes are picked up by themselves.** While `serve` runs, images you add to any library folder are indexed in the background and become searchable within about a minute (`--no-watch` turns this off). On Windows the indexing runs at below-normal priority, so the rest of the computer stays responsive. The library also has an inbox folder, `<library>/inbox`, for memes that don't belong to one of your folders.

**From your phone:** run `memeseeks serve --host 0.0.0.0 --token <something secret>` (with the installer's version: its launcher, e.g. `D:\memeseeks\memeseeks.cmd`, with the same options) and open the printed link with your computer's LAN address. Over plain `http` the phone can search and **save**; **copy** and **share** (and installing as an app) need `localhost` or HTTPS, because browsers only allow them in a secure context.

### Collecting memes from community pages

A userscript adds a 采集 meme button to the pages you read. Click it and it lists the images on that page; the ones you tick go into your library's inbox, together with the site, the page link and its title, and are searchable within about a minute. It has special handling for 百度贴吧 (original-size images from every floor on the page), 小红书 (all images of a note) and 豆瓣小组 (large versions of topic and reply images), and a generic mode for any other site.

1. Install [Violentmonkey](https://violentmonkey.github.io/) (Firefox or Chrome).
2. With `memeseeks serve` running, open the web app's 设置 → 连接浏览器 → 安装采集 meme 脚本. The script is generated for your server and carries a key only your library knows; without it the inbox refuses uploads.
3. On any page, click the cat (drag it wherever you like), tick the images, pick where they go under 放进, and 采集.

Collected images with little text (fewer than 15 characters) are probably 表情包, so they wait under 「待确认」 in the header until you choose 要 (into the library) or 不要 (moved to `<library>/rejected`, not deleted; undo is one click). Your decisions are kept on your machine to train a personal classifier later. Images in your own folders are never held back.

It only acts when you click, only on the page you are looking at, and downloads at most two images a second. It never turns pages or collects in the background, and it sends nothing besides the image, the site name, the page link, the page title and the 图集 you picked. You can hide the button on a site, or put the cat back in its corner, from the Violentmonkey menu.

### Online search (optional)

Results from your own library and from the web are shown in separate sections. Web search is off by default. To turn it on, get a free [KLIPY](https://partner.klipy.com) API key and run:

```bash
MEMESEEKS_KLIPY_KEY=<your key> memeseeks serve --online klipy     # or set MEMESEEKS_ONLINE=klipy
```

When it is on, **the browser** sends your search words to KLIPY, together with a random per-library id and your IP address, and loads the images directly from KLIPY. The memeseeks server never relays or stores them. KLIPY's results are shown exactly as returned, possibly including ads; its terms don't allow filtering or reordering, so adjust content settings in the KLIPY Partner Panel. The key is visible to anyone who can open your web app. KLIPY covers English and Japanese well and Chinese only thinly.

### Scoring your own queries

`queries.csv` has a header row, then one query per row with the file name(s) it should find, separated by `;`:

```csv
query,expected
关于熬夜的,night_owl.jpg
猫在评判你,cat_judge.png;cat_judge_2.png
```

File names may be paths relative to the added folder or unique base names.

## Your data, and backing it up

The library folder (`~/.memeseeks` unless you chose another with `-Library`, `--lib` or `MEMESEEKS_HOME`) holds plain files: `collections.json` (图集 and 我喜欢), `settings.json`, `numbers.json`, `seen.json`, `inbox/` and `provenance.jsonl` (collected and uploaded images and where they came from), `review.jsonl` and `rejected/` (待确认), and `index/`.

- **Images in your own folders are only read, never changed.** 移出图库 only hides them.
- **To back up, copy the library folder.** The index can be rebuilt; 图集 and 我喜欢 cannot, so they are what the backup is for.
- **On a new computer**, copy the library folder over and install with `-Library` pointing at it. If your own meme folders moved, add them again under 设置 → 来源文件夹; 图集 know memes by their content, so nothing is lost.

## License

Code: MIT. The meme knowledge base (when it exists): CC BY-SA 4.0. The bundled subsets of Noto Serif SC and JetBrains Mono are under the SIL OFL 1.1.
