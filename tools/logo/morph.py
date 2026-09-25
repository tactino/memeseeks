"""Pop Cat loader v2: closed mouth <-> logo, a continuous morph played forward and back.

Features keep their traced shapes: each contour is resampled and low-pass filtered (Fourier), which
removes the jaggies but not the character of the shape. Every shape is written as a closed cubic
Bezier through the same number of points, so the browser can interpolate between the two states.
Frame 1 comes from the maintainer's two-panel Pop Cat (left panel), placed in the logo's head by the
ear tips; the end state is the logo. Writes loader2.svg, morph-keys.html and adds "eyes_smooth" to
popcat/classic.json so the static logo uses exactly the animation's final eyes.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from skimage import measure, transform

sys.path.insert(0, str(Path(__file__).resolve().parent))  # frames.py, next to this file
import frames  # noqa: E402

N = 64  # points per shape
logo = json.load(open("popcat/classic.json"))
logo_body = np.load("popcat/classic-body.npy")
logo_eyes = np.load("popcat/classic-eyes.npy")


def ear_tips(body):
    rows, cols = np.nonzero(body)
    x0, x1 = cols.min(), cols.max()
    tips = []
    for lo, hi in ((x0, x0 + (x1 - x0) * 0.35), (x0 + (x1 - x0) * 0.65, x1)):
        sel = (cols >= lo) & (cols <= hi)
        top = rows[sel].min()
        tips.append((cols[sel][rows[sel] <= top + 3].mean(), top))
    return np.array(tips, dtype=float)


def contour(mask):
    """Outer contour of a blob as (x, y) points, counter-clockwise on screen, from its leftmost point."""
    c = max(measure.find_contours(np.pad(mask, 2).astype(float), 0.5), key=len)[:, ::-1] - 2
    area = 0.5 * np.sum(c[:-1, 0] * c[1:, 1] - c[1:, 0] * c[:-1, 1])
    if area > 0:  # screen y points down: make the traversal counter-clockwise as seen
        c = c[::-1]
    return c


def resample(pts, n=N, keep=None):
    """n points evenly spaced along the closed outline, optionally low-passed to `keep` harmonics."""
    closed = np.vstack([pts, pts[:1]])
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))]
    t = np.linspace(0, seg[-1], 512, endpoint=False)
    z = np.interp(t, seg, closed[:, 0]) + 1j * np.interp(t, seg, closed[:, 1])
    if keep:
        f = np.fft.fft(z)
        f[keep + 1:-keep] = 0
        z = np.fft.ifft(f)
    idx = np.linspace(0, len(z), n, endpoint=False).astype(int)
    out = np.stack([z.real, z.imag], axis=1)[idx]
    start = int(np.argmin(out[:, 0]))  # leftmost point first, so shapes correspond when morphing
    return np.roll(out, -start, axis=0)


def blobs(mask, k):
    lab = measure.label(mask)
    regs = sorted(measure.regionprops(lab), key=lambda r: -r.area)[:k]
    return [lab == r.label for r in sorted(regs, key=lambda r: r.centroid[1])]  # left to right


def bezier(pts):
    """Closed Catmull-Rom spline through pts as cubic Beziers (same command list for every shape of size N)."""
    n = len(pts)
    d = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1, c2 = p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6
        d.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return "".join(d) + "Z"


# ---- frame 1 (closed mouth), in the logo's coordinates ----
body1, eyes1, nose1, mouth1 = frames.features("L")
t = transform.SimilarityTransform()
t.estimate(ear_tips(body1), ear_tips(logo_body))
soft = lambda m, s: ndimage.gaussian_filter(m.astype(float), s) > 0.5  # noqa: E731
f1 = {
    "eyes": [t(resample(contour(soft(e, 2)), keep=6)) for e in blobs(eyes1, 2)],
    "nose": t(resample(contour(soft(nose1, 2)), keep=6)),
    "mouth": t(resample(contour(soft(mouth1, 1.5)), keep=9)),
}

# ---- end state: the logo ----
m = logo["mouth"]
a = np.linspace(0, 2 * np.pi, 512, endpoint=False)
ca, sa = np.cos(np.radians(m["angle"])), np.sin(np.radians(m["angle"]))
ex, ey = m["rx"] * np.cos(a), m["ry"] * np.sin(a)
ellipse = np.stack([m["cx"] + ex * ca - ey * sa, m["cy"] + ex * sa + ey * ca], axis=1)
f3 = {
    "eyes": [resample(contour(soft(e, 1.5)), keep=16) for e in blobs(logo_eyes, 2)],
    "mouth": resample(contour_pts := ellipse[::-1] if 0 else ellipse),
}
f3["mouth"] = resample(ellipse if 0.5 * np.sum(ellipse[:-1, 0] * ellipse[1:, 1] - ellipse[1:, 0] * ellipse[:-1, 1]) < 0
                       else ellipse[::-1])
# the nose is pushed up by the opening mouth and shrinks as it goes: it ends just inside the O's
# upper lip, above where it started, where the mouth (drawn on top) swallows it
nc = f1["nose"].mean(axis=0)
lip_top = ellipse[np.argmin(np.abs(ellipse[:, 0] - nc[0]) + 1e3 * (ellipse[:, 1] > m["cy"])), 1]  # the O's top edge at the nose's x
target = np.array([nc[0], min(lip_top + 22, nc[1] - 25)])
f3["nose"] = (f1["nose"] - nc) * 0.12 + target
print(f"nose: from y={nc[1]:.0f} up to y={target[1]:.0f} (O's top edge there: {lip_top:.0f})")

paths = {k: {"eyes": [bezier(e) for e in v["eyes"]], "nose": bezier(v["nose"]), "mouth": bezier(v["mouth"])}
         for k, v in (("closed", f1), ("logo", f3))}
logo["eyes_smooth"] = " ".join(paths["logo"]["eyes"])
json.dump(logo, open("popcat/classic.json", "w"))
json.dump(paths, open("popcat/morph.json", "w"))

# ---------------- drawing ----------------
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("b6", Path(__file__).resolve().parent / "build6.py")
b6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b6)
K, Y = "#161411", "#FFD21F"
VB = (f"{b6.LEFT - (b6.SIDE - (b6.RIGHT - b6.LEFT)) / 2:.0f} {b6.TOP - (b6.SIDE - (b6.BOTTOM - b6.TOP)) / 2:.0f} "
      f"{b6.SIDE:.0f} {b6.SIDE:.0f}")
MC = (m["cx"], m["cy"])
BODY = f'<path d="{logo["body"]}" fill="{Y}" stroke="{K}" stroke-width="15" stroke-linejoin="round"/>'

NOSE_VANISH = ('<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" '
               'keyTimes="0;0.312;0.828" values="1;0;1"/>')  # gone once small, back at the same size
# ping-pong: hold closed, morph to the logo, bubble pops, hold, bubble shrinks, morph back (the same path reversed)
DUR = 3.2
KT = "0;0.14;0.44;0.70;1"
EASE = "0.42 0 0.58 1"  # symmetric, so the way back is the exact reverse
SPL = ";".join([EASE] * 4)


def morph(key, i=None):
    get = (lambda s: paths[s][key][i]) if i is not None else (lambda s: paths[s][key])
    vals = ";".join(get(s) for s in ("closed", "closed", "logo", "logo", "closed"))
    return (f'<path d="{get("closed")}" fill="{K}"><animate attributeName="d" dur="{DUR}s" repeatCount="indefinite" '
            f'calcMode="spline" keyTimes="{KT}" keySplines="{SPL}" values="{vals}"/>')


nose_fade = (f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="spline" '
             f'keyTimes="{KT}" keySplines="{SPL}" values="1;1;0;0;1"/>')
BUBBLE_T = "0;0.44;0.49;0.52;0.64;0.70;1"
BUBBLE_V = "0;0;1.12;1;1;0;0"
bubble = (f'<g transform="translate({MC[0]:.1f} {MC[1]:.1f})"><g><animateTransform attributeName="transform" type="scale" '
          f'dur="{DUR}s" repeatCount="indefinite" keyTimes="{BUBBLE_T}" values="{BUBBLE_V}"/>'
          f'<g transform="translate({-MC[0]:.1f} {-MC[1]:.1f})">{b6.bubble()}</g></g></g>')
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VB}" width="240" height="240">{BODY}'
       + morph("eyes", 0) + "</path>" + morph("eyes", 1) + "</path>"
       + morph("nose") + NOSE_VANISH + "</path>" + morph("mouth") + "</path>" + bubble + "</svg>")
Path("loader2.svg").write_text(svg, encoding="utf-8")


def static(state, size):
    p = paths[state]
    return (f'<svg viewBox="{VB}" width="{size}" height="{size}">{BODY}'
            + "".join(f'<path d="{e}" fill="{K}"/>' for e in p["eyes"])
            + (f'<path d="{p["nose"]}" fill="{K}"/>' if state == "closed" else "")
            + f'<path d="{p["mouth"]}" fill="{K}"/>' + (b6.bubble() if state == "logo" else "") + "</svg>")


Path("popcat/morph-inline.json").write_text(json.dumps({
    "vb": VB, "body": logo["body"], "closed": static("closed", 96), "logo": static("logo", 96),
    "paths": paths, "bubble": b6.bubble(), "mouth_c": MC}), encoding="utf-8")
html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
body {{ margin: 0; background: #F3EFE4; font: 13px "Noto Sans SC", sans-serif; padding: 20px; width: 900px; color: {K}; }}
.row {{ display: flex; gap: 22px; align-items: flex-end; }} figure {{ margin: 0; text-align: center; }} figcaption {{ color: #6E685C; }}
</style></head><body><div class="row">
<figure>{static("closed", 220)}<figcaption>① 闭嘴（五官按描出的形状平滑）</figcaption></figure>
<figure>{static("logo", 220)}<figcaption>② 标志</figcaption></figure>
<figure><img src="loader2.svg" width="220"><figcaption>连续动图（正放、倒放循环）</figcaption></figure>
</div></body></html>"""
Path("morph-keys.html").write_text(html, encoding="utf-8")
print("ok; points per shape", N)
