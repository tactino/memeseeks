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


def _png(rgb) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), rgb).save(buf, "PNG")
    return buf.getvalue()


def _setup(tmp_path):
    """Three memes in your own folder: red (猫猫), blue (狗狗), a second red one (猫猫, similar to the first)."""
    lib = Library(tmp_path / "lib")
    solid(tmp_path / "album", "cat.png", (255, 0, 0))
    solid(tmp_path / "album", "cat2.png", (250, 5, 5))
    solid(tmp_path / "album", "dog.png", (0, 0, 255))
    lib.add_source(tmp_path / "album")
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    now = [0.0]
    indexer = BackgroundIndexer(lib, models, debounce=0, clock=lambda: now[0], priority=contextlib.nullcontext)
    service = LibraryService(lib, models, rng=random.Random(0))
    client = TestClient(create_app(service, inbox=Inbox(lib), indexer=indexer), base_url="http://127.0.0.1")
    ids = {name: next(i for i, p in lib.paths().items() if p.endswith(name)) for name in ("cat.png", "cat2.png", "dog.png")}
    return client, lib, indexer, ids


def test_album_lifecycle(tmp_path):
    client, _, _, ids = _setup(tmp_path)
    listed = client.get("/api/albums").json()
    assert [(a["id"], a["name"], a["count"]) for a in listed] == [("all", "全部", 3), ("liked", "我喜欢", 0)]
    work = client.post("/api/albums", json={"name": "猫"}).json()
    assert client.post(f"/api/albums/{work['id']}/add", json={"ids": [ids["cat.png"], ids["cat2.png"], "nope"]}).json() == {"added": 2}
    got = client.get(f"/api/albums/{work['id']}").json()
    assert [i["id"] for i in got["items"]] == [ids["cat2.png"], ids["cat.png"]]            # newest first
    assert [i["id"] for i in client.get(f"/api/albums/{work['id']}", params={"sort": "old"}).json()["items"]] == [ids["cat.png"], ids["cat2.png"]]
    assert got["items"][0]["thumb"].startswith("/api/thumb/")
    cover = [a for a in client.get("/api/albums").json() if a["id"] == work["id"]][0]["cover"]
    assert cover == f"/api/thumb/{ids['cat2.png']}"
    assert client.patch(f"/api/albums/{work['id']}", json={"name": "猫猫"}).json()["name"] == "猫猫"
    assert client.post(f"/api/albums/{work['id']}/remove", json={"ids": [ids["cat.png"]]}).json() == {"removed": 1}
    assert client.delete(f"/api/albums/{work['id']}").status_code == 200
    assert client.get(f"/api/albums/{work['id']}").status_code == 404


def test_liking_and_the_meme_page(tmp_path):
    client, _, _, ids = _setup(tmp_path)
    client.post("/api/albums/liked/add", json={"ids": [ids["cat.png"]]})
    page = client.get(f"/api/meme/{ids['cat.png']}").json()
    assert page["liked"] is True and page["albums"] == ["liked"] and page["image"].startswith("/api/image/")
    assert [s["id"] for s in page["similar"]] == [ids["cat2.png"]]          # the other 猫猫, not the 狗狗
    assert page["similar"][0]["thumb"].startswith("/api/thumb/")
    assert client.get("/api/meme/nope").status_code == 404


def test_removing_your_own_file_hides_it_and_keeps_it_on_disk(tmp_path):
    client, lib, _, ids = _setup(tmp_path)
    client.post("/api/albums/liked/add", json={"ids": [ids["dog.png"]]})
    assert client.post("/api/memes/remove", json={"ids": [ids["dog.png"]]}).json() == {"removed": 1}
    assert (tmp_path / "album" / "dog.png").exists()
    assert client.get(f"/api/meme/{ids['dog.png']}").status_code == 404
    assert ids["dog.png"] not in {h["id"] for h in client.get("/api/search", params={"q": "狗", "maybe": 10}).json()["maybe"]}
    albums = {a["id"]: a["count"] for a in client.get("/api/albums").json()}
    assert albums == {"all": 2, "liked": 0}                                 # gone from 我喜欢 too


def test_upload_goes_straight_into_the_library_and_an_album(tmp_path):
    client, lib, indexer, _ = _setup(tmp_path)
    work = client.post("/api/albums", json={"name": "上传的"}).json()
    r = client.post("/api/upload", params={"album": work["id"]}, content=_png((0, 255, 0)),
                    headers={"Content-Type": "image/png"})
    assert r.status_code == 200 and r.json()["status"] == "added"
    assert indexer.tick() is True
    new = r.json()["id"]
    assert new in lib.paths()
    assert [i["id"] for i in client.get(f"/api/albums/{work['id']}").json()["items"]] == [new]
    assert client.get("/api/review").json()["pending"] == []                # chosen by you: no 待确认
    assert client.get(f"/api/meme/{new}").json()["sources"][0]["site"] == "上传"


