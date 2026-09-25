# 迷因捕手 · memeseeks

Describe what you remember about a meme, get it back from your own collection. Works across Chinese and English, runs on your machine; searching the web as well is optional and off by default.

**Status:** v0.2 — command line, a local web app and a Docker image. A cross-language meme graph and re-making translated memes are on the roadmap.

## How it finds memes

Every image is read in up to three ways and the results are fused (reciprocal rank fusion):

| Route | What it uses | Needs a GPU? |
|---|---|---|
| OCR text | text printed on the meme ([RapidOCR](https://github.com/RapidAI/RapidOCR)), matched by meaning with [BGE-M3](https://huggingface.co/BAAI/bge-m3) | no |
| Picture | [Chinese-CLIP](https://github.com/OFA-Sys/Chinese-CLIP) image–text similarity | no |
| Description (optional) | a local vision-language model ([Qwen2.5-VL-7B](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)) writes topic / punchline | yes, ~16 GB VRAM |

On the maintainer's text-heavy collection the first two routes already find every query in the top 5, so the description route is off by default (numbers in `experiments/results/`).

## Install

Python 3.10 or newer.

```bash
git clone https://github.com/tactino/memeseeks && cd memeseeks
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # or the CUDA build for your GPU
pip install -e ".[ml,serve]"
```

The first run downloads about 4 GB of models into the Hugging Face cache (`HF_HOME`). Indexing on a laptop CPU takes about 3.5 s per image (roughly an hour per 1,000 memes); only new images are processed on later runs.

**Windows + Anaconda:** don't build the venv from Anaconda's Python if you use torch ≥ 2.9 — Anaconda ships an older MSVC runtime next to `python.exe` and torch fails with `WinError 1114 … c10.dll`. Use a python.org or `uv`-managed Python instead (`uv venv --managed-python --python 3.12`).

## Run with Docker

No Python setup needed; CPU only.

```bash
git clone https://github.com/tactino/memeseeks && cd memeseeks
cp .env.example .env        # then set MEMES_DIR and a token (the file shows how to generate one)
docker compose up -d
docker compose logs -f      # wait for "memeseeks is at http://…"
```

- The first start downloads about 4 GB of models into the `models` volume and indexes your folder (≈ 3.5 s per image on a laptop CPU). **Nothing listens on port 8765 until indexing has finished** — follow the logs.
- Then open `http://<this machine's LAN address>:8765/?token=<your token>` once on each device; the browser remembers it.
- Later starts only index new images. After updating the code run `docker compose up -d --build`; `docker compose down -v` deletes the library and the downloaded models.
- The meme folder is mounted read-only. The container runs as uid 1000, so if you replace the `library` volume with a bind mount, make that folder writable by uid 1000.

## Use

```bash
memeseeks add ~/Pictures/memes            # index a folder; re-run any time, only new images are processed
memeseeks serve                           # web app at http://127.0.0.1:8765/
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

The home screen shows 旧梗重温 — memes you have not seen in a while — and a search box. Tap a meme for 复制 / 保存 / 分享. On the computer running it (`localhost`) it also installs as an app from the browser menu.

**From your phone:** run `memeseeks serve --host 0.0.0.0 --token <something secret>` and open the printed link with your computer's LAN address. Over plain `http` the phone can search and **save**; **copy** and **share** (and installing as an app) need `localhost` or HTTPS, because browsers only allow them in a secure context.

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

## License

Code: MIT. The meme knowledge base (when it exists): CC BY-SA 4.0.
