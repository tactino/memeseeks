"""Pop Cat logo artwork traced from the classic open-mouth frame, so it overlays the meme itself.

- silhouette: merged cut-outs (popcat/ref/classic-mask.npy), cut below the mouth, traced
- eyes: traced from the photo (the darkest pixels around each eye), lightly smoothed
- mouth: an ellipse fitted to the mouth's outline (the only fitted shape)
All coordinates are those of popcat/ref/classic-crop.png. Writes popcat/classic.json and an overlay check.
"""

import json

import numpy as np
import potrace
from PIL import Image, ImageFilter
from skimage import measure, morphology

crop = Image.open("popcat/ref/classic-crop.png").convert("RGB")
OFFSET = np.array([850, 100])  # where the crop sits in kym-cover.jpg

body = np.load("popcat/ref/classic-mask.npy")
CUT = 600  # keep the head and a short piece of neck
body[CUT:, :] = False
lab = measure.label(body)
body = lab == max(measure.regionprops(lab), key=lambda r: r.area).label
# smooth the outline: blur the mask and re-threshold. Small wiggles go, ears and the jaw line stay.
from scipy import ndimage  # noqa: E402
body = ndimage.gaussian_filter(body.astype(float), 7) > 0.5
body[CUT - 1:, :] = False  # keep the flat cut under the neck crisp

# eyes: blurred dark slits; region-grow from the darkest pixel in a window around each eye
V = np.asarray(crop.filter(ImageFilter.GaussianBlur(1.5)), dtype=float).max(axis=2)


def eye_mask(x, y, wx=48, wy=30, rise=34):
    win = V[y - wy:y + wy, x - wx:x + wx]
    sel = win < win.min() + rise
    lab_ = measure.label(sel)
    iy, ix = np.unravel_index(win.argmin(), win.shape)
    blob = lab_ == lab_[iy, ix]
    blob = morphology.closing(blob, morphology.disk(2))
    out = np.zeros_like(V, bool)
    out[y - wy:y + wy, x - wx:x + wx] = blob
    return out


eyes = eye_mask(299, 190) | eye_mask(505, 153)
# thicker than the photo's squint (same shape, grown evenly) so they still read at small sizes
eyes = ndimage.gaussian_filter(morphology.dilation(eyes, morphology.disk(5)).astype(float), 1.5) > 0.5

# mouth: the ellipse with the same centre and second moments as the (filled) mouth region.
# For a filled ellipse this gives the ellipse itself; it is stable for near-circles, unlike a conic fit.
mm = np.asarray(Image.open("popcat/ref/mouth-mask.png")) > 128
mm = mm[OFFSET[1]:OFFSET[1] + crop.height, OFFSET[0]:OFFSET[0] + crop.width]
ys_, xs_ = np.nonzero(mm)
cx, cy = xs_.mean(), ys_.mean()
evals, evecs = np.linalg.eigh(np.cov(np.stack([xs_, ys_])))
a, b = 2 * np.sqrt(evals[1]), 2 * np.sqrt(evals[0])  # semi-axes: variance along an axis is (semi-axis)^2 / 4
vx, vy = evecs[:, 1]
angle = float(np.degrees(np.arctan2(vy, vx)))  # direction of the long axis, screen coordinates
while angle > 90:
    angle -= 180
while angle < -90:
    angle += 180


def trace(mask, turd=20, smooth=1.1):
    bm = potrace.Bitmap(Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)))
    parts = []
    for curve in bm.trace(turdsize=turd, alphamax=smooth, opticurve=True, opttolerance=0.3):
        s = curve.start_point
        d = [f"M{s.x:.1f} {s.y:.1f}"]
        for sg in curve.segments:
            if sg.is_corner:
                d.append(f"L{sg.c.x:.1f} {sg.c.y:.1f}L{sg.end_point.x:.1f} {sg.end_point.y:.1f}")
            else:
                d.append(f"C{sg.c1.x:.1f} {sg.c1.y:.1f} {sg.c2.x:.1f} {sg.c2.y:.1f} "
                         f"{sg.end_point.x:.1f} {sg.end_point.y:.1f}")
        parts.append("".join(d) + "Z")
    return " ".join(parts)


rows, cols = np.nonzero(body)
out = {"size": [crop.width, crop.height],
       "box": [int(cols.min()), int(rows.min()), int(cols.max() - cols.min()), int(rows.max() - rows.min())],
       "body": trace(body, smooth=1.3), "eyes": trace(eyes, turd=5, smooth=1.0),
       "mouth": {"cx": float(cx), "cy": float(cy), "rx": float(a), "ry": float(b), "angle": angle}}
json.dump(out, open("popcat/classic.json", "w"))
np.save("popcat/classic-eyes.npy", eyes)
np.save("popcat/classic-body.npy", body)
print(f"mouth ellipse centre ({cx:.0f},{cy:.0f}) rx {a:.0f} ry {b:.0f} angle {angle:.1f}; "
      f"eye pixels {int(eyes.sum())}; body box {out['box']}")
