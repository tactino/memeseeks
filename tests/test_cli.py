import json

from memeseeks.cli import main
from memeseeks.library import Models
from tests.fakes import FakeBge, FakeClip, FakeOcr, solid


def _models():
    return Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())


def test_add_then_search_prints_ranked_paths(tmp_path, capsys):
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    solid(src, "dog.png", (0, 0, 255))
    lib = str(tmp_path / "lib")
    assert main(["--lib", lib, "add", str(src)], models=_models()) == 0
    capsys.readouterr()
    assert main(["--lib", lib, "search", "狗", "--json"], models=_models()) == 0
    out = json.loads(capsys.readouterr().out)
    assert [h["path"][-7:] for h in out["matches"]] == ["dog.png"] and len(out["maybe"]) == 1


def test_search_before_add_is_a_clear_error(tmp_path, capsys):
    assert main(["--lib", str(tmp_path / "none"), "search", "猫"], models=_models()) == 1
    err = capsys.readouterr().err
    assert "memeseeks add" in err and "Traceback" not in err


def test_add_missing_folder_is_a_clear_error(tmp_path, capsys):
    assert main(["--lib", str(tmp_path / "lib"), "add", str(tmp_path / "nope")], models=_models()) == 1
    assert "not a folder" in capsys.readouterr().err


def test_status_reports_counts(tmp_path, capsys):
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = str(tmp_path / "lib")
    main(["--lib", lib, "add", str(src)], models=_models())
    capsys.readouterr()
    assert main(["--lib", lib, "status"], models=_models()) == 0
    out = capsys.readouterr().out
    assert "images: 1" in out and "vlm: off" in out


def test_piped_output_is_utf8():
    import subprocess
    import sys
    import os
    from pathlib import Path
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))  # works without pip install
    out = subprocess.run([sys.executable, "-m", "memeseeks.cli", "--help"], capture_output=True, env=env)
    assert "迷因捕手" in out.stdout.decode("utf-8")


def test_add_interrupted_before_indexing_gives_a_message_not_a_traceback(tmp_path, capsys):
    from memeseeks.library import Library
    lib = Library(tmp_path / "lib")
    lib.index_dir.mkdir(parents=True)
    (lib.index_dir / "paths.json").write_text('{"abc": "/somewhere/x.png"}', encoding="utf-8")  # killed here
    assert main(["--lib", str(lib.root), "status"], models=_models()) == 0
    capsys.readouterr()
    assert main(["--lib", str(lib.root), "search", "猫"], models=_models()) == 1
    assert "memeseeks add" in capsys.readouterr().err


