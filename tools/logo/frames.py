"""Loading animation frames from the maintainer's two-panel Pop Cat (left: mouth closed, right: open).

Both frames are traced the same way as the logo (silhouette smoothed, features traced, eyes thickened)
and the open frame is aligned to the closed one by the eyes, so the head does not jump when they swap.
Coordinates: the left crop at 2x (popcat/crop-left-2x.png). Writes popcat/frames.json.
"""

import json

import numpy as np
import potrace
from PIL import Image, ImageFilter
from scipy import ndimage
from skimage import measure, morphology, transform

# 2x full-image coordinates of each crop's top-left corner, and the eyes found on the source image
OFF = {"L": np.array([80, 540]), "R": np.array([1120, 540])}
EYES = {"L": np.array([[505.2, 772.6], [692.8, 758.8]]), "R": np.array([[1499.6, 794.4], [1703.8, 766.4]])}
CUT = 690  # in left-crop coordinates: head and a short piece of neck


def load(side):
    cut = Image.open(f"popcat/cut-{'left' if side == 'L' else 'u2net'}{'-u2net' if side == 'L' else ''}.png")
    img = Image.open(f"popcat/crop-{'left' if side == 'L' else 'right'}-2x.png").convert("RGB")
    a = np.asarray(cut.getchannel("A"))
    rows = np.arange(a.shape[0])[:, None]
    # strict near the top (drops the faint background band between the ears), normal below
    body = (a > 200) | ((a > 100) & (rows > 250))
    body = morphology.opening(body, morphology.disk(9))
    lab = measure.label(body)
    body = lab == max(measure.regionprops(lab), key=lambda r: r.area).label
    body = morphology.remove_small_holes(body, max_size=8000)
    gray = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(2)), dtype=float)
    rgb = np.asarray(img.filter(ImageFilter.GaussianBlur(2)), dtype=float)
    return body, gray, rgb


def region(mask_fn, near, r):
    """The connected blob of mask_fn closest to `near` (x, y), searched within radius r."""
    ys, xs = np.mgrid[0:900, 0:900]
    m = mask_fn & ((xs - near[0]) ** 2 + (ys - near[1]) ** 2 < r * r)
    lab = measure.label(m)
    if lab.max() == 0:
        return np.zeros_like(m)
    best = min(measure.regionprops(lab), key=lambda p: np.hypot(p.centroid[1] - near[0], p.centroid[0] - near[1]))
    return lab == best.label


def features(side):
    body, gray, rgb = load(side)
    eyes_c = EYES[side] - OFF[side]
    inner = morphology.erosion(body, morphology.disk(8))
    eyes = np.zeros_like(body)
    for ex, ey in eyes_c:
        win = gray[int(ey) - 22:int(ey) + 22, int(ex) - 30:int(ex) + 30]
        eyes |= region((gray < win.min() + 40) & inner, (ex, ey), 32)
    eyes = ndimage.gaussian_filter(morphology.dilation(eyes, morphology.disk(7)).astype(float), 2) > 0.5
    mid = eyes_c.mean(axis=0)
    dist = np.linalg.norm(eyes_c[1] - eyes_c[0])
    R_, G_, B_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    pink = R_ - (G_ + B_) / 2  # how much redder than the fur around it
    c = mid + [0.25 * dist, 0.42 * dist]
    ys, xs = np.mgrid[0:900, 0:900]
    win = ((xs - c[0]) ** 2 + (ys - c[1]) ** 2 < (0.3 * dist) ** 2) & inner
    vals = pink[win]
    thr = vals.max() - 0.45 * (vals.max() - np.median(vals))  # adaptive: close to the reddest pixel only
    iy, ix = np.unravel_index(np.where(win, pink, -1e9).argmax(), pink.shape)
    nose = region((pink > thr) & win, (ix, iy), 0.3 * dist)
    nose = ndimage.binary_fill_holes(morphology.closing(nose, morphology.disk(6)))  # the pink nose, solid
    nose = ndimage.gaussian_filter(nose.astype(float), 2) > 0.5
    below = mid + [0.25 * dist, 0.78 * dist]
    if side == "L":
        # closed: only the darkest thin line under the nose, redrawn at an even stroke along its skeleton
        win = gray[int(below[1]) - 50:int(below[1]) + 50, int(below[0]) - 70:int(below[0]) + 70]
        line = region((gray < win.min() + 18) & inner & ~morphology.dilation(nose, morphology.disk(4)), below, 0.55 * dist)
        mouth = morphology.dilation(morphology.skeletonize(line), morphology.disk(5))
    else:
        # open: the dark opening itself, filled and smoothed
        mouth = region((gray < 95) & inner, below, 0.6 * dist)
        mouth = ndimage.binary_fill_holes(morphology.closing(mouth, morphology.disk(8)))
        mouth = morphology.opening(mouth, morphology.disk(12))  # drops the thin stalk up to the nose
        lab_ = measure.label(mouth)
        if lab_.max():
            mouth = lab_ == max(measure.regionprops(lab_), key=lambda r_: r_.area).label
    mouth = ndimage.gaussian_filter(mouth.astype(float), 2.5 if side == "L" else 9) > 0.45
    mouth &= ~morphology.dilation(nose, morphology.disk(9))  # a clear gap between nose and mouth
    return body, eyes, nose, mouth


