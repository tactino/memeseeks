import random

import pytest

from memeseeks.library import Library, Models
from memeseeks.search import EmptyLibrary
from memeseeks.service import LibraryService, pick_rediscover
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _service(tmp_path, colors, clock=None):
    src = tmp_path / "src"
    for name, rgb in colors.items():
        solid(src, name, rgb)
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    kw = {"clock": clock} if clock else {}
    return LibraryService(lib, models, rng=random.Random(0), **kw), lib, models, src


def test_pick_rediscover_prefers_never_and_least_recently_shown():
    ids = [f"i{k}" for k in range(10)]
    seen = {f"i{k}": 100.0 + k for k in range(6)}  # i6..i9 never shown
    picked = pick_rediscover(ids, seen, 4, now=200.0, rng=random.Random(1))
    assert set(picked) == {"i6", "i7", "i8", "i9"}


def test_rediscover_cycles_through_the_library(tmp_path):
    t = [1000.0]
    svc, *_ = _service(tmp_path, {f"{k}.png": (k * 20, 10, 10) for k in range(6)}, clock=lambda: t[0])
    shown = set()
    for _ in range(3):
        shown |= {m["id"] for m in svc.rediscover(n=2)}
        t[0] += 60
    assert len(shown) == 6


def test_search_picks_up_a_new_add_without_restart(tmp_path):
    svc, lib, models, src = _service(tmp_path, {"cat.png": (255, 0, 0)})
    assert [m["relpath"] for m in svc.search("狗", k=5)] == ["cat.png"]
    solid(src, "dog.png", (0, 0, 255))
    lib.update(models, log=lambda m: None)
    assert svc.search("狗", k=1)[0]["relpath"] == "dog.png"


def test_path_and_thumbnail_only_for_known_existing_ids(tmp_path):
    svc, lib, _, src = _service(tmp_path, {"cat.png": (255, 0, 0)})
    cat = next(iter(lib.paths()))
    assert svc.path(cat) is not None and svc.path("../../etc/passwd") is None and svc.path("nope") is None
    thumb = svc.thumbnail(cat, size=64)
    assert thumb.exists() and thumb.suffix == ".jpg" and svc.thumbnail(cat, size=64) == thumb
    (src / "cat.png").unlink()
    assert svc.path(cat) is None


def test_empty_library_search_raises(tmp_path):
    svc = LibraryService(Library(tmp_path / "none"), Models(bge=FakeBge(), clip=FakeClip()))
    with pytest.raises(EmptyLibrary):
        svc.search("猫", k=3)


def test_warm_loads_the_query_models_up_front(tmp_path):
    svc, *_ = _service(tmp_path, {"cat.png": (255, 0, 0)})
    loaded = []

    class Spy(Models):
        def get(self, name):
            loaded.append(name)
            return super().get(name)

    svc.models = Spy(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    svc.warm()
    assert {"bge", "clip"} <= set(loaded)


def test_a_search_during_add_does_not_leave_the_server_stale(tmp_path, monkeypatch):
    import memeseeks.library as library_module
    svc, lib, models, src = _service(tmp_path, {"cat.png": (255, 0, 0)})
    svc.search("猫", k=1)
    solid(src, "dog.png", (0, 0, 255))
    real_build = library_module.build_index

    def build_with_a_request_in_the_middle(*args, **kwargs):
        svc.search("狗", k=1)  # a phone asks while paths.json is new but vectors are not
        return real_build(*args, **kwargs)

    monkeypatch.setattr(library_module, "build_index", build_with_a_request_in_the_middle)
    lib.update(models, log=lambda m: None)
    hit = svc.search("狗", k=1)[0]
    assert hit["relpath"] == "dog.png"


def test_concurrent_rediscover_and_thumbnails_do_not_fail(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    svc, lib, *_ = _service(tmp_path, {f"{k}.png": (k * 30, 20, 20) for k in range(4)})
    some_id = next(iter(lib.paths()))
    with ThreadPoolExecutor(16) as pool:
        jobs = [pool.submit(svc.rediscover, 2) for _ in range(16)]
        jobs += [pool.submit(svc.thumbnail, some_id, 128) for _ in range(16)]
        for job in jobs:
            job.result()  # raises if any request failed
    import json
    json.loads((lib.root / "seen.json").read_text(encoding="utf-8"))  # still valid
