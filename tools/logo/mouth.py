"""Measure the classic Pop Cat O mouth on the reference frame, relative to the eyes.

Output: popcat/mouth.json with the mouth outline in "eye coordinates": origin at the midpoint of the
eyes, x axis along the eye line, unit = distance between the eyes. That makes it transferable to
our traced cat (same animal, similar pose) by matching the eyes.
"""

import json

import numpy as np
from PIL import Image, ImageFilter
from skimage import measure, morphology

im = Image.open("popcat/ref/kym-cover.jpg").convert("RGB")
rgb = np.asarray(im.filter(ImageFilter.GaussianBlur(2)), dtype=float)
R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
V = rgb.max(axis=2)
H, W = V.shape

# right panel only (the open-mouth frame)
panel = np.zeros((H, W), bool)
panel[:, W // 2:] = True

# eyes: blurred dark-brown blobs; take the darkest pixels in a window around each eye (found by eye)
def eye_centre(x, y, wx=40, wy=26):
    win = V[y - wy:y + wy, x - wx:x + wx]
    sel = win < win.min() + 22
    ys_, xs_ = np.nonzero(sel)
    return x - wx + xs_.mean(), y - wy + ys_.mean()


lx, ly = eye_centre(1155, 285)
rx, ry = eye_centre(1350, 250)
print("reference eyes", (round(lx), round(ly)), (round(rx), round(ry)))

# mouth: the big reddish / dark opening below the eyes
mouth_box = np.zeros_like(panel)
mouth_box[260:640, 1080:1500] = True
reddish = (R - G > 38) & (R > 90)
shadow = (V < 95) & (R >= G)
mouth = (reddish | shadow) & mouth_box
mouth = morphology.binary_closing(mouth, morphology.disk(9))
lab = measure.label(mouth)
region = max(measure.regionprops(lab), key=lambda r: r.area)
mouth = morphology.remove_small_holes(lab == region.label, 20000)
mouth = morphology.binary_opening(mouth, morphology.disk(7))
contour = max(measure.find_contours(mouth.astype(float), 0.5), key=len)  # (row, col) points
Image.fromarray((mouth * 255).astype(np.uint8)).save("popcat/ref/mouth-mask.png")

# express the outline in eye coordinates
mid = np.array([(lx + rx) / 2, (ly + ry) / 2])
axis = np.array([rx - lx, ry - ly])
unit = np.linalg.norm(axis)
ex = axis / unit
ey = np.array([-ex[1], ex[0]])  # perpendicular, pointing down the face
pts = np.stack([contour[:, 1], contour[:, 0]], axis=1) - mid
eye_coords = np.stack([pts @ ex, pts @ ey], axis=1) / unit
json.dump({"outline": eye_coords[::3].round(4).tolist()}, open("popcat/mouth.json", "w"))
w = eye_coords[:, 0].max() - eye_coords[:, 0].min()
h = eye_coords[:, 1].max() - eye_coords[:, 1].min()
print(f"mouth size in eye distances: {w:.2f} wide x {h:.2f} tall; "
      f"top edge {eye_coords[:, 1].min():.2f}, centre x {eye_coords[:, 0].mean():.2f}")
