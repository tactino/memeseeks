from memeseeks.library import Library, Models
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _models():
    return Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())


def test_library_with_chinese_paths(tmp_path):
    src = tmp_path / "我的 梗图"
    solid(src, "红猫.png", (255, 0, 0))
    solid(src / "子目录", "蓝狗.png", (0, 0, 255))
    lib = Library(tmp_path / "库 目录")
    assert lib.add_source(src) is True and lib.add_source(src) is False
    report = lib.update(_models(), log=lambda m: None)
    assert report["missing_sources"] == [] and len(lib.paths()) == 2
    assert all(p.startswith(str(src.resolve())) for p in lib.paths().values())
    assert Library(tmp_path / "库 目录").config()["sources"] == [str(src.resolve())]


def test_duplicates_across_sources_count_once_and_missing_source_is_reported(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    solid(a, "x.png", (255, 0, 0))
    solid(b, "copy.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(a), lib.add_source(b), lib.add_source(tmp_path / "gone")
    report = lib.update(_models(), log=lambda m: None)
    assert len(lib.paths()) == 1 and report["duplicates"] == 1
    assert report["missing_sources"] == [str((tmp_path / "gone").resolve())]


def test_vlm_is_off_by_default_and_used_only_when_on(tmp_path):
    class FakeVlm:
        calls = 0

        def describe(self, image):
            FakeVlm.calls += 1
            return {"画面": "猫"}

    src = tmp_path / "s"
    solid(src, "r.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge(), vlm=FakeVlm())
    lib.update(models, log=lambda m: None)
    assert lib.config()["vlm"] is False and FakeVlm.calls == 0
    lib.set_vlm(True)
    lib.update(models, log=lambda m: None)
    assert FakeVlm.calls == 1
