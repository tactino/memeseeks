"""Settings shared by every device that opens this library (see docs/design.md, Settings)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .index import _atomic_write_text

FILE = "settings.json"
VERSION = 1
# name -> allowed values; the first is the default
CHOICES = {
    "theme": ("paper", "night"),
    "frame": (True, False),
    "intro": (True, False),
    "motion": ("full", "reduced"),
    "online": (True, False),   # only matters when the server was started with a web source
}


class SettingsError(ValueError):
    pass


class Settings:
    def __init__(self, library_root):
        self.path = Path(library_root) / FILE
        self._lock = threading.Lock()

    def get(self) -> dict:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            saved = {}
        # unknown keys and bad values (a hand edit, an older version) fall back to the default
        return {k: saved.get(k) if saved.get(k) in allowed else allowed[0] for k, allowed in CHOICES.items()}

    def update(self, changes: dict) -> dict:
        for k, v in changes.items():
            if k not in CHOICES:
                raise SettingsError(f"unknown setting {k!r}")
            if v not in CHOICES[k] or type(v) is not type(CHOICES[k][0]):
                raise SettingsError(f"{k} must be one of {list(CHOICES[k])}")
        with self._lock:
            current = {**self.get(), **changes}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(self.path, json.dumps({"version": VERSION, **current}, indent=1))
        return current
