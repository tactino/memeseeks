import json

import numpy as np
from PIL import Image

from memeseeks.images import scan_folder
from memeseeks.index import build_index, load_index
from memeseeks.models.ocr import OcrLine


class FakeOcr:
    def __init__(self):
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        return [OcrLine("字", [[0, 0], [1, 0], [1, 1], [0, 1]], 0.9)]


class FlakyVlm:
    def describe(self, image):
        if image.getpixel((0, 0)) == (0, 0, 255):
            raise RuntimeError("CUDA out of memory")
        return {"画面": "图"}


class FakeClip:
    def embed_images(self, images):
        return np.ones((len(images), 3), np.float32)


def _folder(tmp_path, colors):
    for i, c in enumerate(colors):
        Image.new("RGB", (4, 4), c).save(tmp_path / f"{i}.png")
    return scan_folder(tmp_path).records


def test_build_index_records_errors_and_resumes(tmp_path):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    records = _folder(imgs, [(255, 0, 0), (0, 0, 255)])
    out = tmp_path / "index"
    ocr = FakeOcr()
    build_index(records, out, ocr=ocr, vlm=FlakyVlm(), clip=FakeClip(), log=lambda m: None)
    build_index(records, out, ocr=ocr, vlm=FlakyVlm(), clip=FakeClip(), log=lambda m: None)
    assert ocr.calls == 2  # second run skipped everything already done
    idx = load_index(out)
    assert set(idx.ocr) == {r.id for r in records}
    errors = [v for v in idx.vlm.values() if "_error" in v]
    assert len(errors) == 1 and "out of memory" in errors[0]["_error"]
    assert idx.clip.shape == (2, 3) and sorted(idx.clip_ids) == sorted(r.id for r in records)
    assert set(idx.relpath.values()) == {"0.png", "1.png"}


