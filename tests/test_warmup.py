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
    assert client.get("/api/ready").json() == {"state": "ready", "download": None, "error": None}


def test_the_model_wrappers_never_download_a_model_twice():
    import memeseeks.models  # noqa: F401

    assert os.environ.get("DISABLE_SAFETENSORS_CONVERSION") == "true"
