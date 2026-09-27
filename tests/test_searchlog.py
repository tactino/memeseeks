import csv
import json

from memeseeks.cli import main
from memeseeks.library import Models
from memeseeks.searchlog import FILE, SearchLog, export, sessions, summary
from tests.fakes import FakeBge, FakeClip, FakeOcr
from tests.test_albums_api import _setup


def _events():
    t = [0.0]
    log = SearchLog("unused", clock=lambda: t[0])
    events = []
    log.add = lambda e: events.append({"t": t[0], **e})  # keep them in memory
    log.search("猫猫", ["a", "b"], ["c"]); t[0] += 5
    log.act("猫猫", "b", "open", 2, "matches"); t[0] += 5
    log.act("猫猫", "b", "copy", 2, "matches"); t[0] += 5
    log.search("猫猫", ["a", "b"], ["c"]); t[0] += 60  # back to the results: the same search
    log.search("那只狗", [], ["a", "c"]); t[0] += 20  # nothing done with it...
    log.search("狗狗", ["c"], []); t[0] += 5  # ...but reworded, it is found
    log.act("狗狗", "c", "save", 1, "matches"); t[0] += 1000
    log.search("鸭子", [], ["a"])  # never found
    return events


def test_a_search_counts_once_and_what_was_done_after_it_says_what_it_was_for():
    rows = sessions(_events())
    assert [(r["q"], r["acted"]) for r in rows] == [("猫猫", ["b"]), ("那只狗", []), ("狗狗", ["c"]), ("鸭子", [])]
    assert summary(_events()) == {"searches": 4, "found": 2, "found_first": 1, "found_in_matches": 2,
                                  "found_in_maybe": 0, "missed_then_rephrased": 1, "nothing_acted": 2}


def test_it_writes_out_as_queries_for_eval_with_the_reworded_miss_counted_against_the_first_wording(tmp_path):
    out = tmp_path / "queries.csv"
    assert export(_events(), {"a": "a.png", "b": "b.png", "c": "c.png"}, out) == 3
    with out.open(encoding="utf-8-sig") as f:
        assert list(csv.reader(f)) == [["query", "expected"], ["猫猫", "b.png"], ["狗狗", "c.png"], ["那只狗", "c.png"]]


def test_nothing_is_kept_until_the_setting_is_on_and_then_searches_and_actions_are(tmp_path):
    client, lib, _, ids = _setup(tmp_path)
    client.get("/api/search?q=猫猫")
    assert client.post("/api/searchlog", json={"q": "猫猫", "id": ids["cat.png"], "action": "open"}).json() == {"logged": False}
    assert not (lib.root / FILE).exists()
    client.put("/api/settings", json={"searchlog": True})
    found = client.get("/api/search?q=猫猫").json()
    assert client.post("/api/searchlog", json={"q": "猫猫", "id": ids["cat.png"], "action": "copy", "rank": 1,
                                               "section": "matches"}).json() == {"logged": True}
    rows = [json.loads(line) for line in (lib.root / FILE).read_text(encoding="utf-8").splitlines()]
    assert rows[0]["type"] == "search" and rows[0]["matches"] == [m["id"] for m in found["matches"]]
    assert {k: rows[1][k] for k in ("type", "q", "id", "action", "rank", "section")} == {
        "type": "act", "q": "猫猫", "id": ids["cat.png"], "action": "copy", "rank": 1, "section": "matches"}
    assert client.post("/api/searchlog", json={"q": "猫猫", "id": ids["cat.png"], "action": "delete"}).status_code == 400
    assert client.post("/api/searchlog", json={"q": "猫猫", "id": "nope", "action": "open"}).status_code == 400


def test_the_command_sums_it_up_without_the_queries_and_exports_them(tmp_path, capsys):
    client, lib, _, ids = _setup(tmp_path)
    client.put("/api/settings", json={"searchlog": True})
    client.get("/api/search?q=猫猫")
    client.post("/api/searchlog", json={"q": "猫猫", "id": ids["cat.png"], "action": "open", "rank": 1, "section": "matches"})
    out = tmp_path / "q.csv"
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())
    assert main(["--lib", str(lib.root), "searchlog", "--export", str(out)], models=models) == 0
    printed = capsys.readouterr().out
    assert "1 searches" in printed and "猫猫" not in printed
    assert out.read_text(encoding="utf-8-sig").splitlines()[1] == "猫猫,cat.png"
