// ==UserScript==
// @name         迷因捕手
// @namespace    memeseeks
// @version      0.1.2
// @description  Collect the memes on the page you are reading into your own memeseeks library. Only acts when you click.
// @match        *://*/*
// @noframes
// @inject-into  auto
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        GM_getValue
// @grant        GM_setValue
// @connect      127.0.0.1
// @connect      localhost
// @connect      *
// ==/UserScript==

// What it does: when you click 采集 meme, it lists the images on the page you are looking at and sends the
// ones you tick to your memeseeks server. It never turns pages or runs on its own, and it sends
// nothing but the image, the site name, the page link and the page title.

(function () {
  "use strict";

  const SERVER = "__MEMESEEKS_SERVER__";
  const KEY = "__MEMESEEKS_KEY__";
  const MIN_SIDE = 150;       // smaller than this is an icon, avatar or sticker
  const MAX_ASPECT = 4;       // wider or taller than this is a banner or a divider
  const GAP_MS = 500;         // between two image downloads: about the pace of saving by hand

  // ---------- where the memes are, per site (pure functions; tested with node) ----------

  function absolute(url, base) {
    try {
      const u = new URL(url, base);
      if (u.protocol === "http:" && /(^|\.)xhscdn\.com$/.test(u.hostname)) u.protocol = "https:";
      return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
    } catch (e) {
      return null;
    }
  }

  function doubanLarge(url) {
    // /view/group_topic/{s,m,sqxs}/public/p1.webp -> the large version of the same picture
    return url.replace(/\/view\/group_topic\/(?:s|m|sqxs|xs)\//, "/view/group_topic/l/");
  }

  function xhsImageUrl(image) {
    // A note's image: the full-size default rendition when listed, else whatever url it has.
    if (!image) return null;
    const list = Array.isArray(image.infoList) ? image.infoList : [];
    const full = list.find((x) => x && x.imageScene === "WB_DFT" && x.url);
    return (full && full.url) || image.urlDefault || image.url || image.urlPre || null;
  }

  function looksLikeContent(w, h) {
    if (!w || !h || w < MIN_SIDE || h < MIN_SIDE) return false;
    return Math.max(w / h, h / w) <= MAX_ASPECT;
  }

  function siteOf(host) {
    if (/(^|\.)tieba\.baidu\.com$/.test(host)) return "tieba";
    if (/(^|\.)xiaohongshu\.com$/.test(host)) return "xiaohongshu";
    if (/(^|\.)douban\.com$/.test(host)) return "douban";
    return "generic";
  }

  const SITE_NAMES = { tieba: "百度贴吧", xiaohongshu: "小红书", douban: "豆瓣" };

  // ---------- reading the page ----------

  function pageObject(el) {
    // Page-side properties (Vue instances, state) are hidden from Firefox content scripts.
    return (el && el.wrappedJSObject) || el;
  }

  function shownSize(img) {
    const r = img.getBoundingClientRect();
    return [Math.max(img.naturalWidth || 0, r.width), Math.max(img.naturalHeight || 0, r.height)];
  }

  function imgUrl(img) {
    const src = img.currentSrc || img.src || "";
    return src.startsWith("data:") ? null : absolute(src, location.href);
  }

  function genericImages(root) {
    return [...(root || document).querySelectorAll("img")]
      .filter((img) => looksLikeContent(...shownSize(img)))
      .map((img) => ({ url: imgUrl(img), thumb: imgUrl(img) }));
  }

  function tiebaImages() {
    const found = [];
    // New PC pages: each picture is a LazyImage whose props hold the original URL, even before it loads.
    for (const wrap of document.querySelectorAll(".image-card-wrapper .lazy-img-wrapper")) {
      if (wrap.closest(".top-nav-bar, .frs-search-tag")) continue;
      const vue = pageObject(wrap).__vue__;
      const src = vue && vue.$props && vue.$props.src;
      const img = wrap.querySelector("img");
      const url = absolute(src || (img && imgUrl(img)) || "", location.href);
      if (url) found.push({ url, thumb: (img && imgUrl(img)) || url });
    }
    // Older page layout.
    for (const img of document.querySelectorAll("img.BDE_Image")) {
      const url = imgUrl(img);
      if (url) found.push({ url, thumb: url });
    }
    return found;
  }

  function xhsImages() {
    const id = (location.pathname.match(/\/(?:explore|discovery\/item)\/([0-9a-f]{16,})/) || [])[1];
    const state = pageObject(window).__INITIAL_STATE__;
    try {
      let map = state && state.note && state.note.noteDetailMap;
      map = map && (map.value || map._value || map);
      const entry = id && map && map[id];
      const note = entry && (entry.note || (entry.value && entry.value.note));
      const images = note && (note.imageList || []);
      if (images && images.length) {
        return {
          title: note.title || (note.desc || "").slice(0, 60),
          items: images.map(xhsImageUrl).map((u) => absolute(u, location.href)).filter(Boolean)
            .map((url) => ({ url, thumb: url })),
        };
      }
    } catch (e) { /* fall back to the page */ }
    const box = document.querySelector("#noteContainer, .note-container, .note-detail-mask");
    return { items: box ? genericImages(box) : [] };
  }

  function doubanImages() {
    const selectors = ".topic-content img, .topic-richtext img, #link-report img, #comments .reply-content img, .comment-photos img";
    const found = [];
    for (const img of document.querySelectorAll(selectors)) {
      if (img.closest(".user-face, .pic")) continue;  // avatars
      const url = imgUrl(img);
      if (url && /doubanio\.com\/view\//.test(url)) found.push({ url: doubanLarge(url), thumb: url });
    }
    return found;
  }

  function collect() {
    const site = siteOf(location.hostname);
    let title = (document.querySelector("h1") || {}).textContent || document.title;
    let items;
    if (site === "tieba") items = tiebaImages();
    else if (site === "xiaohongshu") {
      const got = xhsImages();
      items = got.items;
      if (got.title) title = got.title;
    } else if (site === "douban") items = doubanImages();
    if (!items || !items.length) items = genericImages();
    const seen = new Set();
    items = items.filter((it) => it.url && !seen.has(it.url) && seen.add(it.url));
    title = (site === "tieba" ? document.title.replace(/[-_]百度贴吧\s*$/, "") : title).trim().slice(0, 200);
    return { site: SITE_NAMES[site] || location.hostname, title, items };
  }

  // ---------- talking to the network ----------

  function gmRequest(opts) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({ ...opts, onload: resolve, onerror: () => reject(new Error("网络错误")),
        ontimeout: () => reject(new Error("超时")), timeout: 30000 });
    });
  }

  function toBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }

  async function download(url) {
    // The image host sees the page you are on as the referrer, as when your browser shows the image.
    const res = await gmRequest({ method: "GET", url, responseType: "arraybuffer", headers: { Referer: location.href } });
    if (res.status !== 200 || !res.response) throw new Error(`下载失败（${res.status}）`);
    return res.response;
  }

  async function send(item, page) {
    const buffer = await download(item.url);
    const res = await gmRequest({
      method: "POST", url: `${SERVER}/api/inbox`,
      headers: { "Content-Type": "application/json", "X-Memeseeks-Key": KEY },
      data: JSON.stringify({ image: toBase64(buffer), site: page.site, page_url: location.href,
        page_title: page.title, image_url: item.url }),
    });
    let body = {};
    try { body = JSON.parse(res.responseText); } catch (e) { /* not JSON */ }
    if (res.status !== 200) throw new Error(body.error || `迷因捕手没有响应（${res.status}）`);
    return body.status;  // "added" or "duplicate"
  }

  // ---------- the button and the panel ----------

  const hiddenHosts = () => GM_getValue("hiddenHosts", []);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function mount() {
    if (location.origin === SERVER || hiddenHosts().includes(location.hostname)) return;
    const host = document.createElement("div");
    host.style.cssText = "all: initial; position: fixed; z-index: 2147483647; right: 16px; bottom: 16px;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        * { box-sizing: border-box; font: 14px/1.4 system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; }
        .fab { border: 0; border-radius: 999px; padding: 10px 16px; background: #FFD21F; color: #1C1E2E;
               font-weight: 700; cursor: pointer; box-shadow: 0 2px 10px rgba(0,0,0,.25); }
        .panel { position: fixed; right: 16px; bottom: 64px; width: min(560px, calc(100vw - 32px));
                 max-height: 70vh; display: flex; flex-direction: column; background: #fff; color: #1C1E2E;
                 border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,.3); }
        .head, .foot { padding: 10px 14px; display: flex; gap: 8px; align-items: center; }
        .head { border-bottom: 1px solid #eee; justify-content: space-between; }
        .foot { border-top: 1px solid #eee; flex-wrap: wrap; }
        .grid { overflow: auto; padding: 10px; display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 8px; }
        label { position: relative; display: block; aspect-ratio: 1; border-radius: 8px; overflow: hidden; background: #f3f3f3; cursor: pointer; }
        label img { width: 100%; height: 100%; object-fit: cover; }
        label input { position: absolute; top: 6px; left: 6px; width: 18px; height: 18px; }
        label.done::after { content: attr(data-mark); position: absolute; inset: auto 0 0 0; background: rgba(28,30,46,.8); color: #fff; font-size: 12px; text-align: center; }
        button.act { border: 0; border-radius: 8px; padding: 8px 12px; cursor: pointer; background: #f0f0f0; }
        button.go { background: #1C1E2E; color: #fff; font-weight: 700; }
        button:disabled { opacity: .5; cursor: default; }
        .msg { color: #6B6F85; font-size: 13px; flex: 1 1 100%; }
        .x { border: 0; background: none; font-size: 20px; cursor: pointer; }
      </style>
      <button class="fab" type="button">采集 meme</button>`;
    const fab = root.querySelector(".fab");
    let panel = null;

    fab.addEventListener("click", () => {
      if (panel) { panel.remove(); panel = null; return; }
      const page = collect();
      panel = document.createElement("div");
      panel.className = "panel";
      panel.innerHTML = `
        <div class="head"><b>采集 meme · 这一页有 ${page.items.length} 张</b><button class="x" type="button" title="关闭">×</button></div>
        <div class="grid"></div>
        <div class="foot">
          <button class="act all" type="button">全选</button><button class="act none" type="button">全不选</button>
          <button class="act go" type="button">采集</button>
          <div class="msg">${page.items.length ? "只采集这一页上你勾选的图。" : "这一页上没找到像梗图的图。"}</div>
        </div>`;
      const grid = panel.querySelector(".grid");
      const msg = panel.querySelector(".msg");
      const boxes = page.items.map((item) => {
        const label = document.createElement("label");
        const img = document.createElement("img");
        img.src = item.thumb;
        img.referrerPolicy = "no-referrer-when-downgrade";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = true;
        label.append(img, box);
        grid.append(label);
        return { item, box, label };
      });
      const go = panel.querySelector(".go");
      const count = () => { go.textContent = `采集（${boxes.filter((b) => b.box.checked).length}）`; };
      grid.addEventListener("change", count);
      count();
      panel.querySelector(".all").addEventListener("click", () => { boxes.forEach((b) => { b.box.checked = true; }); count(); });
      panel.querySelector(".none").addEventListener("click", () => { boxes.forEach((b) => { b.box.checked = false; }); count(); });
      panel.querySelector(".x").addEventListener("click", () => { panel.remove(); panel = null; });
      go.addEventListener("click", async () => {
        const chosen = boxes.filter((b) => b.box.checked);
        go.disabled = true;
        const tally = { added: 0, duplicate: 0, failed: 0 };
        let lastError = "";
        for (const [n, b] of chosen.entries()) {
          msg.textContent = `正在采集第 ${n + 1}/${chosen.length} 张…`;
          try {
            const status = await send(b.item, page);
            tally[status === "added" ? "added" : "duplicate"] += 1;
            b.label.dataset.mark = status === "added" ? "已采集" : "库里已有";
          } catch (err) {
            tally.failed += 1;
            lastError = err.message;
            b.label.dataset.mark = "失败";
          }
          b.label.classList.add("done");
          b.box.checked = false;
          if (n < chosen.length - 1) await sleep(GAP_MS);
        }
        msg.textContent = `新采集 ${tally.added} 张，库里已有 ${tally.duplicate} 张` +
          (tally.failed ? `，失败 ${tally.failed} 张（${lastError}）` : "") + "。一分钟内就能搜到。";
        go.disabled = false;
        count();
      });
      root.append(panel);
    });
    document.documentElement.append(host);
  }

  if (typeof module !== "undefined") {  // node test harness
    module.exports = { absolute, doubanLarge, xhsImageUrl, looksLikeContent, siteOf };
    return;
  }
  GM_registerMenuCommand("在这个网站隐藏采集 meme 按钮", () => {
    GM_setValue("hiddenHosts", [...new Set([...hiddenHosts(), location.hostname])]);
    location.reload();
  });
  GM_registerMenuCommand("在这个网站显示采集 meme 按钮", () => {
    GM_setValue("hiddenHosts", hiddenHosts().filter((h) => h !== location.hostname));
    location.reload();
  });
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });
})();
