"""E3 fallback (spec §7): few-shot prompt vs zero-shot vs raw sentences, with held-out thresholds."""

import json
import os
from pathlib import Path

from experiments.e3_patterns.patterns import FEWSHOT_PROMPT, heldout_bal_acc, load_items, normalize_pattern, pair_labels
from memeseeks.evalkit import balanced_accuracy
from memeseeks.models.textembed import BgeM3
from memeseeks.models.vlm import QwenVl

OUT = Path(os.environ["MEMESEEKS_RUNS"]) / "e3"

if __name__ == "__main__":
    items = load_items(Path("experiments/e3_patterns/snowclones.yaml"))
    pairs = pair_labels(items)
    labels = [same for *_, same in pairs]
    zero_shot = [p["pattern"] for p in json.loads((OUT / "report.json").read_text(encoding="utf-8"))["patterns"]]
    vlm = QwenVl()
    few_shot = [vlm.chat(FEWSHOT_PROMPT.replace("{s}", s), max_new_tokens=80).split("\n")[0].strip() for s, _ in items]
    bge = BgeM3()
    results = {}
    for name, texts in (("raw_sentence", [s for s, _ in items]), ("zero_shot", zero_shot), ("few_shot", few_shot)):
        vecs = bge.embed(texts)
        sims = [float(vecs[i] @ vecs[j]) for i, j, _ in pairs]
        norm = [normalize_pattern(t) for t in texts]
        results[name] = {
            "exact_match": balanced_accuracy(labels, [norm[i] == norm[j] for i, j, _ in pairs]),
            "embed_at_0.85": balanced_accuracy(labels, [s >= 0.85 for s in sims]),
            "embed_heldout_threshold": heldout_bal_acc(items, pairs, sims),
        }
    report = {"results": results,
              "few_shot_patterns": [{"sentence": s, "group": g, "pattern": p} for (s, g), p in zip(items, few_shot)]}
    (OUT / "report_fallback.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    for (s, g), p in zip(items, few_shot):
        print(g, "|", s, "=>", p)
