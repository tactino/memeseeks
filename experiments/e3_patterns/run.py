"""E3: can the LLM rewrite snowclone variants into one shared pattern?"""

import json
import os
from pathlib import Path

from experiments.e3_patterns.patterns import CANON_PROMPT, load_items, normalize_pattern, pair_labels
from memeseeks.evalkit import balanced_accuracy
from memeseeks.models.textembed import BgeM3
from memeseeks.models.vlm import QwenVl

OUT = Path(os.environ["MEMESEEKS_RUNS"]) / "e3"
MIN_BALANCED_ACC = 0.85
FIXED_THRESHOLD = 0.85

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    items = load_items(Path("experiments/e3_patterns/snowclones.yaml"))
    vlm = QwenVl()
    patterns = [vlm.chat(CANON_PROMPT.replace("{s}", s), max_new_tokens=80) for s, _ in items]
    pairs = pair_labels(items)
    labels = [same for *_, same in pairs]

    norm = [normalize_pattern(p) for p in patterns]
    exact = balanced_accuracy(labels, [norm[i] == norm[j] for i, j, _ in pairs])

    vecs = BgeM3().embed(patterns)
    sims = [float(vecs[i] @ vecs[j]) for i, j, _ in pairs]
    at_fixed = balanced_accuracy(labels, [s >= FIXED_THRESHOLD for s in sims])
    best_t, best = max(((t / 100, balanced_accuracy(labels, [s >= t / 100 for s in sims]))
                        for t in range(50, 100)), key=lambda x: x[1])

    report = {"n_items": len(items), "n_pairs": len(pairs),
              "exact_match_bal_acc": exact, "embed_bal_acc_at_0.85": at_fixed,
              "embed_best": {"threshold": best_t, "bal_acc": best, "note": "threshold tuned on the test set: optimistic"},
              "passes": max(exact, at_fixed) >= MIN_BALANCED_ACC,
              "limitation": "hand-written dataset of 60 sentences; one LLM (Qwen2.5-VL-7B text mode)",
              "patterns": [{"sentence": s, "group": g, "pattern": p} for (s, g), p in zip(items, patterns)]}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "patterns"}, ensure_ascii=False, indent=2))
