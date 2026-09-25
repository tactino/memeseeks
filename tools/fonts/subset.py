"""Build the two bundled web fonts from their OFL sources, keeping only the characters the UI uses.

  memeseeks-serif.woff2  Noto Serif SC, weights 600-900: the wordmark, headings, labels (UI text only;
                         meme text is shown in the reader's system fonts)
  memeseeks-mono.woff2   JetBrains Mono, weights 400-700, ASCII: MEMESEEKS, numbers, meta lines

Run it after changing UI text; tests/test_design_assets.py fails until the serif font covers every
Chinese character in the web app and the browser script.

  pip install fonttools brotli
  python tools/fonts/subset.py [--serif path/to/NotoSerifSC[wght].ttf] [--mono path/to/JetBrainsMono[wght].ttf]

Missing sources are downloaded from the google/fonts repository.
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "src" / "memeseeks" / "web" / "fonts"
UI_FILES = [*(REPO / "src" / "memeseeks" / "web").glob("*.html"), *(REPO / "src" / "memeseeks" / "web").glob("*.js"),
            *(REPO / "src" / "memeseeks" / "browser").glob("*.js")]
GF = "https://github.com/google/fonts/raw/main/ofl"
SOURCES = {"serif": f"{GF}/notoserifsc/NotoSerifSC%5Bwght%5D.ttf", "mono": f"{GF}/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"}
LICENSES = {"NotoSerifSC-OFL.txt": f"{GF}/notoserifsc/OFL.txt", "JetBrainsMono-OFL.txt": f"{GF}/jetbrainsmono/OFL.txt"}
CJK = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯—…·“”‘’]")
ASCII = "".join(chr(c) for c in range(0x20, 0x7F))
ALWAYS = "迷因捕手梗图" + "×→←↑↓·—…「」『』（），。：；！？、"


def ui_chars() -> str:
    found = set(ALWAYS)
    for f in UI_FILES:
        found |= set(CJK.findall(f.read_text(encoding="utf-8")))
    return "".join(sorted(found))


def fetch(url: str, dest: Path) -> Path:
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=300) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def build(src: Path, out: Path, text: str, weights: tuple[int, int]) -> int:
    font = TTFont(src)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt", "palt", "vpal", "halt", "locl"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)  # characters first (the font gets small), then the weight range we use
    font = instancer.instantiateVariableFont(font, {"wght": weights})
    font.flavor = "woff2"
    font.save(out)
    return out.stat().st_size


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serif", type=Path)
    ap.add_argument("--mono", type=Path)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    chars = ui_chars()
    with tempfile.TemporaryDirectory() as tmp:
        serif = args.serif or fetch(SOURCES["serif"], Path(tmp) / "serif.ttf")
        mono = args.mono or fetch(SOURCES["mono"], Path(tmp) / "mono.ttf")
        n1 = build(serif, OUT / "memeseeks-serif.woff2", chars + ASCII, (600, 900))
        n2 = build(mono, OUT / "memeseeks-mono.woff2", ASCII + "×·—…", (400, 700))
        for name, url in LICENSES.items():
            if not (OUT / name).exists():
                fetch(url, OUT / name)
    (OUT / "serif-chars.txt").write_text(chars + "\n", encoding="utf-8")
    print(f"serif: {len(chars)} UI characters, {n1 / 1024:.0f} KB; mono: {n2 / 1024:.0f} KB -> {OUT}")


if __name__ == "__main__":
    main()
