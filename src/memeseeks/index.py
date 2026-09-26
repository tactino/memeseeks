"""Per-image analysis cache (OCR lines, VLM description, CLIP vector). Safe to re-run: done work is skipped."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .images import ImageRecord, load_image
from .maintext import common_lines, main_text
from .models.ocr import OcrLine
from .models.vlm import description_text

CLIP_CHUNK = 16  # images per batch; also how often indexing progress moves in the CLIP stage


def _tmp_for(path: Path) -> Path:
    """A temp name unique to this process and thread, so concurrent writers never share one."""
    return path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = _tmp_for(path)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_save_npy(path: Path, arr: np.ndarray) -> None:
    tmp = _tmp_for(path)
    with open(tmp, "wb") as f:
        np.save(f, arr)
    os.replace(tmp, path)


def _read_jsonl(path: Path) -> dict[str, dict]:
    """Rows by id; a line cut short by a killed run is skipped, so its image is simply redone."""
    rows: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows[row["id"]] = row
    return rows


def _reconcile(ids: list[str], vecs):
    """ids and vectors are written as two files; after a crash keep only the rows both agree on."""
    n = min(len(ids), 0 if vecs is None else len(vecs))
    return ids[:n], (vecs[:n] if n else None)


def _jsonl_stage(records, path: Path, fn, name: str, log, progress=None) -> None:
    done = _read_jsonl(path)
    todo = [r for r in records if r.id not in done]
    if todo and progress:
        progress(name, 0, len(todo))
    if path.exists() and path.stat().st_size and not path.read_bytes().endswith(b"\n"):
        with path.open("a", encoding="utf-8") as f:
            f.write("\n")  # never append onto a half-written line
    with path.open("a", encoding="utf-8") as f:
        for i, rec in enumerate(todo, 1):
            try:
                value = fn(load_image(rec.path))
            except Exception as exc:  # one bad image must not abort the run
                value = {"_error": f"{type(exc).__name__}: {exc}"}
            f.write(json.dumps({"id": rec.id, "relpath": rec.relpath, "value": value}, ensure_ascii=False) + "\n")
            f.flush()
            if progress:
                progress(name, i, len(todo))
            if i % 10 == 0 or i == len(todo):
                log(f"{name}: {i}/{len(todo)}")


def _embed_chunk(clip, chunk, errors: dict[str, str]):
    """Embed a chunk; if it fails, retry image by image so one bad image only loses itself."""
    try:
        return chunk, clip.embed_images([load_image(r.path) for r in chunk])
    except Exception:
        kept, rows = [], []
        for rec in chunk:
            try:
                rows.append(clip.embed_images([load_image(rec.path)]))
                kept.append(rec)
            except Exception as exc:
                errors[rec.id] = f"{type(exc).__name__}: {exc}"
        return kept, (np.concatenate(rows) if rows else None)


def _clip_stage(records, out: Path, clip, log, progress=None) -> None:
    ids_path, vec_path, err_path = out / "clip_ids.json", out / "clip.npy", out / "clip_errors.json"
    ids = json.loads(ids_path.read_text(encoding="utf-8")) if ids_path.exists() else []
    vecs = np.load(vec_path) if vec_path.exists() else None
    errors = json.loads(err_path.read_text(encoding="utf-8")) if err_path.exists() else {}
    ids, vecs = _reconcile(ids, vecs)
    done = set(ids) | set(errors)  # failed images are recorded, not retried; delete clip_errors.json to retry
    todo = [r for r in records if r.id not in done]
    if todo and progress:
        progress("clip", 0, len(todo))
    for start in range(0, len(todo), CLIP_CHUNK):
        kept, new = _embed_chunk(clip, todo[start:start + CLIP_CHUNK], errors)
        if new is not None:
            vecs = new if vecs is None else np.concatenate([vecs, new])
            ids += [r.id for r in kept]
            _atomic_save_npy(vec_path, vecs)
            _atomic_write_text(ids_path, json.dumps(ids))
        if errors:
            _atomic_write_text(err_path, json.dumps(errors, ensure_ascii=False))
        if progress:
            progress("clip", min(start + CLIP_CHUNK, len(todo)), len(todo))
        log(f"clip: {len(ids)} embedded, {len(errors)} failed, of {len(records)}")


def build_index(records: list[ImageRecord], out_dir, ocr=None, vlm=None, clip=None, log=print, progress=None) -> None:
    """progress(stage, done, total), if given, is called as each stage works through the new images."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(out / "relpaths.json", json.dumps({r.id: r.relpath for r in records}, ensure_ascii=False))
    if ocr is not None:
        _jsonl_stage(records, out / "ocr.jsonl", lambda im: [asdict(line) for line in ocr(im)], "ocr", log, progress)
    if vlm is not None:
        _jsonl_stage(records, out / "vlm.jsonl", vlm.describe, "vlm", log, progress)
    if clip is not None:
        _clip_stage(records, out, clip, log, progress)


