import json
import re

from memeseeks import splash


def test_the_splash_needs_nothing_from_the_server(tmp_path):
    page = splash.html(tmp_path)
    assert page.count("data:font/woff2;base64,") == 2 and "window.POPCAT" in page and "Frame.draw" in page
    assert not re.search(r'(src|href)="(?!data:)[^"]+"', page)  # nothing to fetch: the server is not up yet
    assert "<html lang=\"zh-CN\">" in page and "正在启动" in page


def test_the_splash_follows_the_librarys_look(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"theme": "night", "frame": False, "motion": "reduced"}), encoding="utf-8")
    assert '<html lang="zh-CN" data-theme="night" data-frame="off" data-motion="reduced">' in splash.html(tmp_path)
    (tmp_path / "settings.json").write_text("not json", encoding="utf-8")
    assert splash.looks(tmp_path) == {"theme": "paper", "frame": True, "motion": "full"}
