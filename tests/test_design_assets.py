"""The design system's files: bundled fonts cover the UI text, icons exist, the cat's shapes can morph."""

import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "memeseeks" / "web"
BROWSER = WEB.parent / "browser"
CJK = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]")


def test_the_bundled_serif_covers_every_chinese_character_in_the_ui():
    covered = set((WEB / "fonts" / "serif-chars.txt").read_text(encoding="utf-8"))
    files = [*WEB.glob("*.html"), *WEB.glob("*.js"), *BROWSER.glob("*.js")]
    missing = {ch: f.name for f in files for ch in CJK.findall(f.read_text(encoding="utf-8")) if ch not in covered}
    assert not missing, f"UI text changed: run tools/fonts/subset.py (missing {''.join(sorted(missing))})"


def test_fonts_ship_with_their_licences():
    for name in ["memeseeks-serif.woff2", "memeseeks-mono.woff2", "NotoSerifSC-OFL.txt", "JetBrainsMono-OFL.txt"]:
        assert (WEB / "fonts" / name).stat().st_size > 1000, name
    assert (WEB / "fonts" / "memeseeks-serif.woff2").read_bytes()[:4] == b"wOF2"


def test_manifest_and_page_icons_exist():
    manifest = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert {i["purpose"] for i in manifest["icons"]} >= {"any", "maskable"}
    for icon in manifest["icons"]:
        assert (WEB / icon["src"]).is_file(), icon["src"]
    page = (WEB / "index.html").read_text(encoding="utf-8")
    for href in re.findall(r'<link rel="(?:icon|apple-touch-icon|stylesheet|manifest)" href="([^"]+)"', page):
        assert href.startswith("/api/") or (WEB / href).is_file(), href   # /api/custom.css is served from the library


def test_the_cats_two_states_can_morph_into_each_other():
    text = (WEB / "popcat.js").read_text(encoding="utf-8")
    cat = json.loads(text[text.index("{"):text.rindex("}") + 1])
    num = re.compile(r"-?\d+(?:\.\d+)?")
    shapes = [("eyes", 0), ("eyes", 1), ("nose", None), ("mouth", None)]
    for key, i in shapes:
        a = cat["closed"][key] if i is None else cat["closed"][key][i]
        b = cat["final"][key] if i is None else cat["final"][key][i]
        assert re.sub(num, "#", a) == re.sub(num, "#", b), f"{key}: the two states need the same commands"
    assert len(cat["mc"]) == 2 and cat["vb"].count(" ") == 3


def test_every_shell_file_the_service_worker_caches_exists():
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    files = re.findall(r'"([^"]+)"', sw[sw.index("const FILES"):sw.index("];")])
    for f in files:
        assert f == "./" or (WEB / f).is_file(), f
