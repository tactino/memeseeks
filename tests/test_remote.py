import io
import json
import subprocess
import tarfile

import pytest

from memeseeks import remote
from memeseeks.cli import main
from memeseeks.library import Library, Models
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


class FakeBox:
    """The GPU box: unpacks what is sent, "tidies" each image, and keeps the commands it was given."""

    def __init__(self):
        self.commands, self.sent, self.out = [], [], ""

    def run(self, command, data=None):
        self.commands.append(command)
        if data is not None:
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                self.sent = sorted(m.name for m in tar.getmembers())
        return self.out.encode("utf-8") if command.startswith("cat ") else b""

    def stream(self, command, on_line):
        self.commands.append(command)
        rows = []
        for k, name in enumerate(self.sent, 1):
            stem = name.rsplit(".", 1)[0]
            rows.append({"id": stem, "relpath": name, "value": f"- {stem} 说的话", "notes": {"梗": "电车难题"}})
            on_line(f"tidy: {k}/{len(self.sent)}")
        self.out = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def _library(tmp_path):
    src = tmp_path / "memes"
    solid(src, "red.png", (255, 0, 0)), solid(src, "blue.png", (0, 0, 255))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    lib.update(Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge()), log=lambda m: None)
    return lib


def _rows(lib, name):
    path = lib.index_dir / name
    return {r["id"]: r["value"] for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def test_only_memes_without_tidied_text_are_sent_and_both_answers_come_back(tmp_path):
    lib = _library(tmp_path)
    done, new = sorted(lib.paths())
    for name, value in (("tidy.jsonl", "已经整理过"), ("notes.jsonl", {"梗": ""})):
        (lib.index_dir / name).write_text(json.dumps({"id": done, "value": value}, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    box, seen = FakeBox(), []
    n = remote.run(lib, {"host": "box", "home": "~/memeseeks"}, ssh=box, progress=lambda *a: seen.append(a))
    assert n == 1 and box.sent == [f"{new}.png"]
    assert _rows(lib, "tidy.jsonl") == {done: "已经整理过", new: f"- {new} 说的话"}
    assert _rows(lib, "notes.jsonl") == {done: {"梗": ""}, new: {"梗": "电车难题"}}
    assert seen == [("tidy", 0, 1), ("tidy", 1, 1)]
    assert box.commands[-1].startswith("rm -rf ")  # the memes do not stay on the box
    assert remote.run(lib, {"host": "box", "home": "~/memeseeks"}, ssh=FakeBox()) == 0  # nothing new: no ssh


def test_the_library_update_sends_new_memes_there_and_an_unreachable_box_only_leaves_a_note(tmp_path, monkeypatch):
    lib = _library(tmp_path)
    lib.set_tidy_remote({"host": "box", "home": "~/memeseeks"})
    calls = []
    monkeypatch.setattr(remote, "run", lambda library, where, progress=None: calls.append(where))
    report = lib.update(Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge()), log=lambda m: None)
    assert calls == [{"host": "box", "home": "~/memeseeks"}] and "tidy_error" not in report

    def unreachable(library, where, progress=None):
        raise remote.RemoteError("ssh box: Connection timed out")

    monkeypatch.setattr(remote, "run", unreachable)
    report = lib.update(Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge()), log=lambda m: None)
    assert report["images"] == 2 and "Connection timed out" in report["tidy_error"]


def test_a_failed_ssh_says_why_and_changes_nothing(tmp_path, monkeypatch):
    lib = _library(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 255, b"", b"ssh: connect to host box port 22: Connection timed out\n"))
    with pytest.raises(remote.RemoteError, match="Connection timed out"):
        remote.run(lib, {"host": "box", "home": "~/memeseeks"})
    assert not (lib.index_dir / "tidy.jsonl").exists()


def test_paths_are_quoted_for_the_remote_shell_and_a_host_cannot_be_an_option():
    assert remote._q("~/my memes") == "\"$HOME\"/'my memes'" and remote._q("/data/m") == "/data/m"
    with pytest.raises(remote.RemoteError):
        remote.Ssh("-oProxyCommand=calc")


def test_the_command_saves_where_only_after_it_worked_and_off_forgets_it(tmp_path, monkeypatch, capsys):
    lib = _library(tmp_path)

    def unreachable(library, where, out=None, progress=None):
        raise remote.RemoteError("ssh box: Permission denied (publickey)")

    monkeypatch.setattr(remote, "run", unreachable)
    assert main(["--lib", str(lib.root), "tidy-remote", "--host", "box", "--home", "~/m"]) == 1
    assert "tidy_remote" not in lib.config() and "Permission denied" in capsys.readouterr().err
    monkeypatch.setattr(remote, "run", lambda library, where, out=None, progress=None: 2)
    assert main(["--lib", str(lib.root), "tidy-remote", "--host", "box", "--home", "~/m"],
                models=Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())) == 0
    assert lib.config()["tidy_remote"] == {"host": "box", "home": "~/m"} and "tidied 2 memes" in capsys.readouterr().out
    assert main(["--lib", str(lib.root), "tidy-remote", "--off"]) == 0 and "tidy_remote" not in lib.config()
