"""Tidy text on another computer, one with a GPU, over ssh: for a library on a computer without one (tidy.py).

The library's library.json holds "tidy_remote": {"host": <an ssh host>, "home": <a folder there>}. That folder
has a Python environment with memeseeks[ml] in .venv, and the model cache in hf-cache. `memeseeks tidy-remote
--host H --home DIR` saves it and runs once; after that every update of the library (`memeseeks add`, or the
server noticing new memes) sends the memes that have no tidied text yet. ssh never asks anything (BatchMode),
so set up a key first. The images are deleted there once their results are back.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shlex
import subprocess
import tarfile
from pathlib import Path

from .index import _atomic_write_text

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30"]
_PROGRESS = re.compile(r"^tidy: (\d+)/(\d+)$")


class RemoteError(RuntimeError):
    pass


class Ssh:
    def __init__(self, host: str):
        if not host or host.startswith("-"):
            raise RemoteError(f"not an ssh host: {host!r}")
        self.host = host

    def run(self, command: str, data: bytes | None = None) -> bytes:
        result = subprocess.run([*SSH, self.host, command], input=data, capture_output=True)
        if result.returncode != 0:
            raise RemoteError(self._why(result.returncode, result.stderr))
        return result.stdout

    def stream(self, command: str, on_line) -> None:
        """Run a command, handing each line it prints to on_line as it comes."""
        proc = subprocess.Popen([*SSH, self.host, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for raw in proc.stdout:
            on_line(raw.decode("utf-8", "replace").strip())
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise RemoteError(self._why(proc.returncode, err))

    def _why(self, code: int, stderr: bytes | None) -> str:
        lines = [l for l in (stderr or b"").decode("utf-8", "replace").splitlines() if l.strip()]
        return f"ssh {self.host}: {lines[-1].strip() if lines else f'exit {code}'}"


def _q(path: str) -> str:
    """A path for the remote shell, quoted, with a leading ~/ still meaning the home folder there."""
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


def _rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return {r["id"]: r for r in rows}


def pending(library) -> dict[str, Path]:
    """Memes with no tidied text or no notes yet. One that failed there has a row and is not sent again."""
    done = set(_rows(library.index_dir / "tidy.jsonl")) & set(_rows(library.index_dir / "notes.jsonl"))
    return {i: Path(p) for i, p in library.paths().items() if i not in done and Path(p).is_file()}


def run(library, cfg: dict, ssh=None, out: Path | None = None, progress=None) -> int:
    """Send what is pending (with `out`: every meme), tidy it there, and add the results to the library's
    index (with `out`: write them there, the library untouched). Returns how many memes came back."""
    ssh = ssh or Ssh(cfg.get("host", ""))
    home = cfg.get("home", "").rstrip("/") or "~"
    if out is None:
        todo = pending(library)
    else:
        todo = {i: Path(p) for i, p in library.paths().items() if Path(p).is_file()}
    if not todo:
        return 0
    if progress:
        progress("tidy", 0, len(todo))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for i, p in todo.items():
            tar.add(str(p), arcname=f"{i}{p.suffix.lower()}")
    # one folder per library, so two computers can share the GPU box
    inbox = _q(f"{home}/tidy_in/{hashlib.sha1(str(library.root.resolve()).encode()).hexdigest()[:12]}")
    ssh.run(f"rm -rf {inbox} && mkdir -p {inbox} && tar -C {inbox} -xf -", buf.getvalue())
    try:
        def on_line(line: str) -> None:
            m = _PROGRESS.match(line)
            if m and progress:
                progress("tidy", int(m.group(1)), len(todo))

        env = f"HF_HOME={_q(home + '/hf-cache')} XDG_CACHE_HOME={_q(home + '/cache')}"
        ssh.stream(f"cd {_q(home)} && {env} {_q(home + '/.venv/bin/python')} -m memeseeks.tidy "
                   f"{inbox} {inbox}/out.jsonl", on_line)
        got = ssh.run(f"cat {inbox}/out.jsonl").decode("utf-8")
    finally:
        try:
            ssh.run(f"rm -rf {inbox}")  # the memes do not stay there
        except RemoteError:
            pass
    rows = [r for r in (json.loads(line) for line in got.splitlines() if line.strip()) if r.get("id") in todo]
    if out is not None:
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return len(rows)
    relpaths = _relpaths(library)
    for name, key in (("tidy.jsonl", "value"), ("notes.jsonl", "notes")):
        merged = _rows(library.index_dir / name)
        for r in rows:
            if key in r:
                merged[r["id"]] = {"id": r["id"], "relpath": relpaths.get(r["id"], todo[r["id"]].name), "value": r[key]}
        _atomic_write_text(library.index_dir / name,
                           "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged.values()))
    return len(rows)


def _relpaths(library) -> dict[str, str]:
    path = library.index_dir / "relpaths.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
