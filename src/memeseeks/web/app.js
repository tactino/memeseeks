"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  trap: $("trap"), q: $("q"), home: $("home"), homeGrid: $("home-grid"), shuffle: $("shuffle"),
  results: $("results"), resultsGrid: $("results-grid"), resultsTitle: $("results-title"), back: $("back"),
  notice: $("notice"), viewer: $("viewer"), viewerImg: $("viewer-img"), viewerText: $("viewer-text"),
  copy: $("copy"), save: $("save"), share: $("share"), close: $("close"), toast: $("toast"),
};

const canCopyImages = window.isSecureContext && navigator.clipboard && "write" in navigator.clipboard
  && typeof window.ClipboardItem === "function";
let current = null;

async function api(path) {
  const res = await fetch(path, { credentials: "same-origin" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `请求失败（${res.status}）`);
  return body;
}

function notice(text, isError = false) {
  els.notice.textContent = text;
  els.notice.classList.toggle("error", isError);
  els.notice.hidden = !text;
}

function toast(text) {
  els.toast.textContent = text;
  els.toast.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { els.toast.hidden = true; }, 1800);
}

function renderGrid(grid, items) {
  grid.replaceChildren(...items.map((item) => {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";
    const img = document.createElement("img");
    img.src = item.thumb;
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = item.text ? item.text.slice(0, 60) : "梗图";
    tile.append(img);
    tile.addEventListener("click", () => openViewer(item));
    return tile;
  }));
}

async function loadHome() {
  notice("");
  try {
    const items = await api("/api/rediscover?n=12");
    renderGrid(els.homeGrid, items);
    if (!items.length) notice("图库还是空的。在电脑上运行 memeseeks add <文件夹> 把梗图加进来。");
  } catch (err) {
    notice(err.message, true);
  }
}

function showHome() {
  els.results.hidden = true;
  els.home.hidden = false;
  notice("");
  history.replaceState(null, "", location.pathname);
}

async function search(query) {
  els.home.hidden = true;
  els.results.hidden = false;
  els.resultsTitle.textContent = "正在诱捕…";
  els.resultsGrid.replaceChildren();
  notice("");
  try {
    const items = await api(`/api/search?k=30&q=${encodeURIComponent(query)}`);
    els.trap.classList.remove("snap");
    void els.trap.offsetWidth;
    els.trap.classList.add("snap");
    els.resultsTitle.textContent = items.length ? `诱捕到 ${items.length} 张` : "没找到";
    renderGrid(els.resultsGrid, items);
    if (!items.length) notice("换个说法试试，或者直接写图里的字。");
    history.replaceState(null, "", `?q=${encodeURIComponent(query)}`);
  } catch (err) {
    els.resultsTitle.textContent = "出错了";
    notice(err.message, true);
  }
}

function openViewer(item) {
  current = item;
  els.viewerImg.src = item.image;
  els.viewerImg.alt = item.text ? item.text.slice(0, 120) : "梗图";
  els.viewerText.textContent = item.text || "";
  els.viewerText.hidden = !item.text;
  els.save.href = `${item.image}?download=1`;
  els.copy.hidden = !canCopyImages;
  els.share.hidden = !navigator.canShare;
  els.viewer.showModal();
}

async function imageFile(item) {
  const res = await fetch(item.image, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`读取原图失败（${res.status}）`);
  const blob = await res.blob();
  const name = item.relpath.split("/").pop() || "meme";
  return new File([blob], name, { type: blob.type || "image/jpeg" });
}

async function toPng(blob) {
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  canvas.getContext("2d").drawImage(bitmap, 0, 0);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("转换失败"))), "image/png"));
}

els.copy.addEventListener("click", async () => {
  try {
    const png = imageFile(current).then(toPng);  // pending promise: write() must run inside the click (Safari)
    await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
    toast("已复制");
  } catch (err) {
    toast(`复制失败：${err.message}`);
  }
});

els.share.addEventListener("click", async () => {
  try {
    const file = await imageFile(current);
    if (!navigator.canShare({ files: [file] })) throw new Error("这个浏览器不能分享图片，请用保存");
    await navigator.share({ files: [file] });
  } catch (err) {
    if (err.name !== "AbortError") toast(`分享失败：${err.message}`);
  }
});

els.close.addEventListener("click", () => els.viewer.close());
els.viewer.addEventListener("click", (event) => { if (event.target === els.viewer) els.viewer.close(); });
els.trap.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = els.q.value.trim();
  if (query) search(query);
  else showHome();
});
els.shuffle.addEventListener("click", loadHome);
els.back.addEventListener("click", () => { els.q.value = ""; showHome(); });

const initial = new URLSearchParams(location.search).get("q");
if (initial) {
  els.q.value = initial;
  search(initial);
}
loadHome();

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
