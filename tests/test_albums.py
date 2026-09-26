import json

import pytest

from memeseeks.albums import LIKED, CollectionError, Collections, Removed
from memeseeks.settings import Settings, SettingsError


def test_liked_always_exists_and_cannot_be_deleted_or_renamed(tmp_path):
    c = Collections(tmp_path)
    assert [x["id"] for x in c.all()] == [LIKED] and c.get(LIKED)["name"] == "我喜欢"
    with pytest.raises(CollectionError):
        c.delete(LIKED)
    with pytest.raises(CollectionError):
        c.rename(LIKED, "别的")


def test_create_rename_delete(tmp_path):
    c = Collections(tmp_path)
    work = c.create("  上班  梗 ")
    assert work["name"] == "上班 梗" and len(work["id"]) == 8
    with pytest.raises(CollectionError):
        c.create("上班 梗")                     # names are unique
    with pytest.raises(CollectionError):
        c.create("   ")
    with pytest.raises(CollectionError):
        c.create("长" * 41)
    assert c.rename(work["id"], "打工")["name"] == "打工"
    c.delete(work["id"])
    assert [x["id"] for x in c.all()] == [LIKED]
    with pytest.raises(CollectionError):
        c.get(work["id"])


def test_items_are_ids_in_order_without_duplicates(tmp_path):
    now = [100.0]
    c = Collections(tmp_path, clock=lambda: now[0])
    cid = c.create("猫")["id"]
    assert c.add(cid, ["a", "b", "a"]) == 2
    now[0] = 200.0
    assert c.add(cid, ["b", "c"]) == 1
    assert [(it["id"], it["added"]) for it in c.get(cid)["items"]] == [("a", 100.0), ("b", 100.0), ("c", 200.0)]
    c.add(LIKED, ["b"])
    assert sorted(c.containing("b")) == sorted([LIKED, cid])
    assert c.remove(cid, ["b", "zzz"]) == 1 and c.containing("b") == [LIKED]
    c.forget(["a", "b", "c"])
    assert all(not x["items"] for x in c.all())


def test_deleting_a_collection_keeps_the_memes_elsewhere(tmp_path):
    c = Collections(tmp_path)
    one, two = c.create("一")["id"], c.create("二")["id"]
    c.add(one, ["x"]); c.add(two, ["x"])
    c.delete(one)
    assert c.containing("x") == [two]


def test_file_is_versioned_and_survives_a_new_instance(tmp_path):
    Collections(tmp_path).create("存档")
    data = json.loads((tmp_path / "collections.json").read_text(encoding="utf-8"))
    assert data["version"] == 1 and [x["name"] for x in Collections(tmp_path).all()] == ["我喜欢", "存档"]


def test_a_damaged_file_is_reported_not_silently_replaced(tmp_path):
    (tmp_path / "collections.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CollectionError, match="damaged"):
        Collections(tmp_path).all()


def test_removed_ids_accumulate(tmp_path):
    r = Removed(tmp_path)
    assert r.ids() == set()
    r.add(["a"]); r.add(["b", "a"])
    assert r.ids() == {"a", "b"}


def test_settings_defaults_validation_and_bad_values_on_disk(tmp_path):
    s = Settings(tmp_path)
    assert s.get() == {"theme": "paper", "frame": True, "intro": True, "motion": "full", "online": True}
    assert s.update({"theme": "night", "intro": False})["theme"] == "night"
    assert Settings(tmp_path).get()["intro"] is False
    for bad in [{"theme": "pink"}, {"frame": "yes"}, {"frame": 1}, {"colour": "red"}]:
        with pytest.raises(SettingsError):
            s.update(bad)
    (tmp_path / "settings.json").write_text('{"theme": "neon", "motion": "reduced", "extra": 1}', encoding="utf-8")
    assert s.get() == {"theme": "paper", "frame": True, "intro": True, "motion": "reduced", "online": True}


def test_platform_watermarks_are_hidden_from_shown_text():
    from memeseeks.service import display_text
    assert display_text("我在凌晨3点躺在床上 小红书 小红书号：95037120793") == "我在凌晨3点躺在床上"
    assert display_text("我当我在网上搜完自己的症状 微博：@今日memes") == "我当我在网上搜完自己的症状"
    assert display_text("B站：@某某UP 那咋了") == "那咋了"
    assert display_text("小红书上看到的：救命") == "小红书上看到的：救命"     # the word inside a sentence stays
