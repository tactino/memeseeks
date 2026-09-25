# The Pop Cat logo pipeline

These scripts produce the cat's shapes (`src/memeseeks/web/popcat.js`) and the icons. They are for
maintainers; the web app only needs the generated files.

The source pictures are **not** in the repository: they are photos of a real cat, and only the shapes
traced from them (redrawn as smooth vector outlines) are used. To rebuild, make a working folder with a
`popcat/` subfolder holding:

- `popcat/ref/kym-cover.jpg`: the classic two-frame Pop Cat image (closed and open mouth), 1600×900;
  `popcat/ref/classic-crop.png` is its open-mouth frame cropped at (850, 100, 1550, 900).
- `popcat/source.png`: the two-panel "unedited Pop Cat" meme, 1024×848, cropped at 2× into
  `crop-left-2x.png` (40, 270, 490, 720) and `crop-right-2x.png` (560, 270, 1010, 720).
- Cut-outs made with [rembg](https://github.com/danielgatis/rembg): `cut-left-u2net.png`, `cut-u2net.png`
  (u2net), and for the classic frame the union of u2net, isnet-general-use and SAM (point prompts on the
  cat) saved as `ref/classic-mask.npy`.

Then, from the working folder (Python with numpy, scipy, scikit-image, pillow, potracer, resvg-py):

```bash
python <repo>/tools/logo/mouth.py     # measure the classic O mouth relative to the eyes
python <repo>/tools/logo/classic.py   # silhouette and eyes from the classic frame; the mouth as an ellipse
python <repo>/tools/logo/morph.py     # the closed-mouth state from the two-panel meme, and the morphable shapes
python <repo>/tools/logo/export.py <repo>   # popcat.js, icons/*, memeseeks.ico
```

`build6.py` draws the logo itself (the silhouette, the eyes, the mouth and the bubble inside it).
