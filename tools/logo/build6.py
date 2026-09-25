"""B2 logo (bubble inside the mouth), smoothed outline, thicker eyes: sheet with both mouth colours."""

import json
from pathlib import Path

d = json.load(open("popcat/classic.json"))
K, Y, P, WH, RED = "#161411", "#FFD21F", "#F3EFE4", "#FFFFFF", "#DE3B2E"
m = d["mouth"]
cx, cy, rx, ry, ang = m["cx"], m["cy"], m["rx"], m["ry"], m["angle"]
x0, y0, w, h = d["box"]

# bubble: ~12% larger than before, sitting in the upper right of the mouth
BW, BH, R = 168, 108, 28
BX, BY = cx - 0.12 * rx, cy - 0.45 * ry
# tail: a short, wide wedge from the bottom edge towards the throat, so its white part is visible
BASE_L, BASE_R = BX + 26, BX + 82
TIP = (BX + 4, BY + BH + 50)


def bubble(stroke_w=11):
    path = (f"M{BX + R:.0f} {BY:.0f} H{BX + BW - R:.0f} A{R} {R} 0 0 1 {BX + BW:.0f} {BY + R:.0f} "
            f"V{BY + BH - R:.0f} A{R} {R} 0 0 1 {BX + BW - R:.0f} {BY + BH:.0f} H{BASE_R:.0f} "
            f"L{TIP[0]:.0f} {TIP[1]:.0f} L{BASE_L:.0f} {BY + BH:.0f} H{BX + R:.0f} "
            f"A{R} {R} 0 0 1 {BX:.0f} {BY + BH - R:.0f} V{BY + R:.0f} A{R} {R} 0 0 1 {BX + R:.0f} {BY:.0f} Z")
    dots = "".join(f'<circle cx="{BX + BW / 2 + dx:.0f}" cy="{BY + BH / 2:.0f}" r="11.5" fill="{K}"/>' for dx in (-40, 0, 40))
    return f'<path d="{path}" fill="{WH}" stroke="{K}" stroke-width="{stroke_w}" stroke-linejoin="round"/>{dots}'


def art(mouth=K):
    mouth_stroke = 0 if mouth == K else 12
    return (f'<path d="{d["body"]}" fill="{Y}" stroke="{K}" stroke-width="15" stroke-linejoin="round"/>'
            f'<path d="{d.get("eyes_smooth", d["eyes"])}" fill="{K}"/>'
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" transform="rotate({ang:.1f} {cx:.1f} {cy:.1f})" '
            f'fill="{mouth}" stroke="{K}" stroke-width="{mouth_stroke}"/>{bubble()}')


LEFT, TOP, RIGHT, BOTTOM = x0 - 28, y0 - 28, x0 + w + 28, y0 + h + 28
SIDE = max(RIGHT - LEFT, BOTTOM - TOP)


def tile(inner, size, bg=P):
    vx = LEFT - (SIDE - (RIGHT - LEFT)) / 2
    vy = TOP - (SIDE - (BOTTOM - TOP)) / 2
    return (f'<svg viewBox="{vx:.0f} {vy:.0f} {SIDE:.0f} {SIDE:.0f}" width="{size}" height="{size}">'
            f'<rect x="{vx:.0f}" y="{vy:.0f}" width="{SIDE:.0f}" height="{SIDE:.0f}" fill="{bg}"/>{inner}</svg>')


W_, H_ = d["size"]
over = (f'<svg viewBox="0 0 {W_} {H_}" width="300"><image href="popcat/ref/classic-crop.png" width="{W_}" height="{H_}"/>'
        f'<g opacity=".62">{art()}</g></svg>')
letters = "".join(f"<span>{c}</span>" for c in "MEMESEEKS")


def lockup(inner, size, zh, en):
    return (f'<div class="lockup">{tile(inner, size)}<div class="name"><div class="zh" style="font-size:{zh}px">迷因捕手</div>'
            f'<div class="en" style="font-size:{en}px">{letters}</div></div></div>')


cards = ""
for mouth, name in ((K, "B2 · 黑嘴"), (RED, "B2 · 红嘴")):
    inner = art(mouth)
    small = "".join(f'<div>{tile(inner, n)}<small>{n}</small></div>' for n in (64, 48, 32, 16))
    cards += (f'<div class="opt"><h2>{name}</h2><div class="row">{tile(inner, 300)}'
              f'<div class="sizes">{small}<div class="dark">{tile(inner, 48, K)}{tile(inner, 24, K)}</div></div></div>'
              f'{lockup(inner, 96, 54, 21)}</div>')

html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Pop 猫标志 · B2</title><style>
body {{ margin: 0; background: {P}; color: {K}; font: 15px/1.6 "Noto Sans SC", sans-serif; padding: 28px 36px; width: 1400px; }}
h1 {{ font: 900 30px "Noto Serif SC", serif; margin: 0 0 4px; }} .lead {{ color: #6E685C; margin: 0 0 18px; max-width: 100ch; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.opt {{ background: #fff; box-shadow: 0 0 0 1px #E2DACA; padding: 20px; }} .opt h2 {{ font: 900 20px "Noto Serif SC", serif; margin: 0 0 12px; }}
.row {{ display: flex; gap: 20px; align-items: flex-end; flex-wrap: wrap; }} .sizes {{ display: flex; gap: 12px; align-items: flex-end; }}
.sizes small {{ display: block; text-align: center; font: 10px Consolas, monospace; color: #6E685C; }}
.dark {{ background: {K}; padding: 8px; display: flex; gap: 8px; align-items: flex-end; }}
.lockup {{ margin-top: 18px; padding-top: 16px; border-top: 1px dashed #CFC6B2; display: flex; gap: 16px; align-items: center; }}
.name {{ display: inline-flex; flex-direction: column; }} .zh {{ font-weight: 900; font-family: "Noto Serif SC", serif; line-height: 1; letter-spacing: .04em; }}
.en {{ display: flex; justify-content: space-between; margin-top: 9px; font-weight: 700; line-height: 1; font-family: "JetBrainsMono Nerd Font", Consolas, monospace; }}
.over {{ display: flex; gap: 18px; align-items: flex-end; margin-bottom: 20px; }} .over small {{ color: #6E685C; }}
</style></head><body><h1>Pop 猫标志 · B2（气泡在嘴里）</h1>
<p class="lead">对话框放大约 12%，尾巴加宽变短，白色部分清楚可见；眼睛在描出的形状上均匀加粗；外形轮廓做了平滑。左边是叠在原图上的检查。</p>
<div class="over">{over}<small>标志半透明叠在经典原图上</small></div>
<div class="grid">{cards}</div></body></html>"""
Path("logos6.html").write_text(html, encoding="utf-8")
print("ok")
