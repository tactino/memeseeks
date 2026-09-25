import numpy as np
import pytest

from memeseeks.library import Library, Models
from memeseeks.search import EmptyLibrary, Searcher, rank_route
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _lib(tmp_path, colors):
    src = tmp_path / "src"
    for name, rgb in colors.items():
        solid(src, name, rgb)
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    return lib, models, src


def test_text_query_finds_the_matching_meme(tmp_path):
    lib, models, _ = _lib(tmp_path, {"cat.png": (255, 0, 0), "dog.png": (0, 0, 255), "grey.png": (90, 90, 90)})
    hits = Searcher(lib, models).search("红猫", k=3)  # 红 → CLIP route, 猫 → OCR route: both agree
    assert hits[0].relpath == "cat.png" and hits[0].text == "猫猫" and hits[0].score > hits[1].score


def test_no_text_and_failed_images_rank_last_on_text_route(tmp_path):
    lib, models, _ = _lib(tmp_path, {"cat.png": (255, 0, 0), "grey.png": (90, 90, 90), "dog.png": (0, 0, 255)})
    searcher = Searcher(lib, models)
    ranked = searcher.rankings("狗")["ocr"]
    assert [searcher.relpath[i] for i in ranked] == ["dog.png", "cat.png", "grey.png"]


def test_deleted_image_disappears_from_results(tmp_path):
    lib, models, src = _lib(tmp_path, {"cat.png": (255, 0, 0), "dog.png": (0, 0, 255)})
    (src / "cat.png").unlink()
    lib.update(models, log=lambda m: None)
    assert [h.relpath for h in Searcher(lib, models).search("猫", k=5)] == ["dog.png"]


def test_empty_library_raises_clear_error(tmp_path):
    with pytest.raises(EmptyLibrary):
        Searcher(Library(tmp_path / "nothing"), Models(bge=FakeBge(), clip=FakeClip()))


def test_rank_route_appends_ids_without_vectors():
    assert rank_route(np.array([1.0, 0.0]), ["b"], np.array([[1.0, 0.0]]), ["a", "b", "c"]) == ["b", "a", "c"]


def test_evaluate_scores_routes_and_hybrid(tmp_path):
    lib, models, _ = _lib(tmp_path, {"cat.png": (255, 0, 0), "dog.png": (0, 0, 255)})
    csv_path = tmp_path / "q.csv"
    csv_path.write_text("q,f\n猫,cat.png\n狗,dog.png\n红色的,cat.png\n", encoding="utf-8-sig")
    result = Searcher(lib, models).evaluate(csv_path)
    assert result["n_queries"] == 3 and result["scores"]["hybrid"]["recall@5"] == 1.0
    assert set(result["scores"]) == {"ocr", "clip", "hybrid"}


def test_eval_reports_a_name_that_exists_in_two_sources(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    solid(a, "same.png", (255, 0, 0))
    solid(b, "same.png", (0, 0, 255))
    lib = Library(tmp_path / "lib")
    lib.add_source(a), lib.add_source(b)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    csv_path = tmp_path / "q.csv"
    csv_path.write_text("q,f\n猫,same.png\n", encoding="utf-8")
    result = Searcher(lib, models).evaluate(csv_path)
    assert result["n_queries"] == 0 and result["unknown_files"] == {"猫": ["same.png"]}


def test_failed_vlm_description_ranks_last_on_the_vlm_route(tmp_path):
    class HalfVlm:
        def describe(self, image):
            if image.getpixel((0, 0))[2] > 200:
                raise RuntimeError("CUDA out of memory")
            return {"画面": "一只猫"}

    src = tmp_path / "src"
    solid(src, "cat.png", (255, 0, 0))
    solid(src, "dog.png", (0, 0, 255))
    solid(src, "grey.png", (90, 90, 90))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    lib.set_vlm(True)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge(), vlm=HalfVlm())
    lib.update(models, log=lambda m: None)
    searcher = Searcher(lib, models)
    ranked = [searcher.relpath[i] for i in searcher.rankings("狗")["vlm"]]
    assert ranked[0] == "cat.png" and set(ranked[1:]) == {"dog.png", "grey.png"}  # failed/none trail
