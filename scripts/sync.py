"""Move code or private data between this machine and the GPU box over ssh.

  python scripts/sync.py code       # working tree -> ~/$MEMESEEKS_REMOTE/code (replaced atomically)
  python scripts/sync.py data       # $MEMESEEKS_LOCAL_DATA -> ~/$MEMESEEKS_REMOTE/data
  python scripts/sync.py pull-runs  # ~/$MEMESEEKS_REMOTE/runs -> $MEMESEEKS_LOCAL_DATA/runs

Settings come from the environment or the gitignored .memeseeks-dev.env (see the .example file).

Streams a PAX tar so Chinese file names survive; nothing is written to disk in between.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEV_ENV = REPO / ".memeseeks-dev.env"  # gitignored; see .memeseeks-dev.env.example
CODE_EXCLUDES = {".git", ".venv", "__pycache__", ".pytest_cache", ".superpowers", "data", "runs"}
DATA_EXCLUDES = {"runs"}
LOCAL_ONLY = {".memeseeks-dev.env", ".env"}  # hold hosts and the serve token: never copied anywhere


def load_dev_env(path: Path) -> dict[str, str]:
    """KEY=VALUE lines from the dev env file, overridden by real environment variables."""
    cfg: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                value = re.split(r"\s+#", value, maxsplit=1)[0].strip().strip('"').strip("'")
                cfg[key.strip()] = value  # same result as bash sourcing the file (remote.sh)
    cfg.update({k: v for k, v in os.environ.items() if k.startswith("MEMESEEKS_")})
    return cfg


def settings(path: Path = DEV_ENV, need_data: bool = False) -> dict[str, str]:
    cfg = load_dev_env(path)
    needed = ["MEMESEEKS_HOST", "MEMESEEKS_REMOTE"] + (["MEMESEEKS_LOCAL_DATA"] if need_data else [])
    missing = [k for k in needed if not cfg.get(k)]
    if missing:
        sys.exit(f"set {', '.join(missing)} in {path.name} (copy .memeseeks-dev.env.example) or the environment")
    check_remote(cfg["MEMESEEKS_REMOTE"])
    return cfg


def check_remote(remote: str) -> str:
    """The remote dir is rm -rf'ed piecewise, so it must be a plain relative path ending in 'memeseeks'."""
    parts = remote.split("/")
    unsafe = (not re.fullmatch(r"[A-Za-z0-9_./-]+", remote or "") or remote.startswith("/")
              or parts[-1] != "memeseeks" or any(part in ("", ".", "..") for part in parts))
    if unsafe:
        sys.exit(f"refusing unsafe MEMESEEKS_REMOTE={remote!r}: need a relative path like work/memeseeks")
    return remote


def check_source(root: Path) -> None:
    """Pushing replaces the remote copy, so an empty or missing source would wipe it."""
    if not root.is_dir() or not any(root.iterdir()):
        sys.exit(f"refusing to push {root}: missing or empty")


def iter_files(root: Path, exclude_dirs: set[str]):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in exclude_dirs and not d.endswith(".egg-info"))
        for name in sorted(f for f in filenames if f not in LOCAL_ONLY):  # local settings stay local
            path = Path(dirpath, name)
            yield path, path.relative_to(root).as_posix()


def write_tar(stream, root: Path, exclude_dirs: set[str]) -> int:
    count = 0
    with tarfile.open(fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT, encoding="utf-8") as tar:
        for path, rel in iter_files(root, exclude_dirs):
            tar.add(path, arcname=rel, recursive=False)
            count += 1
    return count


def push(host: str, root: Path, dest: str, exclude_dirs: set[str]) -> None:
    check_source(root)
    cmd = f"rm -rf {dest}.new && mkdir -p {dest}.new && tar -xf - -C {dest}.new && rm -rf {dest} && mv {dest}.new {dest}"
    proc = subprocess.Popen(["ssh", host, cmd], stdin=subprocess.PIPE)
    count = write_tar(proc.stdin, root, exclude_dirs)
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit(f"remote extract into {dest} failed")
    print(f"pushed {count} files to {host}:~/{dest}")


def pull_runs(host: str, remote: str, data: Path) -> None:
    target = data / "runs"
    target.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["ssh", host, f"tar -cf - -C {remote} runs"], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
        tar.extractall(data, filter="data")
    if proc.wait() != 0:
        sys.exit("remote tar of runs failed")
    print(f"pulled runs into {target}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what not in ("code", "data", "pull-runs"):
        sys.exit(__doc__)
    cfg = settings(need_data=what != "code")
    host, remote = cfg["MEMESEEKS_HOST"], cfg["MEMESEEKS_REMOTE"]
    if what == "code":
        push(host, REPO, f"{remote}/code", CODE_EXCLUDES)
    elif what == "data":
        push(host, Path(cfg["MEMESEEKS_LOCAL_DATA"]), f"{remote}/data", DATA_EXCLUDES)
    else:
        pull_runs(host, remote, Path(cfg["MEMESEEKS_LOCAL_DATA"]))
