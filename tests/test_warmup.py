import os
import threading
import time

from fastapi.testclient import TestClient

import memeseeks.library as library_module
from memeseeks.library import Models
from memeseeks.server import create_app
from memeseeks.warmup import Warmup
from tests.test_albums_api import _setup


class _Service:
    """Just what Warmup touches: models, and warm() for the index."""

    def __init__(self, get):
        self.models = type("M", (), {"get": staticmethod(get)})()
        self.warmed = False

    def warm(self):
        self.warmed = True


def test_models_are_built_once_even_when_two_threads_ask_at_once(monkeypatch):
    built = []

    def slow_make(name):
        built.append(name)
        time.sleep(0.05)
        return object()

    monkeypatch.setattr(library_module, "_make", slow_make)
    models = Models()
    threads = [threading.Thread(target=models.get, args=("bge",)) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert built == ["bge"]


def test_warmup_shows_the_download_until_the_models_are_ready(tmp_path):
    blobs = tmp_path / "models--BAAI--bge-m3" / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "abc.incomplete").write_bytes(b"x" * 1000)       # a download under way
    go, started = threading.Event(), []
    service = _Service(lambda name: go.wait(5))
    w = Warmup(service, then=lambda: started.append(True), cache=tmp_path, expected=4000)
    w.start()
    s = w.status()
    assert s["state"] == "loading" and s["download"] == {"done": 1000, "total": 4000}
    go.set()
    w.join(5)
    assert w.status() == {"state": "ready", "download": None, "error": None}
    assert service.warmed and started == [True]


def test_warmup_without_a_download_just_loads(tmp_path):
    (tmp_path / "models--BAAI--bge-m3" / "blobs").mkdir(parents=True)
    (tmp_path / "models--BAAI--bge-m3" / "blobs" / "done").write_bytes(b"x" * 4000)
    go = threading.Event()
    w = Warmup(_Service(lambda name: go.wait(5)), cache=tmp_path, expected=4000)
    w.start()
    assert w.status()["state"] == "loading" and w.status()["download"] is None
    go.set()
    w.join(5)


def test_warmup_failure_says_how_to_reach_the_models_from_china(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_ENDPOINT", raising=False)

    def offline(name):
        raise OSError("We couldn't connect to 'https://huggingface.co' to load the files")

    started = []
    w = Warmup(_Service(offline), then=lambda: started.append(True), cache=tmp_path, expected=4000)
    w.start()
    w.join(5)
    s = w.status()
    assert s["state"] == "error" and "HF_ENDPOINT=https://hf-mirror.com" in s["error"] and started == []


def test_search_waits_for_the_models_and_the_page_can_ask(tmp_path):
    client, *_ = _setup(tmp_path)
    app = client.app

    class Loading:
        def status(self):
            return {"state": "loading", "download": {"done": 1, "total": 4}, "error": None}

    waiting = TestClient(create_app(app.state.service, warmup=Loading()), base_url="http://127.0.0.1")
    assert waiting.get("/api/ready").json()["download"] == {"done": 1, "total": 4}
    r = waiting.get("/api/search", params={"q": "猫"})
    assert r.status_code == 503 and "error" in r.json()
    assert waiting.get("/api/albums").status_code == 200                 # everything else works meanwhile
    got = client.get("/api/ready").json()
    assert (got["state"], got["download"], got["error"]) == ("ready", None, None)


def test_the_model_wrappers_never_download_a_model_twice():
    import memeseeks.models  # noqa: F401

    assert os.environ.get("DISABLE_SAFETENSORS_CONVERSION") == "true"


def test_indexing_reports_how_far_it_has_got(tmp_path):
    from memeseeks.library import Library
    from tests.fakes import FakeBge, FakeClip, FakeOcr, solid

    for k in range(3):
        solid(tmp_path / "memes", f"{k}.png", (255, k, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(tmp_path / "memes")
    calls = []
    lib.update(Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge()), log=lambda m: None,
               progress=lambda stage, done, total: calls.append((stage, done, total)))
    assert calls[0] == ("ocr", 0, 3) and ("ocr", 3, 3) in calls and calls[-1] == ("clip", 3, 3)
    calls.clear()
    lib.update(Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge()), log=lambda m: None,
               progress=lambda *a: calls.append(a))
    assert calls == []                                                    # nothing new: nothing to report


def test_the_indexer_shows_its_progress_while_it_runs(tmp_path):
    import contextlib

    from memeseeks.indexer import BackgroundIndexer
    from memeseeks.library import Library
    from tests.fakes import FakeBge, FakeClip, FakeOcr, solid

    solid(tmp_path / "memes", "a.png", (255, 0, 0))
    solid(tmp_path / "memes", "b.png", (0, 0, 255))
    lib = Library(tmp_path / "lib")
    lib.add_source(tmp_path / "memes")
    seen = []

    class Watching(FakeOcr):
        def __call__(self, image):
            seen.append(indexer.status()["progress"])
            return super().__call__(image)

    indexer = BackgroundIndexer(lib, Models(ocr=Watching(), clip=FakeClip(), bge=FakeBge()), debounce=0,
                                clock=lambda: 0.0, priority=contextlib.nullcontext)
    indexer.request()
    assert indexer.tick() is True
    assert seen == [{"stage": "ocr", "done": 0, "total": 2}, {"stage": "ocr", "done": 1, "total": 2}]
    assert indexer.status()["progress"] is None and indexer.status()["last_images"] == 2


def test_ready_carries_the_indexing_state(tmp_path):
    client, _, indexer, _ = _setup(tmp_path)
    got = client.get("/api/ready").json()
    assert got["state"] == "ready" and set(got["indexing"]) >= {"pending", "running", "progress"}
