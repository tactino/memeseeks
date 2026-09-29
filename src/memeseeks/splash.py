"""What the app's window shows while the server starts: the frame, the cat opening and shutting, 迷因捕手 and
正在启动…, in the library's theme. One self-contained page (the app's fonts, cat and frame inlined), since
nothing can be fetched yet; the window moves on to the web app as soon as the server answers.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
SLOW_MS = 12000  # the first start of a new install waits for Windows to check it: say so


def _font(name: str) -> str:
    return "data:font/woff2;base64," + base64.b64encode((WEB / "fonts" / name).read_bytes()).decode()


def looks(home: Path | None) -> dict:
    """The library's theme, frame and motion settings, as the web app would apply them."""
    try:
        saved = json.loads((Path(home) / "settings.json").read_text(encoding="utf-8")) if home else {}
    except (OSError, ValueError):
        saved = {}
    return {"theme": saved.get("theme", "paper"), "frame": saved.get("frame", True), "motion": saved.get("motion", "full")}


def html(home: Path | None = None) -> str:
    look = looks(home)
    tokens = (WEB / "tokens.css").read_text(encoding="utf-8")
    tokens = tokens.replace('url("fonts/memeseeks-serif.woff2")', f'url("{_font("memeseeks-serif.woff2")}")')
    tokens = tokens.replace('url("fonts/memeseeks-mono.woff2")', f'url("{_font("memeseeks-mono.woff2")}")')
    scripts = "".join(f"<script>{(WEB / name).read_text(encoding='utf-8')}</script>" for name in ("popcat.js", "cat.js", "frame.js"))
    attrs = (' data-theme="night"' if look["theme"] == "night" else "") + ("" if look["frame"] else ' data-frame="off"') + \
        (' data-motion="reduced"' if look["motion"] == "reduced" else "")
    return f"""<!doctype html><html lang="zh-CN"{attrs}><head><meta charset="utf-8"><title>迷因捕手</title>
<style>{tokens}
html, body {{ margin: 0; height: 100%; background: var(--paper); color: var(--ink); overflow: hidden; }}
#mframe {{ position: fixed; inset: 0; pointer-events: none; }}
main {{ height: 100%; display: grid; place-items: center; align-content: center; gap: 22px; font-family: var(--font-sans); }}
.lockup {{ display: flex; align-items: center; gap: 18px; }}
.cat {{ width: 112px; height: 112px; }}
.wordmark {{ display: inline-flex; flex-direction: column; line-height: 1; }}
.wordmark .zh {{ font: 900 52px/1 var(--font-serif); letter-spacing: .04em; }}
.wordmark .en {{ display: flex; justify-content: space-between; margin-top: 11px; font: 700 18px/1 var(--font-mono); }}
.wordmark .en i {{ font-style: normal; }}
.status {{ margin: 0; font-size: 15px; color: var(--muted); text-align: center; max-width: 30em; line-height: 1.7; }}
</style></head><body>
<main><div class="lockup"><svg class="cat" aria-hidden="true"></svg>
<span class="wordmark"><span class="zh">迷因捕手</span><span class="en">{"".join(f"<i>{c}</i>" for c in "MEMESEEKS")}</span></span></div>
<p class="status" id="status">正在启动…</p></main>
{scripts}
<script>
  Frame.draw(); addEventListener("resize", Frame.draw);
  const cat = Cat.draw(document.querySelector(".cat"), {{ closed: 1, bubble: 0 }});
  Cat.loop(cat);
  setTimeout(() => {{ document.getElementById("status").textContent =
    "正在启动…第一次启动时 Windows 会先检查一遍新装的程序，要多等一会儿。"; }}, {SLOW_MS});
</script></body></html>"""
