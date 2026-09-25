import random

from fastapi.testclient import TestClient

from memeseeks.library import Library, Models
from memeseeks.server import create_app
from memeseeks.service import LibraryService
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _client(tmp_path, token=None, index=True):
    src = tmp_path / "src"
    solid(src, "cat.png", (255, 0, 0))
    solid(src, "dog.png", (0, 0, 255))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    if index:
        lib.update(models, log=lambda m: None)
    app = create_app(LibraryService(lib, models, rng=random.Random(0)), token=token)
    return TestClient(app, base_url="http://127.0.0.1"), lib


def test_search_returns_hits_with_image_urls(tmp_path):
    client, _ = _client(tmp_path)
    body = client.get("/api/search", params={"q": "狗"}).json()
    hits = body["matches"]
    assert [h["relpath"] for h in hits] == ["dog.png"] and hits[0]["thumb"].startswith("/api/thumb/")
    assert [h["relpath"] for h in body["maybe"]] == ["cat.png"]
    img = client.get(hits[0]["image"])
    assert img.status_code == 200 and img.headers["content-type"].startswith("image/")


def test_download_sets_attachment(tmp_path):
    client, lib = _client(tmp_path)
    some_id = next(iter(lib.paths()))
    r = client.get(f"/api/image/{some_id}", params={"download": 1})
    assert "attachment" in r.headers["content-disposition"]


def test_unknown_or_path_like_ids_are_404(tmp_path):
    client, _ = _client(tmp_path)
    for bad in ["nope", "..%2F..%2Fsecret", "%2E%2E"]:
        assert client.get(f"/api/image/{bad}").status_code == 404
        assert client.get(f"/api/thumb/{bad}").status_code == 404


def test_empty_library_is_a_409_with_message(tmp_path):
    client, _ = _client(tmp_path, index=False)
    r = client.get("/api/search", params={"q": "猫"})
    assert r.status_code == 409 and "memeseeks add" in r.json()["error"]


def test_rediscover_and_status(tmp_path):
    client, _ = _client(tmp_path)
    assert len(client.get("/api/rediscover", params={"n": 2}).json()) == 2
    assert client.get("/api/status").json()["images"] == 2


def test_index_page_is_served(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200 and "迷因捕手" in r.text


def test_token_protects_api_and_cookie_keeps_working(tmp_path):
    client, _ = _client(tmp_path, token="s3cret")
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/search", params={"q": "猫"}).status_code == 401
    assert client.get("/api/status", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/", params={"token": "wrong"}).status_code == 200  # page loads, no cookie
    assert client.get("/api/status").status_code == 401
    client.get("/", params={"token": "s3cret"})
    assert client.get("/api/status").status_code == 200


def test_image_routes_need_the_token_too(tmp_path):
    client, lib = _client(tmp_path, token="s3cret")
    some_id = next(iter(lib.paths()))
    assert client.get(f"/api/image/{some_id}").status_code == 401
    assert client.get(f"/api/thumb/{some_id}").status_code == 401


def test_static_assets_make_no_external_requests():
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "src" / "memeseeks" / "web"
    loaded = [f for f in web.rglob("*") if f.suffix in {".html", ".js", ".css", ".svg", ".webmanifest"}]
    assert len(loaded) >= 6
    for f in loaded:  # what the page fetches (font licence texts mention URLs but are never loaded)
        text = f.read_text(encoding="utf-8").replace('xmlns="http://www.w3.org/2000/svg"', "")  # a namespace, not a fetch
        assert not re.search(r"https?://", text), f.name


def test_right_link_works_even_with_a_stale_cookie(tmp_path):
    client, _ = _client(tmp_path, token="new")
    client.cookies.set("memeseeks_token", "old")
    client.get("/", params={"token": "new"})
    assert client.get("/api/status").status_code == 200


def test_webp_is_served_with_an_image_type(tmp_path):
    client, lib = _client(tmp_path)
    src = tmp_path / "src"
    solid(src, "w.webp", (0, 255, 0))
    from memeseeks.library import Models
    lib.update(Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge()), log=lambda m: None)
    webp_id = next(i for i, p in lib.paths().items() if p.endswith("w.webp"))
    assert client.get(f"/api/image/{webp_id}").headers["content-type"] == "image/webp"


def test_foreign_host_header_is_rejected_without_a_token(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/status", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/api/status").status_code == 200


def test_service_worker_is_network_first_so_updates_are_never_stuck():
    import re
    from pathlib import Path
    sw = (Path(__file__).resolve().parents[1] / "src" / "memeseeks" / "web" / "sw.js").read_text(encoding="utf-8")
    handler = sw.split('addEventListener("fetch"', 1)[1]
    assert re.search(r"respondWith\(\s*fetch\(event\.request\)", handler)  # network first
    assert handler.index(".catch(") < handler.index("caches.match")         # cache only when offline
    assert '"memeseeks-shell-v1"' not in sw                                 # new name drops the old cache
