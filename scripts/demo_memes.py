"""Make a small set of demo memes, to try memeseeks without a collection of your own.

  python scripts/demo_memes.py OUT_DIR [--cache DIR]

They take the shapes memes usually have (a caption over a photo, a screenshotted post with its comments, a chat, a
foreign post with its translation, a comparison, a list, a chart), laid out in HTML and rendered by a headless
browser: `pip install playwright && playwright install chromium`. Every joke, account and chat was written for this
project; every picture is from Wikimedia Commons and marked CC0 or public domain there (checked on each download).
A font with Chinese characters is needed (Noto Sans SC, SIL Open Font License, is tried first).
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "memeseeks-demo (https://github.com/tactino/memeseeks)"}
FREE = {"cc0", "public domain"}

PHOTOS = {
    "keyboard": "File:Cat Sleeping on Keyboard.jpg",
    "flat": "File:Cat lying down 1.jpg",
    "scream": "File:Calico cat yawning.jpg",
    "yawn": "File:Yawning cat by David Montolio.jpg",
    "kitten": "File:A focused kitten (Pixabay).jpg",
    "carton": "File:A kitten in a carton (Flickr).jpg",
    "stare": "File:Patmos Just another cat (15397904857) (2014; cropped 2023).jpg",
    "sad_dog": "File:Black dog face close up.webp",
    "nose": "File:Shiba Inu Mutt 4.jpg",
    "courbet": "File:Gustave Courbet - Le Désespéré (1843).jpg",
    "mona": "File:Mona Lisa, by Leonardo da Vinci, from C2RMF retouched.jpg",
}

CSS = """
* { box-sizing: border-box; margin: 0; }
body { background: #fff; font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; }
.meme { width: 1000px; background: #fff; color: #111; overflow: hidden; }
.cap { padding: 44px 56px 38px; font-weight: 700; font-size: 54px; line-height: 1.42; text-align: center; }
.photo { width: 1000px; background-size: cover; background-position: center; }
.mark { position: absolute; right: 22px; bottom: 16px; font-size: 22px; color: rgba(255,255,255,.72);
  text-shadow: 0 1px 2px rgba(0,0,0,.45); font-weight: 500; }
.rel { position: relative; }
.over { position: absolute; left: 0; right: 0; bottom: 46px; text-align: center; color: #fff; font-weight: 900;
  font-size: 66px; line-height: 1.3; -webkit-text-stroke: 3px #000; paint-order: stroke fill;
  text-shadow: 0 3px 0 #000; }
.vs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; background: #fff; }
.vs .lab { padding: 30px 26px 22px; font-weight: 700; font-size: 46px; }
.vs .photo { width: auto; height: 560px; }
.post { padding: 44px 50px 40px; }
.who { display: flex; align-items: center; gap: 18px; }
.av { width: 76px; height: 76px; border-radius: 50%; overflow: hidden; flex: none; }
.name { font-weight: 700; font-size: 32px; }
.sub { color: #8a8a8a; font-size: 25px; margin-top: 2px; }
.body { font-size: 40px; line-height: 1.55; margin-top: 26px; }
.en { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 42px; line-height: 1.45; margin-top: 28px; }
.meta { color: #8a8a8a; font-size: 26px; margin-top: 26px; font-family: "Segoe UI", Arial, sans-serif; }
.stats { display: flex; gap: 40px; color: #555; font-size: 26px; margin-top: 18px; padding-top: 18px; border-top: 1px solid #e6e6e6; }
.tr { background: #f6f6f6; padding: 34px 50px 40px; font-size: 38px; line-height: 1.6; color: #222; }
.tr b { display: block; font-size: 26px; color: #999; font-weight: 500; margin-bottom: 6px; }
.chat { background: #ededed; padding-bottom: 36px; }
.chat .bar { background: #ededed; text-align: center; font-size: 34px; font-weight: 600; padding: 26px 0 22px; border-bottom: 1px solid #dcdcdc; }
.msg { display: flex; gap: 20px; padding: 26px 30px 0; align-items: flex-start; }
.msg.me { flex-direction: row-reverse; }
.sq { width: 78px; height: 78px; border-radius: 10px; overflow: hidden; flex: none; }
.bub { max-width: 640px; background: #fff; border-radius: 12px; padding: 20px 26px; font-size: 38px; line-height: 1.45; }
.me .bub { background: #95ec69; }
.cmts { border-top: 12px solid #f4f4f4; padding: 34px 50px 30px; }
.cmts h4 { font-size: 30px; margin-bottom: 8px; }
.cmt { display: flex; gap: 18px; padding: 24px 0; border-bottom: 1px solid #efefef; }
.cmt:last-child { border-bottom: 0; }
.cmt .av { width: 62px; height: 62px; font-size: 28px; }
.cmt .name { font-size: 27px; color: #666; font-weight: 500; }
.cmt .text { font-size: 35px; line-height: 1.5; margin-top: 6px; }
.likes { margin-left: auto; color: #999; font-size: 24px; white-space: nowrap; padding-top: 6px; }
.list { padding: 46px 60px 30px; }
.list h2 { font-size: 54px; line-height: 1.35; }
.list li { font-size: 42px; line-height: 1.5; margin: 18px 0 0 1.1em; font-weight: 500; }
.pie { padding: 44px 60px 56px; }
.pie h2 { text-align: center; font-size: 56px; }
.pie .row { display: flex; align-items: center; gap: 56px; margin-top: 44px; }
.disc { width: 420px; height: 420px; border-radius: 50%; flex: none; }
.legend div { display: flex; align-items: center; gap: 16px; font-size: 38px; margin: 18px 0; }
.legend i { width: 34px; height: 34px; border-radius: 6px; display: inline-block; }
"""


def e(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def photo(src: str, height: int, position: str = "center", mark: str = "", zoom: int = 0) -> str:
    tag = f'<div class="mark">{e(mark)}</div>' if mark else ""
    size = f";background-size:{zoom}%" if zoom else ""  # zoom: the picture's width, as a share of the meme's
    return (f'<div class="photo rel" style="height:{height}px;background-image:url({src});'
            f'background-position:{position}{size}">{tag}</div>')


def caption(src, text, height, position="center", mark="", zoom=0):
    return f'<div class="cap">{e(text)}</div>' + photo(src, height, position, mark, zoom)


def overlay(src, text, height, position="center"):
    return f'<div class="rel">{photo(src, height, position)}<div class="over">{e(text)}</div></div>'


def versus(a_label, a_src, b_label, b_src, a_pos="center", b_pos="center"):
    cell = lambda label, src, pos: (f'<div><div class="lab">{e(label)}</div>'
                                    f'<div class="photo" style="background-image:url({src});background-position:{pos}"></div></div>')
    return f'<div class="vs">{cell(a_label, a_src, a_pos)}{cell(b_label, b_src, b_pos)}</div>'


def avatar(char, color, cls="av"):
    """A default profile picture: a head and shoulders on a colour (char only tells people apart in the source)."""
    return (f'<div class="{cls}" style="background:{color}"><svg viewBox="0 0 40 40" width="100%" height="100%">'
            '<circle cx="20" cy="15" r="7" fill="rgba(255,255,255,.85)"/>'
            '<path d="M6 36c1-8 7-12 14-12s13 4 14 12z" fill="rgba(255,255,255,.85)"/></svg></div>')


def foreign_post(name, handle, char, color, text, when, stats, translation):
    return (f'<div class="post"><div class="who">{avatar(char, color)}<div><div class="name">{e(name)}</div>'
            f'<div class="sub">{e(handle)}</div></div></div><div class="en">{e(text)}</div>'
            f'<div class="meta">{e(when)}</div><div class="stats">{"".join(f"<span>{e(s)}</span>" for s in stats)}</div></div>'
            f'<div class="tr"><b>翻译</b>{e(translation)}</div>')


def chat(title, messages):
    rows = "".join(f'<div class="msg{" me" if me else ""}">{avatar(char, color, "sq")}<div class="bub">{e(text)}</div></div>'
                   for me, char, color, text in messages)
    return f'<div class="chat"><div class="bar">{e(title)}</div>{rows}</div>'


def post(name, char, color, when, text, comments):
    rows = "".join(
        f'<div class="cmt">{avatar(c_char, c_color)}<div><div class="name">{e(c_name)}'
        f'</div><div class="text">{e(c_text)}</div></div>'
        f'<div class="likes">♡ {e(likes)}</div></div>' for c_name, c_char, c_color, c_text, likes in comments)
    return (f'<div class="post"><div class="who">{avatar(char, color)}<div><div class="name">{e(name)}</div>'
            f'<div class="sub">{e(when)}</div></div></div><div class="body">{e(text)}</div></div>'
            f'<div class="cmts"><h4>共 {len(comments) + 214} 条评论</h4>{rows}</div>')


def listing(title, items, src, height, position="center"):
    return (f'<div class="list"><h2>{e(title)}</h2><ul>{"".join(f"<li>{e(i)}</li>" for i in items)}</ul></div>'
            + photo(src, height, position))


def pie(title, slices):
    stops, at = [], 0
    for _, share, color in slices:
        stops.append(f"{color} {at}% {at + share}%")
        at += share
    legend = "".join(f'<div><i style="background:{c}"></i>{e(n)}</div>' for n, _, c in slices)
    return (f'<div class="pie"><h2>{e(title)}</h2><div class="row"><div class="disc" '
            f'style="background:conic-gradient({", ".join(stops)})"></div><div class="legend">{legend}</div></div></div>')


def memes(p):
    return {
        "keyboard_cat.jpg": caption(p["keyboard"], "上班时间的我：\n正在全力推进工作", 600, "40% 55%", "@今天也想下班"),
        "battery_low.jpg": caption(p["flat"], "下班回到家的我：\n电量 1%", 600, "56% 64%", zoom=190),
        "monday.jpg": overlay(p["scream"], "想到明天还要上班", 620, "center 35%"),
        "versus.jpg": versus("朋友圈里的我：", p["kitten"], "现实中的我：", p["yawn"], "center 30%", "45% center"),
        "bed_thoughts.jpg": foreign_post(
            "Late Night Thoughts", "@latenight.thoughts", "L", "#5b6ee1",
            "My bed is a magical place where I suddenly remember everything I forgot to do.",
            "2:47 AM · Mar 8, 2024", ["12.8K 转发", "96.1K 喜欢"], "我的床是个神奇的地方：一躺上去，就会突然想起所有忘了做的事。"),
        "mom_chat.jpg": chat("妈妈", [(False, "妈", "#e8a33d", "在干嘛"), (True, "我", "#6a8fd6", "在图书馆学习"),
                                    (False, "妈", "#e8a33d", "那你朋友圈的定位怎么在火锅店"),
                                    (True, "我", "#6a8fd6", "……火锅店旁边的图书馆")]),
        "canteen_post.jpg": post(
            "一只社恐的猫", "猫", "#f28c6b", "3 小时前",
            "求助：一个人在公司食堂吃饭，怎样才能看起来不那么孤单？",
            [("今天也不想上班", "班", "#7fb36a", "戴上耳机，对着空气点头，偶尔笑一下", "2.3万"),
             ("一只社恐的猫", "猫", "#f28c6b", "试了，同事问我是不是在谈恋爱", "8412")]),
        "social_anxiety.jpg": listing("社恐的日常：", ["听到敲门声，先假装不在家", "外卖放门口，等人走远了再开门",
                                                "电话响了，等它自己停"], p["carton"], 560, "center 45%"),
        "salary.jpg": pie("我的工资都去哪了", [("房租", 35, "#e0694f"), ("外卖", 20, "#f2b544"), ("奶茶", 10, "#7fb3d5"),
                                        ("我也不知道", 35, "#9aa0a6")]),
        "two_am.jpg": caption(p["stare"], "我妈看到我凌晨两点\n还在刷手机", 760, "center 40%", "@今天也想下班"),
        "one_more_thing.jpg": caption(p["sad_dog"], "下班前五分钟：\n“这个你顺手弄一下”", 620, "center 40%"),
        "nosy_dog.jpg": caption(p["nose"], "让我看看你在跟谁聊天", 820, "center 35%"),
        "exam.jpg": caption(p["courbet"], "考试前：我能行\n考试后：我是谁 我在哪", 800, "center 30%"),
        "no_overtime.jpg": caption(p["mona"], "听说今天不用加班", 820, "center 22%"),
    }


def fetch(title: str, cache: Path) -> str:
    """The picture as a data URI, 1400 px wide, kept in `cache`; refuses one Commons does not mark CC0 or public domain."""
    path = cache / (title.removeprefix("File:").rsplit(".", 1)[0][:70].replace(" ", "_") + ".jpg")
    if not path.exists():
        query = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo", "format": "json",
                                        "formatversion": 2, "iiprop": "url|extmetadata", "iiurlwidth": 1400})
        with urllib.request.urlopen(urllib.request.Request(f"{API}?{query}", headers=UA), timeout=60) as r:
            info = json.load(r)["query"]["pages"][0]["imageinfo"][0]
        licence = info["extmetadata"].get("LicenseShortName", {}).get("value", "")
        if licence.lower() not in FREE:
            raise SystemExit(f"{title} is marked {licence!r} on Commons, not CC0 or public domain")
        with urllib.request.urlopen(urllib.request.Request(info["thumburl"], headers=UA), timeout=120) as r:
            data = r.read()
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="make a small set of demo memes")
    ap.add_argument("out", type=Path)
    ap.add_argument("--cache", type=Path, help="where to keep the downloaded pictures (default: OUT_DIR/../demo-pictures)")
    args = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright

    cache = args.cache or args.out.resolve().parent / "demo-pictures"
    pictures = {key: fetch(title, cache) for key, title in PHOTOS.items()}
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        for name, body in memes(pictures).items():
            page.set_content(f"<!doctype html><meta charset=utf-8><style>{CSS}</style><div class=meme>{body}</div>")
            page.wait_for_timeout(150)
            page.locator(".meme").screenshot(path=str(args.out / name), type="jpeg", quality=90)
        browser.close()
    print(f"{len(memes(pictures))} memes in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
