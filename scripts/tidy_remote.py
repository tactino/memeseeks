"""Tidy a library's meme text on the GPU box (src/memeseeks/tidy.py), for a library on a computer without one.

  python scripts/sync.py code                     # the GPU box needs this code first
  python scripts/tidy_remote.py [--lib DIR]       # then: restart memeseeks, and search uses the tidied text
  python scripts/tidy_remote.py --out FILE        # just look: write the results to FILE, leave the library alone

Copies the library's images that have no tidied text yet to ~/$MEMESEEKS_REMOTE/tidy_in on $MEMESEEKS_HOST (the
same settings as remote.sh and sync.py), runs `python -m memeseeks.tidy` there, and adds the results to
<library>/index/tidy.jsonl. Running it again only sends what is new.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from memeseeks.index import _atomic_write_text  # noqa: E402
from memeseeks.library import default_home  # noqa: E402
from scripts.sync import settings  # noqa: E402


def _rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["id"]: r for r in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="tidy a library's meme text on the GPU box")
    ap.add_argument("--lib", type=Path, default=default_home())
    ap.add_argument("--out", type=Path, help="write the results here instead of into the library")
    args = ap.parse_args(argv)
    cfg = settings()
    host, remote = cfg["MEMESEEKS_HOST"], cfg["MEMESEEKS_REMOTE"]
    index = args.lib / "index"
    paths = json.loads((index / "paths.json").read_text(encoding="utf-8"))
    have = {i for i, r in _rows(index / "tidy.jsonl").items() if isinstance(r.get("value"), str)}
    todo = {i: Path(p) for i, p in paths.items() if (args.out or i not in have) and Path(p).is_file()}
    if not todo:
        print("every meme's text is tidied already")
        return 0
    print(f"sending {len(todo)} images to {host}")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for i, p in todo.items():
            tar.add(str(p), arcname=f"{i}{p.suffix.lower()}")
    inbox = f"~/{remote}/tidy_in"
    subprocess.run(["ssh", host, f"rm -rf {inbox} && mkdir -p {inbox} && tar -C {inbox} -xf -"],
                   input=buf.getvalue(), check=True)
    home = f"~/{remote}"  # the same environment as scripts/remote.sh
    run = (f"cd {home}/code && export HF_HOME={home}/hf-cache XDG_CACHE_HOME={home}/cache && source {home}/.venv/bin/activate "
           f"&& python -m memeseeks.tidy {inbox} {inbox}/out.jsonl")
    subprocess.run(["ssh", host, run], check=True)
    got = subprocess.run(["ssh", host, f"cat {inbox}/out.jsonl"], capture_output=True, check=True).stdout.decode("utf-8")
    rows = [json.loads(line) for line in got.splitlines() if line.strip()]
    rows = [r for r in rows if r["id"] in todo]
    for r in rows:
        r["relpath"] = str(todo[r["id"]])
    failed = sum(not isinstance(r["value"], str) for r in rows)
    if args.out:
        args.out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"{len(rows)} results in {args.out} ({failed} failed); the library is unchanged")
        return 0
    merged = _rows(index / "tidy.jsonl")
    merged.update({r["id"]: r for r in rows})
    if (index / "tidy.jsonl").exists():
        shutil.copy(index / "tidy.jsonl", index / "tidy.jsonl.bak")
    _atomic_write_text(index / "tidy.jsonl", "\n".join(json.dumps(r, ensure_ascii=False) for r in merged.values()) + "\n")
    print(f"tidied {len(rows) - failed} memes ({failed} failed) into {index / 'tidy.jsonl'}; "
          "restart memeseeks and search uses the new text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
