import contextlib
import io
import random

from fastapi.testclient import TestClient
from PIL import Image

from memeseeks.inbox import Inbox
from memeseeks.indexer import BackgroundIndexer
from memeseeks.library import Library, Models
from memeseeks.models.ocr import OcrLine
from memeseeks.review import Review
from memeseeks.server import create_app
from memeseeks.service import LibraryService
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid

LONG = "上班的时候想下班，下班的时候想睡觉，睡觉的时候想上班"


class TextOcr(FakeOcr):
    """Like FakeOcr, plus: green images carry a long caption (a text-heavy 梗图)."""

    def __call__(self, image):
        r, g, b = image.getpixel((0, 0))
        if g > 200 and r < 50 and b < 50:
            return [OcrLine(LONG, [[0, 0], [1, 0], [1, 1], [0, 1]], 0.9)]
        return super().__call__(image)


def _png(rgb) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), rgb).save(buf, "PNG")
    return buf.getvalue()


META = {"site": "百度贴吧", "page_url": "https://tieba.baidu.com/p/1", "page_title": "今日份"}


def _setup(tmp_path):
    """Folder: a blue meme (little text). Collected: red (little text) and green (long text)."""
    lib = Library(tmp_path / "lib")
    solid(tmp_path / "album", "blue.png", (0, 0, 255))
    lib.add_source(tmp_path / "album")
    inbox = Inbox(lib)
    red = inbox.receive(_png((255, 0, 0)), META)["id"]
    green = inbox.receive(_png((0, 255, 0)), META)["id"]
    models = Models(ocr=TextOcr(), clip=FakeClip(), bge=FakeBge())
    lib.update(models, log=lambda m: None)
    now = [0.0]
    indexer = BackgroundIndexer(lib, models, debounce=0, clock=lambda: now[0], priority=contextlib.nullcontext)
    service = LibraryService(lib, models, rng=random.Random(0))
    client = TestClient(create_app(service, inbox=inbox, indexer=indexer), base_url="http://127.0.0.1")
    return client, service, lib, indexer, red, green


def _all_ids(body):
    return {h["id"] for h in body["matches"] + body["maybe"]}


def test_only_collected_memes_with_little_text_wait_for_review(tmp_path):
    client, service, lib, _, red, green = _setup(tmp_path)
    blue = next(i for i, p in lib.paths().items() if p.endswith("blue.png"))
    pending = client.get("/api/review").json()["pending"]
    assert [p["id"] for p in pending] == [red]  # not green (text-heavy), not blue (your own folder)
    assert pending[0]["thumb"].startswith("/api/thumb/") and pending[0]["source"]["site"] == "百度贴吧"
    shown = _all_ids(client.get("/api/search", params={"q": "猫", "maybe": 10}).json())
    assert red not in shown and {green, blue} <= shown
    assert red not in {h["id"] for h in client.get("/api/rediscover", params={"n": 10}).json()}
    assert client.get("/api/status").json()["pending_review"] == 1


def test_keep_makes_it_searchable(tmp_path):
    client, _, _, _, red, _ = _setup(tmp_path)
    r = client.post("/api/review", json={"id": red, "decision": "keep"})
    assert r.json()["results"] == {red: "kept"} and r.json()["progress"]["decided"] == 1
    assert client.get("/api/review").json()["pending"] == []
    assert red in {h["id"] for h in client.get("/api/search", params={"q": "猫"}).json()["matches"]}


def test_reject_parks_the_file_and_undo_brings_it_back(tmp_path):
    client, _, lib, indexer, red, _ = _setup(tmp_path)
    r = client.post("/api/review", json={"id": red, "decision": "reject"})
    assert r.json()["results"] == {red: "rejected"}
    assert not list((lib.root / "inbox").glob(f"{red}.*")) and list((lib.root / "rejected").glob(f"{red}.*"))
    assert red not in _all_ids(client.get("/api/search", params={"q": "猫", "maybe": 10}).json())
    assert indexer.tick() is True and red not in lib.paths()  # re-indexing drops it from the library
    progress = client.get("/api/review").json()["progress"]
    assert (progress["decided"], progress["rejected"], progress["can_train"]) == (1, 1, False)
    assert client.post("/api/review", json={"id": red, "decision": "keep"}).json()["results"] == {red: "kept"}
    assert list((lib.root / "inbox").glob(f"{red}.*")) and indexer.tick() is True and red in lib.paths()
    assert red in {h["id"] for h in client.get("/api/search", params={"q": "猫"}).json()["matches"]}


def test_keep_all_in_one_request(tmp_path):
    client, _, _, _, red, green = _setup(tmp_path)
    r = client.post("/api/review", json={"ids": [red], "decision": "keep"})
    assert r.status_code == 200 and client.get("/api/review").json()["pending"] == []


def test_own_folder_memes_cannot_be_rejected_and_bad_requests_fail(tmp_path):
    client, _, lib, _, _, _ = _setup(tmp_path)
    blue = next(i for i, p in lib.paths().items() if p.endswith("blue.png"))
    r = client.post("/api/review", json={"id": blue, "decision": "reject"})
    assert r.status_code == 400 and (tmp_path / "album" / "blue.png").exists()
    assert client.post("/api/review", json={"id": "nope", "decision": "keep"}).status_code == 400
    assert client.post("/api/review", json={"id": blue, "decision": "maybe"}).status_code == 400
    assert client.post("/api/review", json={"decision": "keep"}).status_code == 400


def test_decisions_must_be_json_so_other_sites_cannot_send_them(tmp_path):
    client, _, _, _, red, _ = _setup(tmp_path)
    form = client.post("/api/review", content=f'{{"id": "{red}", "decision": "reject"}}',
                       headers={"Content-Type": "text/plain"})
    assert form.status_code == 415
    assert [p["id"] for p in client.get("/api/review").json()["pending"]] == [red]


def test_training_unlocks_after_enough_decisions(tmp_path):
    lib = Library(tmp_path / "lib")
    review = Review(lib)
    log = lib.root / "review.jsonl"
    lib.root.mkdir(parents=True)
    lines = [f'{{"id": "k{i}", "decision": "keep"}}' for i in range(160)]
    lines += [f'{{"id": "r{i}", "decision": "reject"}}' for i in range(40)]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert review.progress()["can_train"] is False  # 200 decisions but only 40 不要
    with log.open("a", encoding="utf-8") as f:
        f.writelines(f'{{"id": "r{i}", "decision": "reject"}}\n' for i in range(40, 50))
    assert review.progress()["can_train"] is True
