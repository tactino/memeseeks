"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  trap: $("trap"), q: $("q"), home: $("home"), homeGrid: $("home-grid"), shuffle: $("shuffle"),
  results: $("results"), resultsGrid: $("results-grid"), resultsTitle: $("results-title"), back: $("back"),
  maybe: $("maybe"), maybeTitle: $("maybe-title"), maybeGrid: $("maybe-grid"),
  online: $("online"), onlineGrid: $("online-grid"), onlineSource: $("online-source"), onlineNotice: $("online-notice"),
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
    if (item instanceof Node) return item;
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

// Online search (off unless the server was started with --online). The provider's terms say the
// browser asks it directly, images load from its own URLs, and every result is shown as returned.
let onlineConfig = null;

async function getOnlineConfig() {
  if (!onlineConfig) onlineConfig = api("/api/online/config").catch(() => ({ enabled: false }));
  return onlineConfig;
}

function pickFile(files, sizes) {
  for (const size of sizes) {
    const set = files && files[size];
    const picked = set && (set.png || set.webp || set.jpg || set.gif);
    if (picked && picked.url) return picked.url;
  }
  return "";
}

function adTile(item) {
  const frame = document.createElement("iframe");
  frame.className = "tile ad";
  frame.title = "广告";
  frame.sandbox = "allow-scripts allow-popups allow-popups-to-escape-sandbox";  // no same-origin: can't touch this page
  frame.srcdoc = item.content || "";
  if (item.width && item.height) frame.style.aspectRatio = `${item.width} / ${item.height}`;
  return frame;
}

async function searchOnline(query) {
  els.onlineGrid.replaceChildren();
  els.onlineNotice.hidden = true;
  const config = await getOnlineConfig();
  if (!config.enabled) { els.online.hidden = true; return; }
  els.online.hidden = false;
  const credit = document.createElement("a");
  credit.href = config.attribution_url;
  credit.target = "_blank";
  credit.rel = "noopener";
  credit.textContent = `Powered by ${config.provider}`;
  els.onlineSource.replaceChildren(credit);
  try {
    const url = new URL(config.search_url);
    for (const [k, v] of Object.entries(config.params)) url.searchParams.set(k, v);
    url.searchParams.set("q", query);
    url.searchParams.set("page", "1");
    const res = await fetch(url, { credentials: "omit", referrerPolicy: "no-referrer" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || body.result === false) {
      const why = body.errors && body.errors.message ? [].concat(body.errors.message).join("；") : `HTTP ${res.status}`;
      throw new Error(`${config.provider} 搜索失败：${why}`);
    }
    const data = body.data && Array.isArray(body.data.data) ? body.data.data : [];
    const tiles = data.map((item) => {
      if (item.type === "ad") return adTile(item);
      const full = pickFile(item.file, ["hd", "md", "sm", "xs"]);
      const thumb = pickFile(item.file, ["md", "sm", "hd", "xs"]) || full;
      return { thumb, image: full, text: item.title || "", relpath: `klipy-${item.slug || item.id}`,
        online: { config, slug: item.slug || item.id, query } };
    });
    renderGrid(els.onlineGrid, tiles);
    if (!data.length) {
      els.onlineNotice.textContent = "网上也没找到。";
      els.onlineNotice.hidden = false;
    }
  } catch (err) {
    els.onlineNotice.textContent = err.message;
    els.onlineNotice.hidden = false;
  }
}

// Tell the provider a result was used (its terms ask for this); best effort, never blocks the user.
function reportShare(item) {
  if (!item || !item.online) return;
  const { config, slug, query } = item.online;
  fetch(`${config.share_url}${encodeURIComponent(slug)}`, {
    method: "POST", credentials: "omit", referrerPolicy: "no-referrer", keepalive: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: config.params.customer_id, q: query }),
  }).catch(() => {});
}

function showHome() {
  els.online.hidden = true;
  els.results.hidden = true;
  els.home.hidden = false;
  notice("");
  history.replaceState(null, "", location.pathname);
}

async function search(query) {
  els.home.hidden = true;
  els.results.hidden = false;
  els.resultsTitle.textContent = "正在搜捕…";
  els.resultsGrid.replaceChildren();
  els.maybe.hidden = true;
  notice("");
  try {
    searchOnline(query);  // in parallel; its own section, only shown when online search is on
    const { matches, maybe } = await api(`/api/search?q=${encodeURIComponent(query)}`);
    els.trap.classList.remove("snap");
    void els.trap.offsetWidth;
    els.trap.classList.add("snap");
    els.resultsTitle.textContent = matches.length ? `捕到 ${matches.length} 张` : "没有把握的结果";
    renderGrid(els.resultsGrid, matches);
    renderGrid(els.maybeGrid, maybe);
    els.maybeTitle.textContent = `可能相关（${maybe.length}）`;
    els.maybe.hidden = !maybe.length;
    els.maybe.open = !matches.length;
    if (!matches.length) notice("换个说法试试，或者直接写图里的字。下面是沾点边的：");
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
  els.save.href = item.online ? item.image : `${item.image}${item.image.includes("?") ? "&" : "?"}download=1`;
  els.copy.hidden = !canCopyImages;
  els.share.hidden = !navigator.canShare;
  els.viewer.showModal();
}

const EXT = { "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp" };

async function imageFile(item) {
  const res = await fetch(item.image, item.online ? { credentials: "omit", referrerPolicy: "no-referrer" }
    : { credentials: "same-origin" });
  if (!res.ok) throw new Error(`读取原图失败（${res.status}）`);
  const blob = await res.blob();
  let name = item.relpath.split("/").pop() || "meme";
  if (item.online) name += EXT[blob.type] || "";
  return new File([blob], name, { type: blob.type || "image/jpeg" });
}

// A cross-origin link ignores the download attribute, so online images are saved from a blob.
els.save.addEventListener("click", async (event) => {
  if (!current || !current.online) return;
  event.preventDefault();
  try {
    const file = await imageFile(current);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(file);
    link.download = file.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 10000);
    reportShare(current);
  } catch (err) {
    toast(`保存失败：${err.message}`);
  }
});

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
    reportShare(current);
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
    reportShare(current);
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