def test_update_loads_models_before_writing_anything(tmp_path):
    from memeseeks.library import Library, Models
    src = tmp_path / "s"
    solid(src, "r.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)

    class Boom:
        def get(self, name):
            raise KeyboardInterrupt  # Ctrl-C while a model loads

    import pytest
    with pytest.raises(KeyboardInterrupt):
        lib.update(Boom(), log=lambda m: None)
    assert lib.paths() == {}


class _NoGpuModels(Models):
    def get(self, name):
        if name == "vlm":
            raise RuntimeError("CUDA is not available")
        return super().get(name)


def _no_gpu():
    return _NoGpuModels(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge())


def test_vlm_that_cannot_load_is_not_switched_on(tmp_path, capsys):
    from memeseeks.library import Library
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = str(tmp_path / "lib")
    assert main(["--lib", lib, "add", str(src), "--vlm"], models=_no_gpu()) == 1
    assert "VLM" in capsys.readouterr().err and Library(lib).config()["vlm"] is False
    assert main(["--lib", lib, "add", str(src)], models=_no_gpu()) == 0


def test_library_with_vlm_on_still_indexes_when_vlm_breaks(tmp_path, capsys):
    from memeseeks.library import Library
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = Library(tmp_path / "lib")
    lib.add_source(src)
    lib.set_vlm(True)  # e.g. turned on on a GPU machine, now running on a laptop
    assert main(["--lib", str(lib.root), "add", str(src)], models=_no_gpu()) == 0
    assert "VLM" in capsys.readouterr().err and len(lib.paths()) == 1


def test_no_vlm_turns_it_off(tmp_path):
    from memeseeks.library import Library

    class FakeVlm:
        def describe(self, image):
            return {"画面": "猫"}

    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = str(tmp_path / "lib")
    models = Models(ocr=FakeOcr(), clip=FakeClip(), bge=FakeBge(), vlm=FakeVlm())
    assert main(["--lib", lib, "add", str(src), "--vlm"], models=models) == 0 and Library(lib).config()["vlm"]
    assert main(["--lib", lib, "add", str(src), "--no-vlm"], models=models) == 0
    assert Library(lib).config()["vlm"] is False


def test_failed_images_are_reported_and_can_be_retried(tmp_path, capsys):
    class SometimesOcr(FakeOcr):
        broken = True

        def __call__(self, image):
            if SometimesOcr.broken and image.getpixel((0, 0))[2] > 200:
                raise RuntimeError("ocr crashed")
            return super().__call__(image)

    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    solid(src, "dog.png", (0, 0, 255))
    lib = str(tmp_path / "lib")
    models = Models(ocr=SometimesOcr(), clip=FakeClip(), bge=FakeBge())
    assert main(["--lib", lib, "add", str(src)], models=models) == 0
    assert "1 image(s) failed" in capsys.readouterr().out
    main(["--lib", lib, "status"], models=models)
    assert "failed: ocr 1" in capsys.readouterr().out
    SometimesOcr.broken = False
    assert main(["--lib", lib, "add", str(src), "--retry-failed"], models=models) == 0
    capsys.readouterr()
    main(["--lib", lib, "search", "狗", "--json"], models=models)
    assert json.loads(capsys.readouterr().out)["matches"][0]["text"] == "狗狗"


def test_missing_csv_and_broken_library_json_are_clear_errors(tmp_path, capsys):
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = tmp_path / "lib"
    main(["--lib", str(lib), "add", str(src)], models=_models())
    capsys.readouterr()
    assert main(["--lib", str(lib), "eval", str(tmp_path / "nope.csv")], models=_models()) == 1
    assert "Traceback" not in capsys.readouterr().err
    (lib / "library.json").write_text("{not json", encoding="utf-8")
    assert main(["--lib", str(lib), "status"], models=_models()) == 1
    assert "library.json" in capsys.readouterr().err


def test_library_json_without_vlm_key_uses_defaults(tmp_path, capsys):
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = tmp_path / "lib"
    main(["--lib", str(lib), "add", str(src)], models=_models())
    (lib / "library.json").write_text(json.dumps({"sources": [str(src.resolve())]}), encoding="utf-8")
    capsys.readouterr()
    assert main(["--lib", str(lib), "status"], models=_models()) == 0
    assert "vlm: off" in capsys.readouterr().out


def test_k_must_be_positive(tmp_path, capsys):
    import pytest
    with pytest.raises(SystemExit):
        main(["--lib", str(tmp_path), "search", "猫", "-k", "0"], models=_models())


def test_status_flags_missing_source(tmp_path, capsys):
    import shutil
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = str(tmp_path / "lib")
    main(["--lib", lib, "add", str(src)], models=_models())
    shutil.rmtree(src)
    capsys.readouterr()
    main(["--lib", lib, "status"], models=_models())
    assert "missing:" in capsys.readouterr().out


def test_serve_refuses_non_local_host_without_token(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MEMESEEKS_TOKEN", raising=False)
    assert main(["--lib", str(tmp_path / "lib"), "serve", "--host", "0.0.0.0"], models=_models()) == 1
    assert "--token" in capsys.readouterr().err


def test_serve_without_the_serve_extra_says_how_to_install(tmp_path, capsys, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "uvicorn", None)  # import uvicorn -> ImportError
    assert main(["--lib", str(tmp_path / "lib"), "serve"], models=_models()) == 1
    assert "[serve]" in capsys.readouterr().err


def test_version_flag(capsys):
    import pytest

    import memeseeks
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0 and memeseeks.__version__ in capsys.readouterr().out


def test_run_indexes_then_serves(tmp_path, monkeypatch):
    import memeseeks.cli as cli
    from memeseeks.library import Library
    served = {}
    monkeypatch.setattr(cli, "_serve", lambda lib, models, host, port, token, **kw: served.update(host=host, port=port) or 0)
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = tmp_path / "lib"
    assert main(["--lib", str(lib), "run", str(src), "--port", "9000"], models=_models()) == 0
    assert len(Library(lib).paths()) == 1 and served == {"host": "127.0.0.1", "port": 9000}


def test_run_refuses_a_network_host_without_a_token_before_indexing(tmp_path, capsys, monkeypatch):
    from memeseeks.library import Library
    monkeypatch.delenv("MEMESEEKS_TOKEN", raising=False)
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = tmp_path / "lib"
    assert main(["--lib", str(lib), "run", str(src), "--host", "0.0.0.0"], models=_models()) == 1
    assert "--token" in capsys.readouterr().err and Library(lib).paths() == {}


def test_weak_or_placeholder_tokens_are_refused(tmp_path, capsys):
    for weak in ["short", "replace-with-a-long-random-string"]:
        assert main(["--lib", str(tmp_path / "lib"), "serve", "--host", "0.0.0.0", "--token", weak],
                    models=_models()) == 1
        assert "token" in capsys.readouterr().err


def test_add_of_an_empty_folder_loads_no_models(tmp_path, capsys):
    from memeseeks.library import Models

    class NoModels(Models):
        def get(self, name):
            raise AssertionError(f"loaded {name} for an empty folder")

    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["--lib", str(tmp_path / "lib"), "add", str(empty)], models=NoModels()) == 0
    assert "no images found" in capsys.readouterr().out


def test_search_without_confident_matches_says_so(tmp_path, capsys):
    src = tmp_path / "memes"
    solid(src, "cat.png", (255, 0, 0))
    lib = str(tmp_path / "lib")
    main(["--lib", lib, "add", str(src)], models=_models())
    capsys.readouterr()
    assert main(["--lib", lib, "search", "一只鸟"], models=_models()) == 0
    out = capsys.readouterr().out
    assert "没有把握" in out and "cat.png" in out


def test_online_search_needs_a_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MEMESEEKS_KLIPY_KEY", raising=False)
    assert main(["--lib", str(tmp_path / "lib"), "serve", "--online", "klipy"], models=_models()) == 1
    assert "MEMESEEKS_KLIPY_KEY" in capsys.readouterr().err


def test_online_klipy_is_passed_to_the_app(tmp_path, monkeypatch):
    import memeseeks.cli as cli
    monkeypatch.setenv("MEMESEEKS_KLIPY_KEY", "k-123")
    built = {}

    def fake_run(app, **kw):
        built["kw"] = kw

    import uvicorn
    monkeypatch.setattr(uvicorn, "run", fake_run)
    real = cli.create_online
    monkeypatch.setattr(cli, "create_online", lambda *a: built.update(online=real(*a)) or built["online"])
    assert main(["--lib", str(tmp_path / "lib"), "serve", "--online", "klipy"], models=_models()) == 0
    assert "/k-123/static-memes/search" in built["online"].search_url
    assert built["online"].params["customer_id"] == (tmp_path / "lib" / "online-customer-id").read_text()


def test_serve_opens_the_inbox_and_watches_folders(tmp_path, monkeypatch):
    import uvicorn

    from memeseeks.indexer import BackgroundIndexer
    from memeseeks.library import Library
    started, apps = [], []
    monkeypatch.setattr(BackgroundIndexer, "start", lambda self: started.append(self))
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: apps.append(app))
    lib = tmp_path / "lib"
    assert main(["--lib", str(lib), "serve"], models=_models()) == 0
    assert str((lib / "inbox").resolve()) in Library(lib).config()["sources"] and len(started) == 1
    assert any(getattr(r, "path", "") == "/api/inbox" for r in apps[0].routes)
    assert main(["--lib", str(lib), "serve", "--no-watch"], models=_models()) == 0
    assert len(started) == 1  # --no-watch starts no indexer


def test_open_waits_until_the_server_answers():
    from memeseeks.cli import _open_when_ready
    answers, opened = iter([False, False, True]), []
    assert _open_when_ready("http://127.0.0.1:1/", probe=lambda url: next(answers), opener=opened.append, step=0)
    assert opened == ["http://127.0.0.1:1/"]
    assert not _open_when_ready("http://127.0.0.1:1/", probe=lambda url: False, opener=opened.append, wait=0.05, step=0)
    assert len(opened) == 1


def test_nothing_answers_on_a_closed_port():
    from memeseeks.cli import _answers
    assert _answers("http://127.0.0.1:9/", timeout=0.5) is False


def test_open_on_a_running_server_just_opens_the_browser(tmp_path, monkeypatch):
    import webbrowser

    import uvicorn

    import memeseeks.cli as cli
    opened, ran = [], []
    monkeypatch.setattr(cli, "_answers", lambda url, timeout=1.0: True)
    monkeypatch.setattr(webbrowser, "open", opened.append)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: ran.append(app))
    assert main(["--lib", str(tmp_path / "lib"), "serve", "--open", "--port", "8799"], models=_models()) == 0
    assert opened == ["http://127.0.0.1:8799/"] and not ran
