from memeseeks.tray import apply_config, choose_mirror, models_missing, read_config


def test_the_installers_launcher_json_says_where_the_library_and_models_are(tmp_path):
    path = tmp_path / "launcher.json"
    path.write_bytes('{"library": "D:\\\\梗图库", "models": "D:\\\\hf-cache", "other": 1}'.encode("utf-8-sig"))
    config = read_config(path)
    assert config == {"library": "D:\\梗图库", "models": "D:\\hf-cache"}  # read through the BOM; nothing else kept
    env = {}
    apply_config(config, env)
    assert env == {"MEMESEEKS_HOME": "D:\\梗图库", "HF_HOME": "D:\\hf-cache"}
    assert read_config(tmp_path / "missing.json") == {} and read_config(tmp_path) == {}


def test_the_mirror_is_asked_for_only_when_the_models_still_need_downloading_and_hugging_face_is_away(tmp_path):
    env = {"HF_HOME": str(tmp_path)}
    assert models_missing(str(tmp_path))
    choose_mirror(env, reachable=lambda: True)
    assert "HF_ENDPOINT" not in env
    choose_mirror(env, reachable=lambda: False)
    assert env["HF_ENDPOINT"] == "https://hf-mirror.com"
    for name in ("models--BAAI--bge-m3", "models--OFA-Sys--chinese-clip-vit-large-patch14-336px"):
        (tmp_path / "hub" / name).mkdir(parents=True)
    env = {"HF_HOME": str(tmp_path)}
    choose_mirror(env, reachable=lambda: (_ for _ in ()).throw(AssertionError("not asked")))
    assert "HF_ENDPOINT" not in env  # everything is here already: no need to ask anyone
    env = {"HF_HOME": str(tmp_path / "empty"), "HF_ENDPOINT": "https://example.org"}
    choose_mirror(env, reachable=lambda: False)
    assert env["HF_ENDPOINT"] == "https://example.org"  # yours wins


def test_a_second_start_finds_the_name_taken():
    import sys
    import uuid

    import pytest

    if sys.platform != "win32":
        pytest.skip("the name is a Windows mutex")
    from memeseeks.wintray import first_instance

    name = f"Local\\memeseeks-test-{uuid.uuid4().hex}"
    assert first_instance(name) is True
    assert first_instance(name) is False  # held by this process now: a second start would give way
