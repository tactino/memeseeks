import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_inbox_api import _setup

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "memeseeks" / "browser" / "memeseeks.user.js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def test_served_script_carries_this_server_and_the_inbox_key(tmp_path):
    client, inbox, _, _ = _setup(tmp_path)
    r = client.get("/api/inbox/memeseeks.user.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert "__MEMESEEKS_" not in r.text
    assert f'const SERVER = "http://127.0.0.1";' in r.text and json.dumps(inbox.key()) in r.text
    assert "// ==UserScript==" in r.text.splitlines()[0]  # what makes userscript managers offer to install it


def test_served_script_needs_the_token_when_there_is_one(tmp_path):
    client, _, _, _ = _setup(tmp_path, token="a-long-enough-token-123")
    assert client.get("/api/inbox/memeseeks.user.js").status_code == 401


@needs_node
def test_served_script_is_valid_javascript(tmp_path):
    client, _, _, _ = _setup(tmp_path)
    out = tmp_path / "served.user.js"
    out.write_text(client.get("/api/inbox/memeseeks.user.js").text, encoding="utf-8")
    subprocess.run([NODE, "--check", str(out)], check=True, capture_output=True)


@needs_node
def test_page_reading_rules():
    harness = f"""
    const m = require({json.dumps(str(SCRIPT))});
    const out = {{
      douban: m.doubanLarge("https://img1.doubanio.com/view/group_topic/m/public/p123.webp"),
      doubanKeepsLarge: m.doubanLarge("https://img1.doubanio.com/view/group_topic/l/public/p9.jpg"),
      xhs: m.xhsImageUrl({{urlDefault: "d", infoList: [{{imageScene: "WB_PRV", url: "p"}}, {{imageScene: "WB_DFT", url: "full"}}]}}),
      xhsFallback: m.xhsImageUrl({{urlPre: "pre"}}),
      xhsHttps: m.absolute("http://sns-webpic-qc.xhscdn.com/a/b!nd", "https://www.xiaohongshu.com/explore/1"),
      otherHttp: m.absolute("http://example.com/a.png", "https://example.com/"),
      relative: m.absolute("/img/a.png", "https://tieba.baidu.com/p/1"),
      js: m.absolute("javascript:alert(1)", "https://x.com/"),
      big: m.looksLikeContent(600, 800), icon: m.looksLikeContent(48, 48), banner: m.looksLikeContent(1200, 90),
      sites: ["tieba.baidu.com", "www.xiaohongshu.com", "www.douban.com", "weibo.com", "nottieba.baidu.com.evil.io"].map(m.siteOf),
    }};
    console.log(JSON.stringify(out));
    """
    got = json.loads(subprocess.run([NODE, "-e", harness], check=True, capture_output=True, text=True).stdout)
    assert got["douban"] == "https://img1.doubanio.com/view/group_topic/l/public/p123.webp"
    assert got["doubanKeepsLarge"].endswith("/l/public/p9.jpg")
    assert got["xhs"] == "full" and got["xhsFallback"] == "pre"
    assert got["xhsHttps"].startswith("https://sns-webpic-qc.xhscdn.com/") and got["otherHttp"].startswith("http://")
    assert got["relative"] == "https://tieba.baidu.com/img/a.png" and got["js"] is None
    assert (got["big"], got["icon"], got["banner"]) == (True, False, False)
    assert got["sites"] == ["tieba", "xiaohongshu", "douban", "generic", "generic"]
