"""Draw a small set of demo memes: for the README's screenshots, or to try memeseeks without a collection.

  python scripts/demo_memes.py OUT_DIR [--font NotoSansSC.otf]

Every joke here was written for this project and every picture is drawn by this script, so the images can be
shared freely. It needs a font with Chinese characters: Noto Sans SC (SIL Open Font License) by default.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = ["C:/Windows/Fonts/Noto Sans SC Bold (TrueType).otf", "C:/Windows/Fonts/NotoSansSC-VF.ttf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/System/Library/Fonts/PingFang.ttc"]
INK, PAPER, CREAM, YELLOW, BLUE, RED, NIGHT = "#1d1d1b", "#ffffff", "#f6f1e7", "#ffd23f", "#2f5dd9", "#e4412b", "#1b2340"


class Draw:
    def __init__(self, font_path: str):
        self.font_path = font_path

    def font(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self.font_path, size)

    def text(self, d: ImageDraw.ImageDraw, xy, text: str, size: int, fill=INK, anchor="la", spacing=1.35):
        f = self.font(size)
        x, y = xy
        for line in text.split("\n"):
            d.text((x, y), line, font=f, fill=fill, anchor=anchor)
            y += int(size * spacing)
        return y

    def center(self, d, w: int, y: int, text: str, size: int, fill=INK, spacing=1.35):
        return self.text(d, (w // 2, y), text, size, fill, anchor="ma", spacing=spacing)


def cat(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill=INK, eyes="open", face=PAPER):
    """A round cat face: ears, eyes (open / half / closed), a small mouth."""
    ear = r * 0.62
    for side in (-1, 1):
        base = cx + side * r * 0.55
        d.polygon([(base - ear * 0.5, cy - r * 0.62), (base + side * ear * 0.15, cy - r * 1.28),
                   (base + ear * 0.5, cy - r * 0.62)], fill=fill)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    ex, ey, er = r * 0.38, cy - r * 0.08, r * 0.17
    for side in (-1, 1):
        x = cx + side * ex
        if eyes == "open":
            d.ellipse([x - er, ey - er, x + er, ey + er], fill=face)
        elif eyes == "half":  # judging you
            d.chord([x - er, ey - er, x + er, ey + er], 0, 180, fill=face)
            d.line([x - er * 1.2, ey, x + er * 1.2, ey], fill=face, width=max(2, r // 22))
        else:
            d.arc([x - er, ey - er * 0.6, x + er, ey + er * 0.6], 200, 340, fill=face, width=max(3, r // 18))
    mw = r * 0.16
    d.line([cx - mw, cy + r * 0.34, cx, cy + r * 0.42, cx + mw, cy + r * 0.34], fill=face, width=max(3, r // 20),
           joint="curve")


def bubble(dr: Draw, d, x: int, y: float, text: str, size: int, right: bool, width: int):
    f = dr.font(size)
    tw = int(d.textlength(text, font=f))
    pad = size * 0.55
    bw, bh = tw + pad * 2, size * 1.9
    x0 = width - x - bw if right else x
    d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=size * 0.5, fill=YELLOW if right else PAPER,
                        outline=INK, width=3)
    d.text((x0 + pad, y + bh / 2), text, font=f, fill=INK, anchor="lm")
    return y + bh + size * 0.7


def meme_off_work(dr: Draw):
    im = Image.new("RGB", (900, 900), CREAM)
    d = ImageDraw.Draw(im)
    dr.center(d, 900, 250, "上班的时候\n想下班", 92)
    dr.center(d, 900, 540, "下班的时候\n想辞职", 92, fill=RED)
    dr.text(d, (880, 870), "@示例小号", 22, fill="#9a948a", anchor="rs")
    return im


def meme_asleep(dr: Draw):
    im = Image.new("RGB", (900, 680), "#ededed")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 900, 110], fill=PAPER)
    dr.center(d, 900, 36, "小鱼", 40)
    y = 170.0
    for text, right in (("睡了吗", False), ("睡了", True), ("那你是在梦里回我吗", False), ("对，梦里信号不太好", True)):
        y = bubble(dr, d, 50, y, text, 46, right, 900)
    return im


def meme_procrastinate(dr: Draw):
    im = Image.new("RGB", (900, 900), YELLOW)
    d = ImageDraw.Draw(im)
    dr.center(d, 900, 150, "我不是在拖延", 84)
    dr.center(d, 900, 330, "我是在等灵感", 84)
    dr.center(d, 900, 560, "灵感也在拖延", 84, fill=BLUE)
    return im


def meme_night_owl(dr: Draw):
    im = Image.new("RGB", (900, 1000), NIGHT)
    d = ImageDraw.Draw(im)
    d.ellipse([640, 90, 790, 240], fill="#f5e6a8")
    d.ellipse([600, 70, 740, 210], fill=NIGHT)
    for i in range(18):
        x, y = (i * 137) % 860 + 20, (i * 71) % 320 + 30
        d.ellipse([x, y, x + 5, y + 5], fill="#c9d1f0")
    dr.center(d, 900, 400, "凌晨三点的我：", 64, fill="#c9d1f0")
    dr.center(d, 900, 520, "再看一个视频就睡", 80, fill=PAPER)
    dr.center(d, 900, 800, "（第 12 个）", 48, fill="#8d97c4")
    return im


def meme_cat_judge(dr: Draw):
    im = Image.new("RGB", (900, 1000), PAPER)
    d = ImageDraw.Draw(im)
    cat(d, 450, 470, 250, eyes="half")
    dr.center(d, 900, 70, "你刚才说“就吃一口”", 60)
    dr.center(d, 900, 830, "猫：我都看见了", 64, fill=RED)
    return im


def meme_weekend(dr: Draw):
    im = Image.new("RGB", (900, 1000), PAPER)
    d = ImageDraw.Draw(im)
    y = dr.text(d, (70, 90), "- 你周末干嘛了？", 58)
    y = dr.text(d, (70, y + 40), "- 躺着", 58)
    y = dr.text(d, (70, y + 40), "- 然后呢？", 58)
    dr.text(d, (70, y + 40), "- 换了个姿势躺着", 58)
    cat(d, 720, 830, 95, eyes="closed")
    return im


def meme_exam(dr: Draw):
    im = Image.new("RGB", (900, 1100), CREAM)
    d = ImageDraw.Draw(im)
    rows = (("考试前", "我能行", YELLOW), ("考试中", "我是谁", "#ffe8a3"), ("考试后", "我在哪", "#fff4d1"))
    for k, (when, what, fill) in enumerate(rows):
        top = 60 + k * 340
        d.rectangle([60, top, 840, top + 300], fill=fill, outline=INK, width=5)
        dr.text(d, (100, top + 40), when, 50, fill="#6b665c")
        dr.text(d, (100, top + 140), what, 96)
    return im


def meme_wallet(dr: Draw):
    im = Image.new("RGB", (900, 900), "#e9f2e4")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([230, 300, 670, 620], radius=40, fill="#7a5a3a", outline=INK, width=6)
    d.rounded_rectangle([520, 400, 700, 520], radius=24, fill="#8f6c49", outline=INK, width=6)
    for x in (320, 440):
        d.ellipse([x - 18, 410, x + 18, 446], fill=PAPER)
    d.arc([330, 470, 430, 560], 200, 340, fill=PAPER, width=8)
    dr.center(d, 900, 110, "月底的钱包：", 70)
    dr.center(d, 900, 700, "我已经尽力了", 80, fill=RED)
    return im


def meme_room(dr: Draw):
    im = Image.new("RGB", (900, 860), PAPER)
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 150, 150], fill=YELLOW, outline=INK, width=4)
    dr.text(d, (180, 70), "整理控小王", 40)
    dr.text(d, (180, 122), "2 小时前", 30, fill="#9a948a")
    dr.text(d, (60, 220), "花了一整天\n终于把房间收拾干净了！", 58)
    d.line([60, 520, 840, 520], fill="#e0dcd4", width=3)
    dr.text(d, (60, 570), "评论 3", 34, fill="#6b665c")
    cat(d, 110, 720, 46)
    dr.text(d, (190, 670), "楼下的猫", 36, fill="#6b665c")
    dr.text(d, (190, 730), "已经帮你弄乱了，不用谢", 46)
    return im


def meme_early(dr: Draw):
    im = Image.new("RGB", (900, 900), BLUE)
    d = ImageDraw.Draw(im)
    dr.center(d, 900, 260, "明天一定早睡", 96, fill=PAPER)
    dr.center(d, 900, 520, "——我，第 365 次说", 54, fill=YELLOW)
    return im


def meme_diet(dr: Draw):
    im = Image.new("RGB", (900, 900), "#fde3dc")
    d = ImageDraw.Draw(im)
    dr.center(d, 900, 200, "减肥第一天", 90)
    dr.center(d, 900, 420, "先吃饱", 120, fill=RED)
    dr.center(d, 900, 620, "才有力气减", 90)
    return im


def meme_monday(dr: Draw):
    im = Image.new("RGB", (1000, 700), PAPER)
    d = ImageDraw.Draw(im)
    d.line([500, 40, 500, 660], fill=INK, width=5)
    dr.center(d, 500, 60, "周一的我", 56)
    dr.text(d, (750, 60), "周五的我", 56, anchor="ma")
    cat(d, 250, 380, 150, eyes="closed")
    cat(d, 750, 380, 150, fill=YELLOW, face=INK)
    return im


def meme_english(dr: Draw):
    im = Image.new("RGB", (900, 900), PAPER)
    d = ImageDraw.Draw(im)
    y = dr.text(d, (70, 120), "me: I'll just check my phone\nfor five minutes", 56)
    dr.text(d, (70, y + 70), "the sun, rising:", 56)
    d.pieslice([300, 620, 600, 920], 180, 360, fill=YELLOW, outline=INK, width=5)
    for k in range(7):
        a = math.pi * (k + 1) / 8
        d.line([450 - 190 * math.cos(a), 770 - 190 * math.sin(a), 450 - 250 * math.cos(a), 770 - 250 * math.sin(a)],
               fill=INK, width=6)
    return im


def meme_traditional(dr: Draw):
    im = Image.new("RGB", (900, 900), CREAM)
    d = ImageDraw.Draw(im)
    dr.center(d, 900, 230, "這個梗我收藏了", 80)
    dr.center(d, 900, 430, "下次吵架的時候用", 64, fill=BLUE)
    return im


MEMES = {
    "off_work.png": meme_off_work, "asleep.png": meme_asleep, "procrastinate.png": meme_procrastinate,
    "night_owl.jpg": meme_night_owl, "cat_judge.png": meme_cat_judge, "weekend.png": meme_weekend,
    "exam.png": meme_exam, "wallet.png": meme_wallet, "room.png": meme_room, "early.png": meme_early,
    "diet.png": meme_diet, "monday.png": meme_monday, "phone.png": meme_english, "collected.png": meme_traditional,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="draw a small set of demo memes")
    ap.add_argument("out", type=Path)
    ap.add_argument("--font", help="a font with Chinese characters")
    args = ap.parse_args(argv)
    font = args.font or next((f for f in FONTS if Path(f).exists()), None)
    if not font:
        print("no font with Chinese characters found; pass --font", file=sys.stderr)
        return 1
    dr = Draw(font)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, make in MEMES.items():
        im = make(dr)
        im.save(args.out / name, quality=90) if name.endswith(".jpg") else im.save(args.out / name, optimize=True)
    print(f"{len(MEMES)} memes in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
