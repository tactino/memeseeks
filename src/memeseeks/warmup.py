"""Getting the models ready while the web app is already up (docs/design.md, "First run").

On the first run this downloads them, about 3.9 GB, so the server listens at once and the page shows how
far the download has got; search waits, everything else works. The indexer starts once the models are in.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from .search import EmptyLibrary

# What the default models load from the Hugging Face Hub (their main branch), in bytes.
EXPECTED = {"BAAI/bge-m3": 2_293_331_623, "OFA-Sys/chinese-clip-vit-large-patch14-336px": 1_626_539_027}
MIRROR_HINT = "连不上 Hugging Face。在国内可以先设置环境变量 HF_ENDPOINT=https://hf-mirror.com，再重新启动迷因捕手。"


def hub_cache() -> Path:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return Path(HF_HUB_CACHE)
    except ImportError:  # the ml extra is not installed: nothing will download anyway
        return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def downloaded_bytes(cache: Path, repos=EXPECTED) -> int:
    """Bytes of these models in the cache so far, a download under way included. Symlinked snapshots
    point at blobs and are skipped; without symlinks (Windows) the snapshot files are the real ones."""
    total = 0
    for repo in repos:
        root = Path(cache) / ("models--" + repo.replace("/", "--"))
        for sub in ("blobs", "snapshots"):
            if not (root / sub).is_dir():
                continue
            for p in (root / sub).rglob("*"):
                try:
                    if not p.is_symlink() and p.is_file():
                        total += p.stat().st_size
                except OSError:
                    pass
    return total


def _unreachable(exc: BaseException) -> bool:
    text = str(exc).lower()
    return isinstance(exc, (ConnectionError, TimeoutError)) or "connect" in text or "huggingface.co" in text


class Warmup:
    def __init__(self, service, names=("bge", "clip", "ocr"), then=None, cache=None, expected: int | None = None):
        self.service, self.names, self.then = service, names, then
        self.cache = Path(cache) if cache is not None else hub_cache()
        self.expected = sum(EXPECTED.values()) if expected is None else expected
        # a first run: the models are not (all) there yet
        self.downloading = downloaded_bytes(self.cache) < self.expected * 0.98
        self._state, self._error = "loading", None
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        try:
            for name in self.names:
                self.service.models.get(name)
            try:
                self.service.warm()  # the index, and a first query through the models
            except EmptyLibrary:
                pass  # nothing to search yet; the models are loaded all the same
        except Exception as exc:  # keep serving: the page says what went wrong
            message = f"{type(exc).__name__}: {exc}"
            if _unreachable(exc) and not os.environ.get("HF_ENDPOINT"):
                message = f"{MIRROR_HINT}（{message}）"
            self._state, self._error = "error", message
            return
        self._state = "ready"
        if self.then is not None:
            self.then()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="memeseeks-warmup", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def status(self) -> dict:
        download = None
        if self._state == "loading" and self.downloading:
            download = {"done": downloaded_bytes(self.cache), "total": self.expected}
        return {"state": self._state, "download": download, "error": self._error}