def test_jsonl_rows_are_utf8_readable(tmp_path):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    records = _folder(imgs, [(1, 1, 1)])
    build_index(records, tmp_path / "idx", ocr=FakeOcr(), log=lambda m: None)
    line = (tmp_path / "idx" / "ocr.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["value"][0]["text"] == "字"


def test_load_index_can_read_an_alternate_vlm_file(tmp_path):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    records = _folder(imgs, [(9, 9, 9)])
    out = tmp_path / "idx"
    build_index(records, out, vlm=FlakyVlm(), log=lambda m: None)
    (out / "vlm.jsonl").rename(out / "vlm.old.jsonl")
    assert load_index(out).vlm == {}
    assert load_index(out, vlm_file="vlm.old.jsonl").vlm == {records[0].id: {"画面": "图"}}


class PickyClip:
    """Fails whenever a batch contains a blue image, like a processor that rejects one file."""

    def __init__(self):
        self.calls = 0

    def embed_images(self, images):
        self.calls += 1
        if any(im.getpixel((0, 0)) == (0, 0, 255) for im in images):
            raise RuntimeError("processor rejected image")
        return np.ones((len(images), 3), np.float32)


def test_clip_failure_is_isolated_to_the_bad_image_and_not_retried(tmp_path):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    records = _folder(imgs, [(255, 0, 0), (0, 0, 255), (0, 255, 0)])
    out = tmp_path / "index"
    clip = PickyClip()
    build_index(records, out, clip=clip, log=lambda m: None)
    idx = load_index(out)
    blue = next(r.id for r in records if r.relpath == "1.png")
    assert sorted(idx.clip_ids) == sorted(r.id for r in records if r.id != blue)
    assert idx.clip.shape == (2, 3)
    errors = json.loads((out / "clip_errors.json").read_text(encoding="utf-8"))
    assert list(errors) == [blue] and "rejected" in errors[blue]
    calls = clip.calls
    build_index(records, out, clip=clip, log=lambda m: None)
    assert clip.calls == calls  # the bad image is not retried forever


def test_truncated_last_jsonl_line_is_recomputed(tmp_path):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    records = _folder(imgs, [(255, 0, 0), (0, 255, 0)])
    out = tmp_path / "idx"
    build_index(records, out, ocr=FakeOcr(), log=lambda m: None)
    path = out / "ocr.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n" + lines[1][: len(lines[1]) // 2], encoding="utf-8")  # killed mid-write
    ocr = FakeOcr()
    build_index(records, out, ocr=ocr, log=lambda m: None)
    assert ocr.calls == 1 and set(load_index(out).ocr) == {r.id for r in records}


def test_clip_ids_and_vectors_are_reconciled_after_a_crash(tmp_path):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    records = _folder(imgs, [(255, 0, 0), (0, 255, 0)])
    out = tmp_path / "idx"
    build_index(records, out, clip=FakeClip(), log=lambda m: None)
    np.save(out / "clip.npy", np.ones((1, 3), np.float32))  # vectors written for fewer ids than listed
    idx = load_index(out)
    assert len(idx.clip_ids) == idx.clip.shape[0] == 1
    build_index(records, out, clip=FakeClip(), log=lambda m: None)
    idx = load_index(out)
    assert sorted(idx.clip_ids) == sorted(r.id for r in records) and idx.clip.shape == (2, 3)


class CountingEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return np.ones((len(texts), 4), np.float32)


def test_text_vectors_skip_empty_and_errors_and_rebuild_only_on_change(tmp_path):
    from memeseeks.index import LoadedIndex, build_text_vectors, load_text_vectors, route_texts
    line = {"text": "猫", "box": [], "score": 1.0}
    idx = LoadedIndex(ocr={"a": [line], "b": [], "c": {"_error": "x"}},
                      vlm={"a": {"画面": "猫"}, "b": {"_error": "oom"}},
                      clip_ids=[], clip=np.zeros((0, 0), np.float32), relpath={})
    texts = route_texts(idx)
    assert texts == {"ocr": {"a": "猫"}, "vlm": {"a": "画面：猫"}}
    emb = CountingEmbedder()
    build_text_vectors(idx, tmp_path, emb, log=lambda m: None)
    build_text_vectors(idx, tmp_path, emb, log=lambda m: None)
    assert emb.calls == 2  # one per route, second run skipped
    ids, vecs = load_text_vectors(tmp_path, "ocr")
    assert ids == ["a"] and vecs.shape == (1, 4)
    idx.ocr["b"] = [dict(line, text="狗")]
    build_text_vectors(idx, tmp_path, emb, log=lambda m: None)
    assert emb.calls == 3 and load_text_vectors(tmp_path, "ocr")[0] == ["a", "b"]


def test_load_text_vectors_missing_is_empty(tmp_path):
    from memeseeks.index import load_text_vectors
    ids, vecs = load_text_vectors(tmp_path, "ocr")
    assert ids == [] and vecs.shape[0] == 0


def test_failure_counts_and_drop_failures_keep_good_rows(tmp_path):
    from memeseeks.index import drop_failures, failure_counts
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    records = _folder(imgs, [(255, 0, 0), (0, 0, 255)])
    out = tmp_path / "idx"
    build_index(records, out, ocr=FakeOcr(), vlm=FlakyVlm(), clip=PickyClip(), log=lambda m: None)
    assert failure_counts(out) == {"ocr": 0, "vlm": 1, "clip": 1}
    assert drop_failures(out) == 2
    assert failure_counts(out) == {"ocr": 0, "vlm": 0, "clip": 0}
    idx = load_index(out)
    assert len(idx.vlm) == 1 and len(idx.clip_ids) == 1  # good rows kept, failed ones will be redone


def test_text_vectors_rebuild_when_the_embedder_changes(tmp_path):
    from memeseeks.index import LoadedIndex, build_text_vectors
    idx = LoadedIndex(ocr={"a": [{"text": "猫", "box": [], "score": 1.0}]}, vlm={}, clip_ids=[],
                      clip=np.zeros((0, 0), np.float32), relpath={})
    first, second = CountingEmbedder(), CountingEmbedder()
    first.model_id, second.model_id = "model-a", "model-b"
    build_text_vectors(idx, tmp_path, first, log=lambda m: None)
    build_text_vectors(idx, tmp_path, second, log=lambda m: None)
    assert first.calls == 1 and second.calls == 1