@dataclass
class LoadedIndex:
    ocr: dict[str, list[dict]]
    vlm: dict[str, dict]
    clip_ids: list[str]
    clip: np.ndarray
    relpath: dict[str, str]


def load_index(out_dir, vlm_file: str = "vlm.jsonl") -> LoadedIndex:
    out = Path(out_dir)
    ids_path, vec_path = out / "clip_ids.json", out / "clip.npy"
    ids = json.loads(ids_path.read_text(encoding="utf-8")) if ids_path.exists() else []
    ids, vecs = _reconcile(ids, np.load(vec_path) if vec_path.exists() else None)
    return LoadedIndex(
        ocr={k: v["value"] for k, v in _read_jsonl(out / "ocr.jsonl").items()},
        vlm={k: v["value"] for k, v in _read_jsonl(out / vlm_file).items()},
        clip_ids=ids,
        clip=vecs if vecs is not None else np.zeros((0, 0), np.float32),
        relpath=json.loads((out / "relpaths.json").read_text(encoding="utf-8")) if (out / "relpaths.json").exists() else {},
    )


def route_texts(idx: LoadedIndex) -> dict[str, dict[str, str]]:
    """Non-empty text per image for each text route; OCR/VLM error rows count as no text. For OCR it is the
    meme's own words (maintext.py): no watermarks, accounts or screen furniture, wrapped lines joined."""
    lines = {i: [OcrLine(**l) for l in v] for i, v in idx.ocr.items() if isinstance(v, list)}
    common = common_lines(lines.values())
    ocr = {i: main_text(ls, common) for i, ls in lines.items()}
    vlm = {i: description_text(v) for i, v in idx.vlm.items() if isinstance(v, dict) and "_error" not in v}
    return {"ocr": {i: t for i, t in ocr.items() if t.strip()},
            "vlm": {i: t for i, t in vlm.items() if t.strip()}}


def build_text_vectors(idx: LoadedIndex, out_dir, embedder, log=print) -> None:
    """Embed each route's texts; skipped when the (id, text) set is unchanged since the last run."""
    out = Path(out_dir)
    for route, texts in route_texts(idx).items():
        ids = sorted(texts)
        model = getattr(embedder, "model_id", type(embedder).__name__)  # new embedder -> new vectors
        fp = hashlib.sha256(json.dumps([model, [[i, texts[i]] for i in ids]], ensure_ascii=False).encode()).hexdigest()
        meta, vec = out / f"text_{route}.json", out / f"text_{route}.npy"
        if meta.exists() and vec.exists() and json.loads(meta.read_text(encoding="utf-8")).get("fingerprint") == fp:
            continue
        if not ids:
            for p in (meta, vec):
                p.unlink(missing_ok=True)
            continue
        _atomic_save_npy(vec, embedder.embed([texts[i] for i in ids]))
        _atomic_write_text(meta, json.dumps({"fingerprint": fp, "ids": ids}, ensure_ascii=False))
        log(f"text vectors ({route}): {len(ids)}")


def load_text_vectors(out_dir, route: str) -> tuple[list[str], np.ndarray]:
    out = Path(out_dir)
    meta, vec = out / f"text_{route}.json", out / f"text_{route}.npy"
    if not (meta.exists() and vec.exists()):
        return [], np.zeros((0, 0), np.float32)
    ids, arr = json.loads(meta.read_text(encoding="utf-8"))["ids"], np.load(vec)
    if len(ids) != len(arr):
        return [], np.zeros((0, 0), np.float32)
    return ids, arr


_STAGE_FILES = {"ocr": "ocr.jsonl", "vlm": "vlm.jsonl"}


def _is_error(value) -> bool:
    return isinstance(value, dict) and "_error" in value


def failure_counts(out_dir) -> dict[str, int]:
    """How many images each stage recorded as failed (they are searchable only on the other routes)."""
    out = Path(out_dir)
    counts = {stage: sum(1 for row in _read_jsonl(out / name).values() if _is_error(row["value"]))
              for stage, name in _STAGE_FILES.items()}
    errors = out / "clip_errors.json"
    counts["clip"] = len(json.loads(errors.read_text(encoding="utf-8"))) if errors.exists() else 0
    return counts


def drop_failures(out_dir) -> int:
    """Forget recorded failures so the next build retries those images; good rows are kept."""
    out = Path(out_dir)
    dropped = 0
    for name in _STAGE_FILES.values():
        rows = _read_jsonl(out / name)
        good = [row for row in rows.values() if not _is_error(row["value"])]
        if len(good) < len(rows):
            dropped += len(rows) - len(good)
            _atomic_write_text(out / name, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in good))
    errors = out / "clip_errors.json"
    if errors.exists():
        dropped += len(json.loads(errors.read_text(encoding="utf-8")))
        errors.unlink()
    return dropped
