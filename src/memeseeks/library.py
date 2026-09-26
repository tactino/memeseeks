"""A meme library: source folders plus their index, all stored under one directory."""

from __future__ import annotations

import json
import threading
import os
from pathlib import Path

from .images import ImageRecord, scan_folder
from .index import _atomic_write_text, build_index, build_text_vectors, drop_failures, failure_counts, load_index


class LibraryError(Exception):
    pass


def default_home() -> Path:
    return Path(os.environ.get("MEMESEEKS_HOME") or Path.home() / ".memeseeks")


def _make(name: str):
    if name == "ocr":
        from .models.ocr import RapidOcr
        return RapidOcr()
    if name == "clip":
        from .models.clip import ChineseClip
        return ChineseClip()
    if name == "bge":
        from .models.textembed import BgeM3
        return BgeM3()
    if name == "vlm":
        from .models.vlm import QwenVl
        return QwenVl()
    if name == "tidy":
        from .tidy import Tidier
        return Tidier()
    raise KeyError(name)


class Models:
    """Model wrappers, built on first use; tests pass fakes."""

    def __init__(self, ocr=None, clip=None, bge=None, vlm=None, tidy=None):
        self._models = {"ocr": ocr, "clip": clip, "bge": bge, "vlm": vlm, "tidy": tidy}
        self._lock = threading.Lock()  # the warm-up, the indexer and a search may all ask at once

    def get(self, name: str):
        if self._models[name] is None:
            with self._lock:
                if self._models[name] is None:  # built once, however many threads were waiting
                    self._models[name] = _make(name)
        return self._models[name]


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.index_dir = self.root / "index"

    def config(self) -> dict:
        path = self.root / "library.json"
        cfg = {"sources": [], "vlm": False, "tidy": False}
        if path.exists():
            try:
                cfg.update(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                raise LibraryError(f"{path} is not valid JSON ({exc}); fix or delete it") from exc
        return cfg

    def _save(self, cfg: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(self.root / "library.json", json.dumps(cfg, ensure_ascii=False, indent=2))

    def add_source(self, folder) -> bool:
        cfg = self.config()
        path = str(Path(folder).resolve())
        if path in cfg["sources"]:
            return False
        cfg["sources"].append(path)
        self._save(cfg)
        return True

    def remove_source(self, folder) -> bool:
        """Stop watching a folder. Its files are untouched; its memes leave the library at the next update."""
        cfg = self.config()
        path = str(Path(folder).resolve())
        if path not in cfg["sources"]:
            return False
        cfg["sources"].remove(path)
        self._save(cfg)
        return True

    def set_vlm(self, on: bool) -> None:
        cfg = self.config()
        cfg["vlm"] = bool(on)
        self._save(cfg)

    def set_tidy(self, on: bool) -> None:
        cfg = self.config()
        cfg["tidy"] = bool(on)
        self._save(cfg)

    def records(self) -> tuple[list[ImageRecord], dict]:
        report = {"unreadable": [], "duplicates": 0, "skipped": 0, "missing_sources": []}
        records, seen = [], set()
        for source in self.config()["sources"]:
            if not Path(source).is_dir():
                report["missing_sources"].append(source)
                continue
            scan = scan_folder(source)
            report["unreadable"] += [f"{source}/{r}" for r in scan.unreadable]
            report["duplicates"] += sum(map(len, scan.duplicates.values()))
            report["skipped"] += len(scan.skipped)
            for rec in scan.records:
                if rec.id in seen:
                    report["duplicates"] += 1
                    continue
                seen.add(rec.id)
                records.append(rec)
        return records, report

    def update(self, models: Models, log=print, retry_failed: bool = False, progress=None) -> dict:
        records, report = self.records()
        if not records:  # e.g. an empty or mistyped folder: don't load (or download) any model
            if self.index_dir.exists():
                _atomic_write_text(self.index_dir / "paths.json", "{}")
            report["images"] = 0
            report["failed"] = failure_counts(self.index_dir) if self.index_dir.exists() else {}
            return report
        # Load models before writing: an interrupt during a (slow) model load must leave the library untouched.
        ocr, clip, bge = models.get("ocr"), models.get("clip"), models.get("bge")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        if retry_failed:
            report["retried"] = drop_failures(self.index_dir)
        _atomic_write_text(self.index_dir / "paths.json",
                           json.dumps({r.id: str(r.path) for r in records}, ensure_ascii=False))
        build_index(records, self.index_dir, ocr=ocr, clip=clip, log=log, progress=progress)
        if self.config()["vlm"]:
            try:
                vlm = models.get("vlm")
            except Exception as exc:  # e.g. no GPU on this machine: index everything else, report it
                report["vlm_error"] = f"{type(exc).__name__}: {exc}"
            else:
                build_index(records, self.index_dir, vlm=vlm, log=log, progress=progress)
        if self.config()["tidy"]:
            try:
                tidier = models.get("tidy")
            except Exception as exc:  # no GPU here: the rule-based text stays
                report["tidy_error"] = f"{type(exc).__name__}: {exc}"
            else:
                build_index(records, self.index_dir, tidy=tidier, log=log, progress=progress)
        build_text_vectors(load_index(self.index_dir), self.index_dir, bge, log=log)
        report["images"] = len(records)
        report["failed"] = failure_counts(self.index_dir)
        return report

    def paths(self) -> dict[str, str]:
        path = self.index_dir / "paths.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
