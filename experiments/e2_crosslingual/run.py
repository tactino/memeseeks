"""E2 step 2: text-route AUC (translation vs same-template-different-joke) and base-image AUC."""

import json
import os
from pathlib import Path

from memeseeks.evalkit import auc
from memeseeks.images import load_image
from memeseeks.masking import mask_text
from memeseeks.models.clip import ChineseClip
from memeseeks.models.ocr import RapidOcr
from memeseeks.models.textembed import BgeM3

OUT = Path(os.environ["MEMESEEKS_RUNS"]) / "e2"
TEXT_MIN_AUC = 0.90

if __name__ == "__main__":
    rows = json.loads((OUT / "pairs.json").read_text(encoding="utf-8"))
    bge = BgeM3()
    pos, neg = [], []
    for r in rows:
        en0, en1, en2 = bge.embed(r["captions"])
        zh = bge.embed([r["zh"]])[0]
        pos.append(float(en0 @ zh))
        neg += [float(en0 @ en1), float(en0 @ en2)]
    text_auc = auc(pos, neg)

    ocr, clip = RapidOcr(), ChineseClip()
    full, masked = {}, {}
    for r in rows:
        for name in r["images"]:
            im = load_image(OUT / "images" / name)
            full[name] = clip.embed_images([im])[0]
            masked[name] = clip.embed_images([mask_text(im, [l.box for l in ocr(im)])])[0]
    image_auc = {}
    for label, vecs in (("full", full), ("masked", masked)):
        same = [float(vecs[r["images"][0]] @ vecs[r["images"][1]]) for r in rows]
        diff = [float(vecs[rows[i]["images"][0]] @ vecs[rows[(i + 1) % len(rows)]["images"][1]])
                for i in range(len(rows))]
        image_auc[label] = auc(same, diff)

    report = {"n_templates": len(rows), "text_auc": text_auc, "text_passes": text_auc >= TEXT_MIN_AUC,
              "mean_pos": sum(pos) / len(pos), "mean_neg": sum(neg) / len(neg), "image_auc": image_auc,
              "limitation": "positives are Qwen transcreations, not human 译制; English templates only"}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
