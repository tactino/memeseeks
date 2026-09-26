import io
import random

import pytest
from PIL import Image

from memeseeks.inbox import Inbox, InboxError, clean_meta, read_provenance
from memeseeks.indexer import BackgroundIndexer
from memeseeks.library import Library, Models
from memeseeks.service import LibraryService
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _png(rgb=(255, 0, 0), size=(8, 8)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "PNG")
    return buf.getvalue()


def _models():
    return Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())


def _no_priority():
    import contextlib
    return contextlib.nullcontext()


META = {"site": "贴吧", "page_url": "https://tieba.baidu.com/p/123", "page_title": "今日份梗图",
        "image_url": "https://tiebapic.baidu.com/forum/pic/item/abc.jpg"}


def test_received_image_keeps_its_bytes_and_the_scan_id(tmp_path):
    lib = Library(tmp_path / "lib")
    data = _png()
    got = Inbox(lib).receive(data, META)
    assert got["status"] == "added"
    saved = next((lib.root / "inbox").iterdir())
    assert saved.read_bytes() == data and saved.suffix == ".png"
    records, _ = lib.records()  # the inbox is a source, and the scan gives the same id
    assert [r.id for r in records] == [got["id"]]


def test_same_image_twice_is_stored_once_but_both_sources_are_kept(tmp_path):
    lib = Library(tmp_path / "lib")
    inbox = Inbox(lib)
    first = inbox.receive(_png(), META)
    again = inbox.receive(_png(), dict(META, page_url="https://www.douban.com/group/topic/9/"))
    assert again == {"id": first["id"], "status": "duplicate"}
    assert len(list((lib.root / "inbox").iterdir())) == 1
    assert [s["page_url"] for s in read_provenance(lib.root)[first["id"]]] == [
        "https://tieba.baidu.com/p/123", "https://www.douban.com/group/topic/9/"]


def test_an_image_already_in_another_folder_is_a_duplicate(tmp_path):
    src = tmp_path / "album"
    solid(src, "cat.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    lib.update(_models(), log=lambda m: None)
    got = Inbox(lib).receive((src / "cat.png").read_bytes(), META)
    assert got["status"] == "duplicate"
    assert not list((lib.root / "inbox").iterdir())


@pytest.mark.parametrize("data", [b"not an image", b""])
def test_non_images_are_refused(tmp_path, data):
    with pytest.raises(InboxError):
        Inbox(Library(tmp_path / "lib")).receive(data, META)


def test_oversized_images_are_refused(tmp_path, monkeypatch):
    import memeseeks.inbox as inbox_mod
    monkeypatch.setattr(inbox_mod, "MAX_IMAGE_BYTES", 10)
    with pytest.raises(InboxError, match="larger"):
        Inbox(Library(tmp_path / "lib")).receive(_png(), META)


def test_meta_keeps_only_shown_fields_and_real_links():
    got = clean_meta({"site": " 小红书 ", "page_title": "标题\n换行" + "长" * 500, "page_url": "javascript:alert(1)",
                      "image_url": "https://sns-webpic.xhscdn.com/x.webp", "author": "someone", "cookie": "secret"})
    assert got["site"] == "小红书" and got["page_title"].startswith("标题 换行") and len(got["page_title"]) == 200
    assert "page_url" not in got and got["image_url"].startswith("https://")
    assert "author" not in got and "cookie" not in got


def test_key_is_long_random_and_stable(tmp_path):
    inbox = Inbox(Library(tmp_path / "lib"))
    assert len(inbox.key()) >= 32 and inbox.key() == inbox.key()
    assert inbox.key() != Inbox(Library(tmp_path / "other")).key()


def test_indexer_picks_up_new_files_after_a_quiet_moment(tmp_path):
    now = [100.0]
    src = tmp_path / "album"
    solid(src, "cat.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    lib.update(_models(), log=lambda m: None)
    idx = BackgroundIndexer(lib, _models(), debounce=3, clock=lambda: now[0], priority=_no_priority)
    assert idx.tick() is False  # first look only records the folders
    solid(src, "dog.png", (0, 0, 255))
    assert idx.tick() is False and idx.status()["pending"]  # noticed, but waits for more saves
    now[0] += 5
    assert idx.tick() is True
    assert len(lib.paths()) == 2 and idx.status() == {"pending": False, "running": False, "last_error": None,
                                                       "last_images": 2, "progress": None}
    assert idx.tick() is False  # nothing new


def test_indexer_request_indexes_the_inbox(tmp_path):
    now = [0.0]
    lib = Library(tmp_path / "lib")
    inbox = Inbox(lib)
    idx = BackgroundIndexer(lib, _models(), debounce=1, clock=lambda: now[0], priority=_no_priority)
    got = inbox.receive(_png((0, 0, 255)), META)
    idx.request()
    now[0] += 2
    assert idx.tick() is True and got["id"] in lib.paths()


def test_indexer_survives_a_failing_update(tmp_path):
    now = [0.0]
    lib = Library(tmp_path / "lib")

    class Boom(Models):
        def get(self, name):
            raise RuntimeError("model missing")

    solid(tmp_path / "album", "cat.png", (255, 0, 0))
    lib.add_source(tmp_path / "album")
    idx = BackgroundIndexer(lib, Boom(), debounce=0, clock=lambda: now[0], priority=_no_priority)
    idx.request()
    assert idx.tick() is True and "model missing" in idx.status()["last_error"]


def test_search_results_carry_where_a_meme_came_from(tmp_path):
    lib = Library(tmp_path / "lib")
    got = Inbox(lib).receive(_png((255, 0, 0)), META)
    solid(tmp_path / "album", "dog.png", (0, 0, 255))
    lib.add_source(tmp_path / "album")
    lib.update(_models(), log=lambda m: None)
    service = LibraryService(lib, _models(), rng=random.Random(0))
    assert service.search("猫")["matches"] == []  # little text: it waits in 待确认 first
    service.decide(got["id"], "keep")
    hit = service.search("猫")["matches"][0]
    assert hit["id"] == got["id"]
    assert hit["source"] == {"site": "贴吧", "page_url": "https://tieba.baidu.com/p/123", "page_title": "今日份梗图"}
    assert "source" not in service.search("狗")["matches"][0]  # a meme from a folder has no recorded source