def test_upload_and_changes_refuse_what_other_sites_could_send(tmp_path):
    client, _, _, ids = _setup(tmp_path)
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    assert client.post("/api/upload", content=_png((0, 255, 0)), headers=form).status_code == 415
    assert client.post("/api/albums", content="name=x", headers=form).status_code == 415
    assert client.post("/api/memes/remove", content='{"ids": []}', headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/upload", params={"album": "nope"}, content=_png((0, 255, 0)),
                       headers={"Content-Type": "image/png"}).status_code == 404
    assert client.post("/api/upload", content=b"not an image", headers={"Content-Type": "image/png"}).status_code == 400
    assert client.post("/api/albums/liked/add", json={"ids": "all"}).status_code == 400
    assert client.post("/api/albums", json={"name": ""}).status_code == 400
    assert client.delete("/api/albums/liked").status_code == 400


def test_settings_round_trip(tmp_path):
    client, _, _, _ = _setup(tmp_path)
    assert client.get("/api/settings").json()["theme"] == "paper"
    assert client.put("/api/settings", json={"theme": "night", "frame": False}).json()["frame"] is False
    assert client.get("/api/settings").json()["theme"] == "night"
    assert client.put("/api/settings", json={"theme": "pink"}).status_code == 400


def test_numbers_are_given_once_in_arrival_order_and_never_change(tmp_path):
    import os
    client, lib, indexer, ids = _setup(tmp_path)
    for k, name in enumerate(("dog.png", "cat.png", "cat2.png")):       # set arrival order by mtime
        os.utime(tmp_path / "album" / name, (1000 + k, 1000 + k))
    nos = {h["id"]: h["no"] for h in client.get("/api/albums/all").json()["items"]}
    assert sorted(nos.values()) == [1, 2, 3]
    solid(tmp_path / "album", "old.png", (0, 255, 0))
    os.utime(tmp_path / "album" / "old.png", (1, 1))                      # older than everything
    lib.update(Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge()), log=lambda m: None)
    again = {h["id"]: h["no"] for h in client.get("/api/albums/all").json()["items"]}
    assert all(again[i] == n for i, n in nos.items()) and max(again.values()) == 4


def test_today_is_one_meme_with_text_and_stable_for_the_day(tmp_path):
    client, _, _, ids = _setup(tmp_path)
    first, second = client.get("/api/today").json(), client.get("/api/today").json()
    assert first["id"] == second["id"] and first["text"] and first["thumb"].startswith("/api/thumb/")


def test_source_folders_can_be_added_and_removed_from_the_web_app(tmp_path):
    client, lib, indexer, ids = _setup(tmp_path)
    listed = client.get("/api/sources").json()
    assert any(s["path"].endswith("album") and s["exists"] and not s["inbox"] for s in listed)
    more = tmp_path / "more"
    solid(more, "frog.png", (0, 255, 0))
    assert client.post("/api/sources", json={"path": str(more)}).status_code == 200
    assert indexer.tick() is True and len(lib.paths()) == 4
    assert client.post("/api/sources", json={"path": str(tmp_path / "nope")}).status_code == 400
    assert client.post("/api/sources/remove", json={"path": str(more)}).status_code == 200
    assert indexer.tick() is True and len(lib.paths()) == 3
    assert (more / "frog.png").exists()                                     # files are never touched
    inbox_dir = [s for s in client.get("/api/sources").json() if s["inbox"]]
    if inbox_dir:
        assert client.post("/api/sources/remove", json={"path": inbox_dir[0]["path"]}).status_code == 400


def test_custom_css_is_served_from_the_library(tmp_path):
    client, lib, _, _ = _setup(tmp_path)
    empty = client.get("/api/custom.css")
    assert empty.status_code == 200 and empty.text == "" and empty.headers["content-type"].startswith("text/css")
    (lib.root / "custom.css").write_text(":root { --accent: hotpink; }", encoding="utf-8")
    assert "hotpink" in client.get("/api/custom.css").text


def test_heic_uploads_are_accepted(tmp_path):
    import pillow_heif
    client, _, _, _ = _setup(tmp_path)
    buf = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (16, 16), (10, 200, 30))).save(buf, format="HEIF")
    r = client.post("/api/upload", content=buf.getvalue(), headers={"Content-Type": "image/heic"})
    assert r.status_code == 200 and r.json()["status"] == "added"
