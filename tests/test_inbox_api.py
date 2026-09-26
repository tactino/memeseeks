import base64
import contextlib
import io
import random

from fastapi.testclient import TestClient
from PIL import Image

from memeseeks.inbox import Inbox
from memeseeks.indexer import BackgroundIndexer
from memeseeks.library import Library, Models
from memeseeks.server import create_app
from memeseeks.service import LibraryService
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _png(rgb=(255, 0, 0)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), rgb).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _setup(tmp_path, token=None):
    src = tmp_path / "album"
    solid(src, "dog.png", (0, 0, 255))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    inbox = Inbox(lib)
    now = [0.0]
    indexer = BackgroundIndexer(lib, models, debounce=1, clock=lambda: now[0], priority=contextlib.nullcontext)
    app = create_app(LibraryService(lib, models, rng=random.Random(0)), token=token, inbox=inbox, indexer=indexer)
    return TestClient(app, base_url="http://127.0.0.1"), inbox, indexer, now


BODY = {"image": _png(), "site": "豆瓣", "page_url": "https://www.douban.com/group/topic/1/", "page_title": "人类超爱梗"}


def test_inbox_needs_the_key_even_on_localhost(tmp_path):
    client, inbox, _, _ = _setup(tmp_path)
    assert client.post("/api/inbox", json=BODY).status_code == 401
    assert client.post("/api/inbox", json=BODY, headers={"X-Memeseeks-Key": "wrong"}).status_code == 401
    assert not inbox.folder.exists() or not any(inbox.folder.iterdir())


def test_collected_meme_becomes_searchable_after_background_indexing(tmp_path):
    client, inbox, indexer, now = _setup(tmp_path)
    r = client.post("/api/inbox", json=BODY, headers={"X-Memeseeks-Key": inbox.key()})
    assert r.status_code == 200 and r.json()["status"] == "added"
    assert client.get("/api/status").json()["indexing"]["pending"] is True
    now[0] += 2
    assert indexer.tick() is True
    assert [p["id"] for p in client.get("/api/review").json()["pending"]] == [r.json()["id"]]  # little text
    client.post("/api/review", json={"id": r.json()["id"], "decision": "keep"})
    hits = client.get("/api/search", params={"q": "猫"}).json()["matches"]
    assert [h["id"] for h in hits] == [r.json()["id"]]
    assert hits[0]["source"]["page_title"] == "人类超爱梗"


def test_inbox_rejects_bad_payloads(tmp_path):
    client, inbox, _, _ = _setup(tmp_path)
    key = {"X-Memeseeks-Key": inbox.key()}
    assert client.post("/api/inbox", json={"image": "!!!not base64"}, headers=key).status_code == 400
    assert client.post("/api/inbox", json={"image": base64.b64encode(b"text").decode()}, headers=key).status_code == 400
    assert client.post("/api/inbox", content=b"{not json", headers=key).status_code == 400
    too_big = {"Content-Length": str(40 * 1024 * 1024), **key}
    assert client.post("/api/inbox", content=b"{}", headers=too_big).status_code == 413


def test_inbox_works_with_its_key_when_the_server_uses_a_token(tmp_path):
    client, inbox, _, _ = _setup(tmp_path, token="a-long-enough-token-123")
    assert client.post("/api/inbox", json=BODY, headers={"X-Memeseeks-Key": inbox.key()}).status_code == 200
    assert client.get("/api/status").status_code == 401  # everything else still needs the token


def test_inbox_is_absent_when_not_configured(tmp_path):
    lib = Library(tmp_path / "lib")
    solid(tmp_path / "a", "x.png", (255, 0, 0))
    lib.add_source(tmp_path / "a")
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    client = TestClient(create_app(LibraryService(lib, models)), base_url="http://127.0.0.1")
    assert client.post("/api/inbox", json=BODY, headers={"X-Memeseeks-Key": "x"}).status_code in (404, 405)
    assert "indexing" not in client.get("/api/status").json()


def test_the_browser_script_can_list_albums_and_collect_into_one(tmp_path):
    client, inbox, _, _ = _setup(tmp_path, token="a-long-enough-token-123")
    key = {"X-Memeseeks-Key": inbox.key()}
    assert client.get("/api/inbox/albums").status_code == 401                     # the key, not the token
    assert client.get("/api/inbox/albums", headers={"X-Memeseeks-Key": "wrong"}).status_code == 401
    work = client.post("/api/albums", json={"name": "上班"}, params={"token": "a-long-enough-token-123"}).json()
    listed = client.get("/api/inbox/albums", headers=key).json()
    assert listed == [{"id": "liked", "name": "我喜欢"}, {"id": work["id"], "name": "上班"}]
    r = client.post("/api/inbox", json={**BODY, "album": work["id"]}, headers=key)
    assert r.status_code == 200
    # in the 图集 already; it shows there once indexed (and, with little text, once kept in 待确认)
    assert r.json()["id"] in (inbox.library.root / "collections.json").read_text(encoding="utf-8")
    before = sorted(p.name for p in inbox.folder.iterdir())
    bad = client.post("/api/inbox", json={**BODY, "image": _png((1, 2, 3)), "album": "nope"}, headers=key)
    assert bad.status_code == 404 and sorted(p.name for p in inbox.folder.iterdir()) == before  # nothing stored
