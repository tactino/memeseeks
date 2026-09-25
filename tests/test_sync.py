import io
import tarfile

from scripts.sync import iter_files, write_tar


def test_tar_keeps_chinese_names_and_skips_excluded(tmp_path):
    (tmp_path / "梗图").mkdir()
    (tmp_path / "梗图" / "无语 猫.jpg").write_bytes(b"x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref")
    assert [rel for _, rel in iter_files(tmp_path, {".git"})] == ["梗图/无语 猫.jpg"]
    buf = io.BytesIO()
    assert write_tar(buf, tmp_path, {".git"}) == 1
    buf.seek(0)
    with tarfile.open(fileobj=buf) as tar:
        assert tar.getnames() == ["梗图/无语 猫.jpg"]


def test_remote_path_must_stay_inside_a_memeseeks_folder():
    import pytest
    from scripts.sync import check_remote
    assert check_remote("work/memeseeks") == "work/memeseeks"
    for bad in ["", "work", "/work/memeseeks", "~/memeseeks", "work/memeseeks; rm -rf ~", "a/../memeseeks"]:
        with pytest.raises(SystemExit):
            check_remote(bad)


def test_refuses_to_push_a_missing_or_empty_folder(tmp_path):
    import pytest
    from scripts.sync import check_source
    with pytest.raises(SystemExit):
        check_source(tmp_path / "nope")
    with pytest.raises(SystemExit):
        check_source(tmp_path)
    (tmp_path / "x.txt").write_text("x")
    check_source(tmp_path)


def test_remote_scripts_keep_every_cache_inside_the_project_folder():
    from pathlib import Path
    for name in ["scripts/remote.sh", "scripts/setup_remote.sh"]:
        text = Path(name).read_text(encoding="utf-8")
        for var in ["XDG_CACHE_HOME", "PIP_CACHE_DIR", "HF_HOME"]:
            value = text.split(f"{var}=", 1)[1].split()[0] if f"{var}=" in text else ""
            assert "memeseeks" in value or "$REMOTE" in value or "$R/" in value, (name, var)


def test_dev_env_file_is_read_and_real_env_wins(tmp_path, monkeypatch):
    from scripts.sync import load_dev_env
    f = tmp_path / ".memeseeks-dev.env"
    f.write_text("# comment\nMEMESEEKS_HOST=box\nMEMESEEKS_REMOTE=work/memeseeks\n\n", encoding="utf-8")
    monkeypatch.setenv("MEMESEEKS_HOST", "from-shell")
    monkeypatch.delenv("MEMESEEKS_REMOTE", raising=False)
    cfg = load_dev_env(f)
    assert cfg["MEMESEEKS_HOST"] == "from-shell" and cfg["MEMESEEKS_REMOTE"] == "work/memeseeks"


def test_sync_without_configuration_explains_what_to_set(tmp_path, monkeypatch):
    import pytest
    from scripts.sync import settings
    for key in ["MEMESEEKS_HOST", "MEMESEEKS_REMOTE", "MEMESEEKS_LOCAL_DATA"]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(SystemExit) as exc:
        settings(tmp_path / "missing.env", need_data=True)
    assert "MEMESEEKS_HOST" in str(exc.value)


def test_tracked_files_hold_none_of_the_local_dev_settings():
    """Whatever a maintainer configures locally (hosts, dirs) must never be committed.

    Denylist = the location keys of the gitignored .memeseeks-dev.env, plus $MEMESEEKS_PRIVATE_STRINGS
    (newline-separated; a CI secret). docs/superpowers/ (process notes) is excluded until the maintainer
    decides whether to publish it.
    """
    import os
    import subprocess
    from pathlib import Path

    import pytest
    from scripts.privacy import denylist_parts, find_leaks
    from scripts.sync import DEV_ENV, load_dev_env
    cfg = load_dev_env(DEV_ENV)
    values = [cfg.get(k, "") for k in ("MEMESEEKS_HOST", "MEMESEEKS_REMOTE", "MEMESEEKS_LOCAL_DATA")]
    values += os.environ.get("MEMESEEKS_PRIVATE_STRINGS", "").splitlines()
    parts = denylist_parts(values)
    if not parts:
        pytest.skip("no local .memeseeks-dev.env and no MEMESEEKS_PRIVATE_STRINGS")
    root = Path(__file__).resolve().parents[1]
    listing = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
    tracked = listing.stdout.split()
    assert listing.returncode == 0 and tracked, "git ls-files failed: the guard would pass vacuously"
    texts = {}
    for name in tracked:
        if name.startswith("docs/superpowers/"):
            continue
        try:
            texts[name] = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    assert find_leaks(texts, parts) == {}


def test_dev_env_strips_inline_comments_and_quotes(tmp_path, monkeypatch):
    from scripts.sync import load_dev_env
    for key in ["MEMESEEKS_HOST", "MEMESEEKS_REMOTE"]:
        monkeypatch.delenv(key, raising=False)
    f = tmp_path / ".memeseeks-dev.env"
    f.write_text('MEMESEEKS_HOST="box"   # ssh alias\nMEMESEEKS_REMOTE=work/memeseeks      # a folder\n', encoding="utf-8")
    cfg = load_dev_env(f)
    assert cfg["MEMESEEKS_HOST"] == "box" and cfg["MEMESEEKS_REMOTE"] == "work/memeseeks"


def test_local_env_files_never_travel_to_the_box(tmp_path):
    from scripts.sync import iter_files
    for name in [".env", ".memeseeks-dev.env", "keep.txt"]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert [rel for _, rel in iter_files(tmp_path, set())] == ["keep.txt"]


def test_denylist_parts_ignore_generic_words_and_stem_compounds():
    from scripts.privacy import denylist_parts
    assert denylist_parts(["work/memeseeks", "/path/to/private-memes-data"]) == set()
    parts = denylist_parts(["alicia-memeseeks", "bob/memeseeks", r"D:\\90210\\memeseeks-data"])
    assert parts == {"alicia", "90210"}  # "bob": too short to match safely


def test_find_leaks_matches_whole_words_only():
    from scripts.privacy import find_leaks
    texts = {"a.md": "the alice box", "b.py": "malice aforethought", "c.txt": "zip 90210"}
    assert find_leaks(texts, {"alice", "90210"}) == {"a.md": ["alice"], "c.txt": ["90210"]}
