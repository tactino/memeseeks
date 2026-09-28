import contextlib
import io
import json
import random
import zipfile

from fastapi.testclient import TestClient

from memeseeks.inbox import Inbox, read_provenance
from memeseeks.indexer import BackgroundIndexer
from memeseeks.library import Library, Models
from memeseeks.server import create_app
from memeseeks.service import LibraryService
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _library(root, colours):
    lib = Library(root / "lib")
    for name, rgb in colours.items():
        solid(root / "memes", name, rgb)
    lib.add_source(root / "memes")
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    indexer = BackgroundIndexer(lib, models, debounce=0, clock=lambda: 0.0, priority=contextlib.nullcontext)
    service = LibraryService(lib, models, rng=random.Random(0))
    inbox = Inbox(lib)
    client = TestClient(create_app(service, inbox=inbox, indexer=indexer), base_url="http://127.0.0.1")
    ids = {name: next(i for i, p in lib.paths().items() if p.endswith(name)) for name in colours}
    return client, lib, indexer, inbox, ids


def _shared(client, ids, names, name="打工人"):
    album = client.post("/api/albums", json={"name": name}).json()
    client.post(f"/api/albums/{album['id']}/add", json={"ids": [ids[n] for n in names]})
    res = client.get(f"/api/albums/{album['id']}/export")
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    assert "memeseeks.zip" in res.headers["content-disposition"]
    return res.content


def _import(client, data, ctype="application/zip"):
    return client.post("/api/albums/import", content=data, headers={"Content-Type": ctype})


def test_a_shared_album_arrives_whole_in_someone_elses_library(tmp_path):
    a, _, _, inbox_a, ids_a = _library(tmp_path / "a", {"cat.png": (255, 0, 0), "dog.png": (0, 0, 255)})
    inbox_a.note_source(ids_a["cat.png"], {"site": "小红书", "page_url": "https://www.xiaohongshu.com/explore/1"})
    data = _shared(a, ids_a, ["dog.png", "cat.png"])
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read("album.json"))
        assert manifest["name"] == "打工人" and [it["file"].split("/")[1][:16] for it in manifest["items"]] == [
            ids_a["dog.png"], ids_a["cat.png"]]  # the album's own order
        assert "memes" not in json.dumps(manifest["items"]) and tmp_path.name not in json.dumps(manifest)  # no paths
    b, lib_b, indexer_b, _, ids_b = _library(tmp_path / "b", {"dog.png": (0, 0, 255), "green.png": (0, 255, 0)})
    found = _import(b, data, "application/x-zip-compressed").json()  # what Windows browsers call a .zip
    assert found["album"]["name"] == "打工人" and found["added"] == 1 and found["duplicate"] == 1
    before = b.get(f"/api/albums/{found['album']['id']}").json()
    assert before["count"] == 1 and before["waiting"] == 1  # the new one is not indexed yet
    indexer_b.tick()
    album = b.get(f"/api/albums/{found['album']['id']}").json()
    assert [it["id"] for it in album["items"]] == [ids_a["cat.png"], ids_a["dog.png"]]  # newest first, as every 图集
    sources = read_provenance(lib_b.root)
    assert [s.get("site") for s in sources[ids_a["cat.png"]]] == ["图集分享", "小红书"]
    assert ids_b["dog.png"] not in sources  # one you already had keeps its own story
    assert ids_a["cat.png"] not in [m["id"] for m in b.get("/api/review").json()["pending"]]  # no 待确认


def test_a_name_you_already_use_gets_marked_as_shared(tmp_path):
    a, _, _, _, ids_a = _library(tmp_path / "a", {"cat.png": (255, 0, 0)})
    data = _shared(a, ids_a, ["cat.png"])
    b, _, _, _, _ = _library(tmp_path / "b", {"dog.png": (0, 0, 255)})
    b.post("/api/albums", json={"name": "打工人"})
    assert _import(b, data).json()["album"]["name"] == "打工人（分享）"
    assert _import(b, data).json()["album"]["name"] == "打工人（分享 2）"


def test_anything_but_a_shared_album_file_is_refused(tmp_path):
    b, lib_b, _, _, _ = _library(tmp_path / "b", {"dog.png": (0, 0, 255)})
    assert _import(b, b"not a zip").status_code == 400
    assert _import(b, b"{}", ctype="application/json").status_code == 415
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("album.json", json.dumps({"format": "memeseeks-album", "version": 1, "name": "坏的",
                                              "items": [{"file": "../../evil.png"}, {"file": "images/nope.png"}]}))
        zf.writestr("../../evil.png", b"x")
    res = _import(b, buf.getvalue())
    assert res.status_code == 400 and "没有能用的图" in res.json()["error"]
    assert not (lib_b.root.parent / "evil.png").exists()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("album.json", json.dumps({"format": "memeseeks-album", "version": 9, "items": []}))
    assert "更新" in _import(b, buf.getvalue()).json()["error"]
