"""Generate an offline page for writing E1 search queries against your own memes.

Usage: python tools/make_label_page.py <data dir containing my-memes/>
Open the generated label.html in a browser. Type what you would search, click the memes it
should find, press 添加. When done press 导出 and save queries.csv into the data folder,
replacing the old one.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from memeseeks.images import scan_folder

TEMPLATE = """<!doctype html><meta charset="utf-8"><title>梗图标注</title>
<style>
body{font:14px system-ui,sans-serif;margin:0;padding:16px;background:#fafafa;color:#222}
header{position:sticky;top:0;background:#fafafa;padding:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center;z-index:1}
input{font:inherit;padding:6px 8px;min-width:16em}
button{font:inherit;padding:6px 12px;cursor:pointer}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin-top:8px}
figure{margin:0;border:3px solid transparent;border-radius:6px;background:#fff;cursor:pointer}
figure.on{border-color:#2a7}
figure img{width:100%;height:140px;object-fit:contain;display:block}
figcaption{font-size:11px;padding:2px 4px;word-break:break-all;color:#666}
table{border-collapse:collapse;margin-top:12px}td{border:1px solid #ddd;padding:4px 8px}
</style>
<header>
  <input id="q" placeholder="想找回哪张图？比如：关于熬夜的、猫被剃头那张">
  <button id="add">添加</button><button id="export">导出 queries.csv</button>
  <span id="count"></span>
</header>
<table id="rows"></table>
<div id="grid"></div>
<script>
const DATA = __DATA__;
let rows = DATA.rows.map(r => ({q: r[0], files: r[1] ? r[1].split(/[;；]/).filter(Boolean) : []}));
const picked = new Set();
const grid = document.getElementById("grid");
for (const rel of DATA.images) {
  const fig = document.createElement("figure");
  const img = document.createElement("img");
  img.loading = "lazy";
  img.src = DATA.base + "/" + rel.split("/").map(encodeURIComponent).join("/");
  const cap = document.createElement("figcaption");
  cap.textContent = rel;
  fig.append(img, cap);
  fig.onclick = () => { picked.has(rel) ? picked.delete(rel) : picked.add(rel); fig.classList.toggle("on"); };
  grid.append(fig);
}
function draw() {
  const t = document.getElementById("rows");
  t.replaceChildren(...rows.map((r, i) => {
    const tr = document.createElement("tr");
    const del = document.createElement("button");
    del.textContent = "删除"; del.onclick = () => { rows.splice(i, 1); draw(); };
    for (const text of [r.q, r.files.join("；") || "（未选图）"]) {
      const td = document.createElement("td"); td.textContent = text; tr.append(td);
    }
    const td = document.createElement("td"); td.append(del); tr.append(td);
    return tr;
  }));
  document.getElementById("count").textContent = rows.length + " 条";
}
document.getElementById("add").onclick = () => {
  const q = document.getElementById("q").value.trim();
  if (!q) return;
  rows.push({q, files: [...picked]});
  picked.clear();
  document.querySelectorAll("figure.on").forEach(f => f.classList.remove("on"));
  document.getElementById("q").value = "";
  draw();
};
document.getElementById("export").onclick = () => {
  const cell = s => '"' + String(s).replace(/"/g, '""') + '"';
  const lines = [["搜索词", "期望的图（文件名，多张用分号隔开；想不起来可以留空）"], ...rows.map(r => [r.q, r.files.join(";")])];
  const text = "\\ufeff" + lines.map(l => l.map(cell).join(",")).join("\\r\\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type: "text/csv"}));
  a.download = "queries.csv";
  a.click();
};
draw();
</script>
"""


def render_page(relpaths: list[str], image_dir_name: str, existing_rows: list[list[str]]) -> str:
    payload = json.dumps({"images": relpaths, "rows": existing_rows, "base": image_dir_name}, ensure_ascii=False)
    return TEMPLATE.replace("__DATA__", payload.replace("</", "<\\/"))


def _read_rows(csv_path: Path) -> list[list[str]]:
    if not csv_path.exists():
        return []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))[1:]
    return [[r[0].strip(), r[1].strip() if len(r) > 1 else ""] for r in rows if r and r[0].strip()]


def main(data_dir: str) -> None:
    data = Path(data_dir)
    scan = scan_folder(data / "my-memes")
    html = render_page([r.relpath for r in scan.records], "my-memes", _read_rows(data / "queries.csv"))
    (data / "label.html").write_text(html, encoding="utf-8")
    print(f"wrote {data / 'label.html'} with {len(scan.records)} images "
          f"({len(scan.unreadable)} unreadable, {sum(map(len, scan.duplicates.values()))} duplicates skipped)")


if __name__ == "__main__":
    main(sys.argv[1])
