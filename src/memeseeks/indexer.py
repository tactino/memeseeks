"""Keeps the index up to date while the server runs: new files in any source folder get indexed.

It polls the source folders (no extra dependency) and waits a few seconds after the last change, so
a batch of saves becomes one run. On Windows the process drops to below-normal priority while it
indexes, so the rest of the computer stays responsive.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from pathlib import Path

from .images import IMAGE_EXTS


@contextlib.contextmanager
def below_normal_priority():
    if sys.platform != "win32":
        yield
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    process = kernel32.GetCurrentProcess()
    kernel32.SetPriorityClass(process, 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS
    try:
        yield
    finally:
        kernel32.SetPriorityClass(process, 0x20)  # NORMAL_PRIORITY_CLASS


def folder_signature(folder: str | Path) -> tuple[int, int, int]:
    """(image count, total bytes, newest mtime): changes whenever an image is added, replaced or removed."""
    count = size = newest = 0
    stack = [str(folder)]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                    st = entry.stat()
                    count, size, newest = count + 1, size + st.st_size, max(newest, st.st_mtime_ns)
            except OSError:
                continue
    return count, size, newest


class BackgroundIndexer:
    def __init__(self, library, models, poll_seconds: float = 20.0, debounce: float = 3.0,
                 clock=time.monotonic, priority=below_normal_priority):
        self.library, self.models = library, models
        self.poll_seconds, self.debounce, self.clock, self.priority = poll_seconds, debounce, clock, priority
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._signature = None
        self._pending_since: float | None = None
        self._state = {"running": False, "last_error": None, "last_images": None, "progress": None}

    def request(self) -> None:
        """Index soon: after `debounce` seconds without another request."""
        with self._lock:
            self._pending_since = self.clock()
        self._wake.set()

    def signature(self):
        return tuple((s, folder_signature(s)) for s in self.library.config()["sources"])

    def tick(self) -> bool:
        """Check the folders once and run an update if one is due; returns whether it ran."""
        sig = self.signature()
        if self._signature is not None and sig != self._signature:
            self.request()
        self._signature = sig
        with self._lock:
            due = self._pending_since is not None and self.clock() - self._pending_since >= self.debounce
            if due:
                self._pending_since = None
                self._state["running"] = True
        if not due:
            return False
        try:
            with self.priority():
                report = self.library.update(self.models, log=lambda message: None, progress=self._progress)
            self._state.update(last_error=None, last_images=report["images"])
        except Exception as exc:  # keep serving; the next change retries
            self._state["last_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            self._state["running"] = False
            self._state["progress"] = None
            self._signature = self.signature()
        return True

    def _progress(self, stage: str, done: int, total: int) -> None:
        self._state["progress"] = {"stage": stage, "done": done, "total": total}  # the web app shows it

    def status(self) -> dict:
        with self._lock:
            pending = self._pending_since is not None
        return {"pending": pending, **self._state}

    def start(self) -> None:
        self.request()  # catch up on whatever changed while the server was off
        self._thread = threading.Thread(target=self._loop, name="memeseeks-indexer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            with self._lock:
                wait = self.poll_seconds if self._pending_since is None else self.debounce
            self._wake.wait(timeout=wait)
            self._wake.clear()