def to_left(mask):
    """Warp a right-frame mask into left-frame coordinates by matching the eyes (similarity transform)."""
    t = transform.SimilarityTransform()
    t.estimate(EYES["L"], EYES["R"])  # maps left full coords -> right full coords (what warp needs)

    def inverse_map(coords):  # coords: (col, row) in left-crop space
        full_left = coords + OFF["L"]
        return t(full_left) - OFF["R"]

    return transform.warp(mask.astype(float), inverse_map, output_shape=mask.shape, order=1) > 0.5


def trace(mask, turd=10, smooth=1.2):
    bm = potrace.Bitmap(Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)))
    parts = []
    for curve in bm.trace(turdsize=turd, alphamax=smooth, opticurve=True, opttolerance=0.3):
        s = curve.start_point
        d = [f"M{s.x:.1f} {s.y:.1f}"]
        for sg in curve.segments:
            if sg.is_corner:
                d.append(f"L{sg.c.x:.1f} {sg.c.y:.1f}L{sg.end_point.x:.1f} {sg.end_point.y:.1f}")
            else:
                d.append(f"C{sg.c1.x:.1f} {sg.c1.y:.1f} {sg.c2.x:.1f} {sg.c2.y:.1f} {sg.end_point.x:.1f} {sg.end_point.y:.1f}")
        parts.append("".join(d) + "Z")
    return " ".join(parts)


if __name__ == "__main__":
    out = {}
    shared = None  # both frames use the closed frame's silhouette: same video, same pose, so the head never jumps
    for side, name in (("L", "closed"), ("R", "open")):
        parts = features(side)
        if side == "R":
            parts = tuple(to_left(m) for m in parts)
        body, eyes, nose, mouth = parts
        if shared is None:
            body = morphology.opening(body, morphology.disk(5)).copy()
            body[CUT:, :] = False
            body = ndimage.gaussian_filter(body.astype(float), 5) > 0.5
            body[CUT - 1:, :] = False
            shared = body
        body = shared
        out[name] = {"body": trace(body, 30, 1.3), "eyes": trace(eyes), "nose": trace(nose, 4), "mouth": trace(mouth, 6)}
        Image.fromarray((body * 190 + (eyes | nose | mouth) * 65).astype(np.uint8)).save(f"popcat/frame-{name}.png")
        rows, cols = np.nonzero(body)
        out[name]["box"] = [int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())]
        print(name, "box", out[name]["box"], "eye/nose/mouth px", int(eyes.sum()), int(nose.sum()), int(mouth.sum()))
    json.dump(out, open("popcat/frames.json", "w"))
