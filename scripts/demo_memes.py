"""Make a small set of demo memes: for the README's screenshots, or to try memeseeks without a collection.

  python scripts/demo_memes.py OUT_DIR [--font NotoSansSC-Bold.otf] [--cache DIR]

Each one is a public-domain painting (downloaded from Wikimedia Commons, where each file is marked public domain)
under a caption written for this project, in the plain style of a Chinese 配文图. It needs a font with Chinese
characters: Noto Sans SC (SIL Open Font License) by default.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = ["C:/Windows/Fonts/Noto Sans SC Bold (TrueType).otf", "C:/Windows/Fonts/NotoSansSC-VF.ttf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/System/Library/Fonts/PingFang.ttc"]
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "memeseeks-demo (https://github.com/tactino/memeseeks)"}
WIDTH = 1000

# file name, the painting on Commons, the part of it to keep (left, top, right, bottom, as fractions), caption
MEMES = [
    ("sunday_night.jpg", "File:Edvard Munch, 1893, The Scream, oil, tempera and pastel on cardboard, 91 x 73 cm, "
     "National Gallery of Norway.jpg", (0.04, 0.22, 0.96, 0.98), "周日晚上十一点\n突然想起明天要上班"),
    ("no_overtime.jpg", "File:Mona Lisa, by Leonardo da Vinci, from C2RMF retouched.jpg",
     (0.1, 0.06, 0.9, 0.6), "听说今天不用加班"),
    ("night_owl.jpg", "File:Van Gogh - Starry Night - Google Art Project.jpg",
     (0, 0, 1, 1), "凌晨三点的我：\n再看一个视频就睡"),
    ("deadline.jpg", "File:Tsunami by hokusai 19th century.jpg", (0, 0, 1, 1), "deadline 向我涌来的样子"),
    ("one_bite.jpg", "File:1665 Girl with a Pearl Earring.jpg", (0.06, 0.04, 0.94, 0.9), "你刚才说“就吃一口”？"),
    ("bill.jpg", "File:Caravaggio - Boy Bitten by a Lizard.jpg", (0, 0.02, 1, 0.82), "打开这个月的电费账单"),
    ("exam.jpg", "File:Gustave Courbet - Le Désespéré (1843).jpg", (0, 0, 1, 1), "考试前：我能行\n考试后：我是谁 我在哪"),
    ("friday.jpg", "File:Caspar David Friedrich - Wanderer above the sea of fog.jpg", (0, 0, 1, 0.9),
     "周五下午四点五十九分\n眺望周末"),
    ("winter_commute.jpg", "File:Pieter Bruegel the Elder - Hunters in the Snow (Winter) - Google Art Project.jpg",
     (0, 0, 1, 1), "冬天早上七点\n出门上班的打工人"),
    ("month_end.jpg", "File:Jean-François Millet - Gleaners - Google Art Project 2.jpg", (0, 0, 1, 1),
     "月底在沙发缝里找零钱"),
    ("weekend.jpg", "File:Flaming June, by Frederic Lord Leighton (1830-1896).jpg", (0, 0, 1, 1),
     "- 你周末干嘛了？\n- 躺着\n- 然后呢？\n- 换了个姿势躺着"),
]


def fetch(title: str, cache: Path) -> Image.Image:
    """The painting, 1200 px wide, kept in `cache` after the first download. Refuses one not marked public domain."""
    path = cache / (title.removeprefix("File:").rsplit(".", 1)[0][:80].replace(" ", "_") + ".jpg")
    if not path.exists():
        query = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo", "format": "json",
                                        "formatversion": 2, "iiprop": "url|extmetadata", "iiurlwidth": 1200})
        with urllib.request.urlopen(urllib.request.Request(f"{API}?{query}", headers=UA), timeout=60) as r:
            info = json.load(r)["query"]["pages"][0]["imageinfo"][0]
        licence = info["extmetadata"].get("LicenseShortName", {}).get("value", "")
        if licence.lower() != "public domain":
            raise SystemExit(f"{title} is marked {licence!r}, not public domain")
        with urllib.request.urlopen(urllib.request.Request(info["thumburl"], headers=UA), timeout=120) as r:
            data = r.read()
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return Image.open(io.BytesIO(path.read_bytes())).convert("RGB")


def meme(painting: Image.Image, crop, caption: str, font_path: str) -> Image.Image:
    w, h = painting.size
    picture = painting.crop((round(crop[0] * w), round(crop[1] * h), round(crop[2] * w), round(crop[3] * h)))
    picture = picture.resize((WIDTH, round(picture.height * WIDTH / picture.width)), Image.LANCZOS)
    lines = caption.split("\n")
    dialogue = all(line.startswith("- ") for line in lines)
    size = 56 if max(len(line) for line in lines) <= 13 else 48
    font = ImageFont.truetype(font_path, size)
    step, pad = round(size * 1.45), 46
    band = pad * 2 + step * len(lines) - round(size * 0.45)
    im = Image.new("RGB", (WIDTH, band + picture.height), "white")
    d = ImageDraw.Draw(im)
    for k, line in enumerate(lines):
        y = pad + k * step
        if dialogue:  # a dialogue reads down the left, one line a turn
            d.text((64, y), line, font=font, fill="#111111")
        else:
            d.text((WIDTH // 2, y), line, font=font, fill="#111111", anchor="ma")
    im.paste(picture, (0, band))
    return im


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="make a small set of demo memes from public-domain paintings")
    ap.add_argument("out", type=Path)
    ap.add_argument("--font", help="a font with Chinese characters")
    ap.add_argument("--cache", type=Path, help="where to keep the downloaded paintings (default: OUT_DIR/../demo-paintings)")
    args = ap.parse_args(argv)
    font = args.font or next((f for f in FONTS if Path(f).exists()), None)
    if not font:
        print("no font with Chinese characters found; pass --font", file=sys.stderr)
        return 1
    cache = args.cache or args.out.resolve().parent / "demo-paintings"
    args.out.mkdir(parents=True, exist_ok=True)
    for name, title, crop, caption in MEMES:
        meme(fetch(title, cache), crop, caption, font).save(args.out / name, quality=88)
    print(f"{len(MEMES)} memes in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
