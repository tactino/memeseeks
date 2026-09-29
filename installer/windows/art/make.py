"""Draw the installer's pictures from the app's own cat, fonts and colours (docs/design.md), as PNGs next to
this file: the tall one beside the welcome and finish pages, and the small one in the corner of the others.

  python installer/windows/art/make.py      (needs playwright with chromium)

Each is drawn once in CSS pixels and saved at the sizes Inno Setup picks from for 100 %, 150 % and 250 % DPI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
WEB = (HERE.parents[2] / "src" / "memeseeks" / "web").as_uri()

HEAD = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{WEB}/tokens.css">
<script src="{WEB}/popcat.js"></script><script src="{WEB}/cat.js"></script>
<style>
  html, body {{ margin: 0; background: transparent; }}
  .pic {{ position: relative; overflow: hidden; }}
  .pic > * {{ position: absolute; }}
  .ink {{ background: var(--ink); }}
</style></head><body>"""

# Mondrian: planes first, then black lines that run edge to edge or into another line (docs/design.md)
SIDE = HEAD + """
<div class="pic" id="pic" style="width:202px;height:386px;background:var(--paper)">
  <div style="left:168px;top:0;width:30px;height:70px;background:var(--accent)"></div>
  <div style="left:168px;top:164px;width:30px;height:72px;background:var(--red)"></div>
  <div style="left:0;top:336px;width:58px;height:46px;background:var(--blue)"></div>
  <div style="left:154px;top:336px;width:44px;height:46px;background:var(--accent)"></div>
  <div class="ink" style="left:164px;top:0;width:4px;height:236px"></div>
  <div class="ink" style="left:164px;top:70px;width:34px;height:4px"></div>
  <div class="ink" style="left:164px;top:160px;width:34px;height:4px"></div>
  <div class="ink" style="left:0;top:236px;width:202px;height:6px"></div>
  <div class="ink" style="left:0;top:332px;width:202px;height:4px"></div>
  <div class="ink" style="left:58px;top:336px;width:4px;height:46px"></div>
  <div class="ink" style="left:150px;top:336px;width:4px;height:46px"></div>
  <!-- the panel's own edges, so no line or block stops short where the page begins -->
  <div class="ink" style="left:198px;top:0;width:4px;height:386px"></div>
  <div class="ink" style="left:0;top:382px;width:202px;height:4px"></div>
  <svg class="cat" style="left:18px;top:52px;width:128px;height:128px"></svg>
  <div id="name" style="left:0;top:256px;width:198px;text-align:center">
    <div id="zh" style="display:inline-block;font:900 36px/1.1 var(--font-serif);color:var(--ink);letter-spacing:.02em">迷因捕手</div>
    <div id="en" style="display:flex;justify-content:space-between;margin:8px auto 0;font:700 11px/1 var(--font-mono);color:var(--ink)"></div>
  </div>
</div>
<script>
  Cat.draw(document.querySelector("svg.cat"), {});
  const en = document.getElementById("en");
  for (const c of "MEMESEEKS") en.append(Object.assign(document.createElement("i"), { textContent: c, style: "font-style:normal" }));
  document.fonts.ready.then(() => { en.style.width = document.getElementById("zh").getBoundingClientRect().width + "px"; });
</script></body></html>"""

SMALL = HEAD + """
<div class="pic" id="pic" style="width:58px;height:58px"><svg class="cat" style="left:0;top:0;width:58px;height:58px"></svg></div>
<script>Cat.draw(document.querySelector("svg.cat"), {});</script></body></html>"""


async def render(page, html: str, width: int, sizes: list[int], name: str) -> None:
    for size in sizes:
        scale = size / width
        ctx = await page.context.browser.new_context(device_scale_factor=scale, viewport={"width": 800, "height": 1200})
        p = await ctx.new_page()
        page_file = HERE / "_render.html"  # a file:// page, so it may load the app's file:// fonts and scripts
        page_file.write_text(html, encoding="utf-8")
        await p.goto(page_file.as_uri())
        await p.evaluate("document.fonts.ready")
        await p.wait_for_timeout(300)
        out = HERE / f"{name}-{size}.png"
        await p.locator("#pic").screenshot(path=str(out), omit_background=True)
        print(out.name)
        await ctx.close()
        page_file.unlink()


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await render(page, SIDE, 202, [202, 336, 534], "wizard")
        await render(page, SMALL, 58, [58, 97, 159], "small")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
