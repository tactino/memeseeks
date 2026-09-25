import json
import random

import pytest
from fastapi.testclient import TestClient

from memeseeks.library import Library, Models
from memeseeks.online import KlipyMemes, OnlineError, OnlineHit, OnlineService
from memeseeks.server import create_app
from memeseeks.service import LibraryService
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid

KLIPY_RESPONSE = {
    "result": True,
    "data": {
        "data": [
            {"id": 101, "slug": "cat-keyboard", "title": "Cat on keyboard", "type": "meme",
             "file": {"hd": {"jpg": {"url": "https://static.example/101_hd.jpg", "width": 800, "height": 600}},
                      "sm": {"jpg": {"url": "https://static.example/101_sm.jpg", "width": 220, "height": 165}}}},
            {"id": "ad-1", "type": "ad", "title": "Buy things",
             "file": {"hd": {"jpg": {"url": "https://ads.example/ad.jpg", "width": 800}}}},
            {"id": 102, "title": "No image here", "type": "meme"},
        ],
        "has_next": True,
    },
}


def test_klipy_builds_the_request_and_parses_hits():
    seen = {}

    def fetch(url):
        seen["url"] = url
        return KLIPY_RESPONSE

    hits = KlipyMemes("KEY123", fetch=fetch).search("猫 键盘", n=5)
    assert "/api/v1/KEY123/static-memes/search?" in seen["url"] and "q=%E7%8C%AB" in seen["url"]
    assert "per_page=5" in seen["url"]
    assert hits == [OnlineHit(id="klipy:101", title="Cat on keyboard",
                              thumb="https://static.example/101_sm.jpg", full="https://static.example/101_hd.jpg",
                              provider="KLIPY")]


def test_klipy_error_payload_raises_a_clear_error():
    bad = {"result": False, "errors": {"message": ["The provided API key is invalid."]}}
    with pytest.raises(OnlineError, match="invalid"):
        KlipyMemes("nope", fetch=lambda url: bad).search("cat")


class FakeSource:
    name = "FAKE"

    def search(self, query, n=20):
        return [OnlineHit("fake:1", f"{query} meme", "https://img.example/t.jpg", "https://img.example/f.jpg", "FAKE")]


def fake_download(url, max_bytes):
    return (b"\xff\xd8\xff fake jpeg for " + url.encode(), "image/jpeg")


def test_proxy_serves_only_urls_a_search_returned():
    online = OnlineService(FakeSource(), download=fake_download)
    hits = online.search("猫")
    assert online.image(hits[0].id, "thumb")[0].endswith(b"t.jpg")
    assert online.image("fake:999", "thumb") is None  # never searched: no fetch at all
    assert online.image(hits[0].id, "../../etc") is None


def test_proxy_refuses_non_images():
    online = OnlineService(FakeSource(), download=lambda url, max_bytes: (b"<html>", "text/html"))
    hit = online.search("猫")[0]
    with pytest.raises(OnlineError):
        online.image(hit.id, "full")


def _client(tmp_path, online=None):
    src = tmp_path / "src"
    solid(src, "cat.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    app = create_app(LibraryService(lib, models, rng=random.Random(0)), online=online)
    return TestClient(app, base_url="http://127.0.0.1")


def test_online_endpoint_is_off_unless_configured(tmp_path):
    body = _client(tmp_path).get("/api/online", params={"q": "猫"}).json()
    assert body == {"enabled": False, "hits": []}


def test_online_hits_come_back_with_proxied_image_urls(tmp_path):
    client = _client(tmp_path, OnlineService(FakeSource(), download=fake_download))
    body = client.get("/api/online", params={"q": "猫"}).json()
    assert body["enabled"] is True and body["provider"] == "FAKE"
    hit = body["hits"][0]
    assert hit["thumb"].startswith("/api/online/img/") and "img.example" not in json.dumps(hit)
    r = client.get(hit["thumb"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get("/api/online/img/fake:999?v=thumb").status_code == 404


def test_provider_failure_is_a_clear_error_not_a_500(tmp_path):
    class Broken:
        name = "BROKEN"

        def search(self, query, n=20):
            raise OnlineError("KLIPY said: The provided API key is invalid.")

    r = _client(tmp_path, OnlineService(Broken(), download=fake_download)).get("/api/online", params={"q": "猫"})
    assert r.status_code == 502 and "invalid" in r.json()["error"]


def test_online_image_can_be_downloaded_as_a_file(tmp_path):
    client = _client(tmp_path, OnlineService(FakeSource(), download=fake_download))
    hit = client.get("/api/online", params={"q": "猫"}).json()["hits"][0]
    r = client.get(hit["image"] + "&download=1")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "fake-1.jpg" in r.headers["content-disposition"]
