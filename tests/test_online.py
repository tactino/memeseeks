import random

from fastapi.testclient import TestClient

from memeseeks.library import Library, Models
from memeseeks.online import customer_id_for, klipy_config
from memeseeks.server import create_app
from memeseeks.service import LibraryService
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def test_klipy_config_points_the_browser_at_klipy_directly():
    cfg = klipy_config("KEY123", customer_id="c-1")
    assert cfg.provider == "KLIPY"
    assert cfg.search_url == "https://api.klipy.com/api/v1/KEY123/static-memes/search"
    assert cfg.share_url == "https://api.klipy.com/api/v1/KEY123/static-memes/share/"
    assert cfg.params == {"customer_id": "c-1", "locale": "cn", "content_filter": "medium", "per_page": 24}
    assert cfg.attribution_url == "https://klipy.com"


def test_customer_id_is_random_but_stable_per_library(tmp_path):
    a = customer_id_for(tmp_path / "lib-a")
    assert a == customer_id_for(tmp_path / "lib-a") and a != customer_id_for(tmp_path / "lib-b")
    assert len(a) >= 16 and "memeseeks" not in a  # anonymous: nothing about the machine or user


def _client(tmp_path, online=None):
    src = tmp_path / "src"
    solid(src, "cat.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    app = create_app(LibraryService(lib, models, rng=random.Random(0)), online=online)
    return TestClient(app, base_url="http://127.0.0.1")


def test_online_config_is_off_unless_configured(tmp_path):
    assert _client(tmp_path).get("/api/online/config").json() == {"enabled": False}


def test_online_config_is_served_when_on(tmp_path):
    body = _client(tmp_path, klipy_config("KEY123", customer_id="c-1")).get("/api/online/config").json()
    assert body["enabled"] is True and body["provider"] == "KLIPY"
    assert body["search_url"].endswith("/KEY123/static-memes/search") and body["params"]["customer_id"] == "c-1"


def test_the_server_no_longer_relays_online_searches_or_images(tmp_path):
    client = _client(tmp_path, klipy_config("KEY123", customer_id="c-1"))
    assert client.get("/api/online", params={"q": "猫"}).status_code == 404
    assert client.get("/api/online/img/klipy:1", params={"v": "thumb"}).status_code == 404
