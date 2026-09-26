// ==UserScript==
// @name         迷因捕手
// @namespace    memeseeks
// @version      0.2.0
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

// What it does: when you click the cat (采集 meme), it lists the images on the page you are looking at and
// sends the ones you tick to your memeseeks server. It never turns pages or runs on its own, and it sends
// nothing but the image, the site name, the page link, the page title and the 图集 you chose.

(function () {
  "use strict";

  const SERVER = "__MEMESEEKS_SERVER__";
  const KEY = "__MEMESEEKS_KEY__";
  const POPCAT = "__MEMESEEKS_POPCAT__";  // the logo's shapes (web/popcat.js), filled in by the server
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

  function stop(message) {  // the server is not there (or does not know this script): no use trying the rest
    const err = new Error(message);
    err.offline = true;
    return err;
  }

  async function send(item, page, album) {
    const buffer = await download(item.url);
    let res;
    try {
      res = await gmRequest({
        method: "POST", url: `${SERVER}/api/inbox`,
        headers: { "Content-Type": "application/json", "X-Memeseeks-Key": KEY },
        data: JSON.stringify({ image: toBase64(buffer), site: page.site, page_url: location.href,
          page_title: page.title, image_url: item.url, ...(album ? { album } : {}) }),
      });
    } catch (err) {
      throw stop("迷因捕手没在运行，打开桌面上的「迷因捕手」再试一次");
    }
    let body = {};
    try { body = JSON.parse(res.responseText); } catch (e) { /* not JSON */ }
    if (res.status === 401) throw stop("采集脚本需要重新安装，在迷因捕手的「设置 · 连接浏览器」里再装一次");
    if (res.status !== 200) throw new Error(body.error || `迷因捕手没有响应（${res.status}）`);
    return body.status;  // "added" or "duplicate"
  }

  // ---------- the cat button and the panel (docs/design.md, "The browser collector") ----------
  // It runs on other people's sites, so everything lives in a closed shadow root with system fonts only.

  const hiddenHosts = () => GM_getValue("hiddenHosts", []);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const NUM = /-?\d+(\.\d+)?/g;
  const lerp = (a, b, t) => { const nb = b.match(NUM); let i = 0; return a.replace(NUM, (x) => (+x + (nb[i++] - x) * t).toFixed(1)); };
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const spit = (u) => (u < 0.6 ? 1.15 * ease(u / 0.6) : 1.15 - 0.15 * ease((u - 0.6) / 0.4));
  const animate = (ms, fn) => new Promise((done) => {  // fn(t in ms) every frame; resolves when done
    const t0 = performance.now();
    const step = (now) => { const t = Math.min(ms, now - t0); fn(t); if (t < ms) requestAnimationFrame(step); else done(); };
    requestAnimationFrame(step);
  });

  const STYLE = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .root { --ink: #161411; --paper: #F3EFE4; --accent: #FFD21F; --red: #DE3B2E; --blue: #1F4FA3; --muted: #6E685C;
      font: 14px/1.5 system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; color: var(--ink); }
    .fab { position: fixed; left: 0; top: 0; z-index: 2147483000; display: flex; align-items: center; touch-action: none; }
    .fab.label-right { flex-direction: row-reverse; }
    .fab.label-right .label { margin: 0 0 0 10px; transform: translateX(-8px); }
    .fab.dragging .cat { cursor: grabbing; transform: translate(-2px, -2px) rotate(-4deg); box-shadow: 7px 7px 0 var(--ink); transition: none; }
    .fab.dragging .label { opacity: 0 !important; }
    .cat { width: 56px; height: 56px; padding: 5px; background: var(--paper); border: 2.5px solid var(--ink); box-shadow: 4px 4px 0 var(--ink);
      cursor: pointer; display: block; transition: transform .12s; }
    .cat:hover { transform: translate(-1px, -1px); box-shadow: 5px 5px 0 var(--ink); }
    .cat:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 var(--ink); }
    .cat svg { width: 100%; height: 100%; display: block; overflow: visible; }
    .label { display: flex; align-items: stretch; background: var(--ink); color: #fff; font-weight: 700; margin-right: 10px; line-height: 32px;
      padding-right: 12px; white-space: nowrap; opacity: 0; transform: translateX(8px); pointer-events: none; transition: opacity .18s, transform .18s; }
    .label b { width: 8px; background: var(--accent); margin-right: 10px; }
    .fab:hover .label, .fab.show-label .label { opacity: 1; transform: none; }
    .count { position: absolute; right: -8px; top: -10px; background: var(--ink); color: var(--accent); font: 700 12px/1 Consolas, monospace;
      padding: 4px 6px; opacity: 0; transition: opacity .2s; }
    .fab.label-right .count { right: auto; left: 48px; }
    .count.on { opacity: 1; }
    .count.bump { animation: bump .22s cubic-bezier(.2, .8, .2, 1); }
    @keyframes bump { from { transform: scale(1.35); } to { transform: scale(1); } }
    .panel { position: fixed; z-index: 2147483000; width: min(560px, calc(100vw - 36px)); max-height: 72vh; display: flex; flex-direction: column;
      background: var(--paper); border: 3px solid var(--ink); box-shadow: 6px 6px 0 var(--ink); animation: open .22s cubic-bezier(.2, .8, .2, 1); }
    .panel[hidden] { display: none; }
    @keyframes open { from { opacity: 0; transform: scale(.94); } }
    .strip { display: flex; height: 12px; border-bottom: 3px solid var(--ink); flex: none; }
    .strip i { border-right: 2px solid var(--ink); }
    .strip i:last-child { border-right: 0; }
    .strip .p { background: var(--paper); } .strip .y { background: var(--accent); } .strip .r { background: var(--red); } .strip .b { background: var(--blue); }
    .head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; padding: 12px 16px 8px; }
    .title { font: 900 19px/1.2 "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif; }
    .meta { font: 12px Consolas, monospace; color: var(--muted); }
    .x { border: 0; background: none; font-size: 22px; line-height: 1; cursor: pointer; color: var(--ink); padding: 0 2px; }
    .grid { overflow: auto; padding: 4px 16px 12px; display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; }
    .item { position: relative; aspect-ratio: 1; background: #fff; border: 2px solid #CFC6B2; cursor: pointer; overflow: hidden; padding: 0; }
    .item img { width: 100%; height: 100%; object-fit: cover; display: block; transition: opacity .15s; }
    .item.on { border-color: var(--ink); }
    .item:not(.on) img { opacity: .4; }
    .check { position: absolute; left: 6px; top: 6px; width: 20px; height: 20px; background: #fff; border: 2px solid var(--ink); display: grid; place-items: center; }
    .item.on .check { background: var(--accent); }
    .item.on .check::after { content: ""; width: 9px; height: 5px; border: solid var(--ink); border-width: 0 0 2.5px 2.5px; transform: rotate(-45deg) translate(1px, -1px); }
    .tag { position: absolute; left: 0; right: 0; bottom: 0; font: 700 11px/20px system-ui, sans-serif; text-align: center; background: var(--ink); color: var(--accent); }
    .tag.dup { color: #fff; } .tag.fail { background: var(--red); color: #fff; }
    .foot { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 16px 14px; border-top: 2px solid var(--ink); }
    .btn { font: 700 14px system-ui, "Microsoft YaHei", sans-serif; padding: 7px 14px; border: 2px solid var(--ink); background: #fff; cursor: pointer; color: var(--ink); }
    .btn.go { background: var(--accent); box-shadow: 3px 3px 0 var(--ink); }
    .btn:disabled { opacity: .5; cursor: default; }
    .where { display: flex; align-items: center; gap: 6px; margin-left: auto; font-size: 13px; }
    .where select { font: 13px system-ui, "Microsoft YaHei", sans-serif; color: var(--ink); background: #fff; border: 2px solid var(--ink); padding: 5px 6px; max-width: 150px; }
    .msg { flex: 1 1 100%; display: flex; align-items: stretch; font-size: 13px; min-height: 30px; background: var(--ink); color: #fff; }
    .msg[hidden] { display: none; }
    .msg b { width: 8px; margin-right: 10px; flex: none; background: var(--accent); }
    .msg.err b { background: var(--red); }
    .msg.note { background: none; color: var(--muted); } .msg.note b { display: none; }
    .msg span { padding: 5px 10px 5px 0; }
    .flyer { position: fixed; z-index: 2147483001; pointer-events: none; border: 2px solid var(--ink); object-fit: cover; }
    @media (prefers-reduced-motion: reduce) { .panel, .count.bump { animation: none; } .label, .cat, .item img { transition: none; } }`;

  function mount() {
    if (location.origin === SERVER || hiddenHosts().includes(location.hostname)) return;
    const host = document.createElement("div");
    host.style.cssText = "all: initial; position: fixed; left: 0; top: 0; width: 0; height: 0; z-index: 2147483647;";
    const shadow = host.attachShadow({ mode: "closed" });
    shadow.innerHTML = `<style>${STYLE}</style>
      <div class="root">
        <div class="panel" hidden>
          <div class="strip"><i class="p" style="flex:3"></i><i class="y" style="flex:1.4"></i><i class="p" style="flex:2.2"></i><i class="r" style="flex:.5"></i><i class="p" style="flex:2.6"></i><i class="b" style="flex:1"></i><i class="p" style="flex:1.2"></i></div>
          <div class="head"><div><div class="title">采集 meme</div><div class="meta"></div></div><button class="x" type="button" title="关闭">×</button></div>
          <div class="grid"></div>
          <div class="foot">
            <button class="btn all" type="button">全选</button><button class="btn none" type="button">全不选</button>
            <label class="where">放进<select></select></label>
            <button class="btn go" type="button">采集</button>
            <div class="msg" hidden><b></b><span></span></div>
          </div>
        </div>
        <div class="fab"><div class="label"><b></b><span>采集 meme</span></div>
          <button class="cat" type="button" title="采集 meme（可以拖动）"><svg aria-hidden="true"></svg></button><div class="count"></div></div>
      </div>`;
    const $ = (sel) => shadow.querySelector(sel);
    const fab = $(".fab"), catBtn = $(".cat"), svg = $(".cat svg"), panel = $(".panel"), grid = $(".grid"), go = $(".go");
    const msg = $(".msg"), count = $(".count"), where = $(".where select"), labelText = $(".label span");

    // ---- the cat: the logo's shapes; the mouth shuts and opens by interpolating them ----
    const P = POPCAT, K = "#161411", [mx, my] = P.mc;
    svg.setAttribute("viewBox", P.vb);
    svg.innerHTML = `<path d="${P.body}" fill="#FFD21F" stroke="${K}" stroke-width="18" stroke-linejoin="round"/>
      <path class="e0" fill="${K}"/><path class="e1" fill="${K}"/><path class="nose" fill="${K}"/><path class="mouth" fill="${K}"/>
      <g class="bub">${P.bubble}</g>`;
    const setCat = (closed, bubble) => {
      [[".e0", P.final.eyes[0], P.closed.eyes[0]], [".e1", P.final.eyes[1], P.closed.eyes[1]],
        [".nose", P.final.nose, P.closed.nose], [".mouth", P.final.mouth, P.closed.mouth]]
        .forEach(([sel, a, b]) => svg.querySelector(sel).setAttribute("d", lerp(a, b, closed)));
      svg.querySelector(".nose").setAttribute("opacity", closed >= 0.375 ? 1 : 0);
      svg.querySelector(".bub").setAttribute("transform", `translate(${mx} ${my}) scale(${bubble.toFixed(3)}) translate(${-mx} ${-my})`);
    };
    setCat(0, 1);
    // one gulp per meme that arrives; a new arrival mid-gulp takes over from the current mouth shape, so the
    // cat never lags behind the memes
    let gulpToken = null, gulpDone = Promise.resolve(), mouth = 0;
    const gulp = () => {
      if (reduce()) return gulpDone;
      const token = {}, c0 = mouth;
      gulpToken = token;
      gulpDone = animate(150, (t) => {
        if (gulpToken !== token) return;
        mouth = t < 65 ? c0 + (1 - c0) * ease(t / 65) : 1 - ease((t - 65) / 85);
        setCat(mouth, 0);
      });
      return gulpDone;
    };
    const spitOut = () => (reduce() ? (setCat(0, 1), Promise.resolve()) : animate(260, (t) => setCat(0, spit(t / 260))));
    const shut = () => (reduce() ? (setCat(1, 0), Promise.resolve()) : animate(200, (t) => setCat(ease(t / 200), 0)));

    // ---- the cat can be dragged anywhere; a tap still opens the panel ----
    const MARGIN = 12, POS_KEY = `pos:${location.hostname}`;  // where the cat sits, per site
    let pos = GM_getValue(POS_KEY, null);  // the cat's centre, as fractions of the window
    const placePanel = () => {  // open towards the middle of the screen
      const r = catBtn.getBoundingClientRect(), w = innerWidth, h = innerHeight;
      const pr = { width: panel.offsetWidth, height: panel.offsetHeight };  // its layout size: the opening animation scales it
      const left = r.left + r.width / 2 > w / 2 ? r.right - pr.width : r.left;
      const top = r.top + r.height / 2 > h / 2 ? r.top - pr.height - 16 : r.bottom + 16;
      panel.style.left = `${Math.min(w - pr.width - MARGIN, Math.max(MARGIN, left))}px`;
      panel.style.top = `${Math.min(h - pr.height - MARGIN, Math.max(MARGIN, top))}px`;
      panel.style.transformOrigin = `${left < r.left ? "100%" : "0"} ${top < r.top ? "100%" : "0"}`;
    };
    const placeFab = () => {
      const r = catBtn.getBoundingClientRect(), w = innerWidth, h = innerHeight;
      const cx = pos ? pos.fx * w : w - MARGIN - r.width / 2 - 6, cy = pos ? pos.fy * h : h - MARGIN - r.height / 2 - 6;
      const x = Math.min(w - MARGIN - r.width / 2 - 6, Math.max(MARGIN + r.width / 2, cx));
      const y = Math.min(h - MARGIN - r.height / 2 - 6, Math.max(MARGIN + r.height / 2, cy));
      fab.classList.toggle("label-right", x < w / 2);  // the label slides out towards the middle
      const lab = $(".label").getBoundingClientRect().width + 10;
      fab.style.transform = `translate(${x - r.width / 2 - (x < w / 2 ? 0 : lab)}px, ${y - r.height / 2}px)`;
      if (!panel.hidden) placePanel();
    };
    let drag = null;
    catBtn.addEventListener("pointerdown", (e) => {
      const r = catBtn.getBoundingClientRect();
      drag = { id: e.pointerId, x0: e.clientX, y0: e.clientY, dx: e.clientX - (r.left + r.width / 2), dy: e.clientY - (r.top + r.height / 2), moved: false };
      catBtn.setPointerCapture(e.pointerId);
    });
    catBtn.addEventListener("pointermove", (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      if (!drag.moved && Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 5) return;  // a tap, not a drag yet
      drag.moved = true;
      fab.classList.add("dragging");
      pos = { fx: (e.clientX - drag.dx) / innerWidth, fy: (e.clientY - drag.dy) / innerHeight };
      placeFab();
    });
    const endDrag = (e) => {
      if (!drag || e.pointerId !== drag.id) return null;
      const moved = drag.moved;
      drag = null;
      fab.classList.remove("dragging");
      if (moved) GM_setValue(POS_KEY, pos);
      return moved;
    };
    catBtn.addEventListener("pointercancel", endDrag);
    catBtn.addEventListener("pointerup", (e) => {
      const moved = endDrag(e);
      if (moved === false) toggle();
    });
    catBtn.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    addEventListener("resize", placeFab);
    GM_registerMenuCommand("猫头回到右下角", () => { pos = null; GM_setValue(POS_KEY, null); placeFab(); });

    // ---- the panel: this page's images, ticked; where to put them; collect ----
    let page = null, items = [], busy = false;
    const say = (text, kind = "ok") => { msg.className = `msg ${kind}`; msg.querySelector("span").textContent = text; msg.hidden = !text; };
    const paint = () => {
      grid.replaceChildren(...items.map((it, i) => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = `item${it.on ? " on" : ""}`;
        el.dataset.i = i;
        const img = document.createElement("img");
        img.src = it.thumb;
        img.alt = "";
        img.referrerPolicy = "no-referrer-when-downgrade";
        const check = document.createElement("span");
        check.className = "check";
        el.append(img, check);
        if (it.done) {
          const tag = document.createElement("span");
          tag.className = `tag ${it.done}`;
          tag.textContent = { ok: "已采集", dup: "库里已有", fail: "没采到" }[it.done];
          el.append(tag);
        }
        return el;
      }));
      const n = items.filter((x) => x.on && !x.done).length;
      $(".meta").textContent = `这一页 ${items.length} 张 · 已选 ${items.filter((x) => x.on).length}`;
      go.textContent = `采集（${n}）`;
      go.disabled = busy || !n;
    };
    grid.addEventListener("click", (e) => {
      const el = e.target.closest(".item");
      if (!el || busy) return;
      const it = items[+el.dataset.i];
      if (it.done) return;
      it.on = !it.on;
      paint();
    });
    $(".all").addEventListener("click", () => { items.forEach((x) => { if (!x.done) x.on = true; }); paint(); });
    $(".none").addEventListener("click", () => { items.forEach((x) => { if (!x.done) x.on = false; }); paint(); });
    const hide = () => { panel.hidden = true; if (!busy) setCat(0, 1); };  // closing reopens a shut mouth
    $(".x").addEventListener("click", hide);
    panel.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
    where.addEventListener("change", () => GM_setValue("album", where.value));

    async function loadAlbums() {  // the 图集 to put memes in: chosen here, remembered here
      const keep = GM_getValue("album", "");
      where.replaceChildren(new Option("只进图库", ""));
      try {
        const res = await gmRequest({ method: "GET", url: `${SERVER}/api/inbox/albums`, headers: { "X-Memeseeks-Key": KEY } });
        if (res.status === 401) throw new Error("采集脚本需要重新安装，在迷因捕手的「设置 · 连接浏览器」里再装一次。");
        if (res.status !== 200) throw new Error(`迷因捕手没有响应（${res.status}）`);
        for (const a of JSON.parse(res.responseText)) where.append(new Option(a.name, a.id));
        where.value = [...where.options].some((o) => o.value === keep) ? keep : "";
        return true;
      } catch (err) {
        say(err.message === "网络错误" ? "迷因捕手没在运行，打开桌面上的「迷因捕手」再试一次。" : err.message, "err");
        return false;
      }
    }

    function toggle() {
      if (!panel.hidden) { hide(); return; }
      if (!busy) {
        page = collect();
        items = page.items.map((it) => ({ ...it, on: true, done: null }));
        say(items.length ? "" : "这一页上没找到像梗图的图。", "note");
        loadAlbums();
      }
      panel.hidden = false;
      paint();
      placePanel();
    }

    const mouthPoint = () => {  // the mouth centre on screen
      const m = svg.getScreenCTM();
      return { x: m.a * mx + m.e, y: m.d * my + m.f };
    };
    const fly = (el) => {  // a copy of the thumbnail shrinks into the cat's mouth
      if (!el || reduce()) return Promise.resolve();
      const r = el.getBoundingClientRect(), to = mouthPoint();
      const f = document.createElement("img");
      f.src = el.querySelector("img").src;
      f.className = "flyer";
      Object.assign(f.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
      shadow.append(f);
      const dx = to.x - (r.left + r.width / 2), dy = to.y - (r.top + r.height / 2);
      return f.animate([{ transform: "none", opacity: 1 },
        { transform: `translate(${dx * 0.55}px, ${dy * 0.35 - 40}px) scale(.55)`, opacity: 1, offset: 0.5 },
        { transform: `translate(${dx}px, ${dy}px) scale(.06)`, opacity: 0.9 }],
      { duration: 460, easing: "cubic-bezier(.5, 0, .75, 1)" }).finished.then(() => f.remove(), () => f.remove());
    };
    let eaten = 0;
    const bumpCount = () => {
      eaten += 1;
      count.textContent = `+${eaten}`;
      count.classList.remove("bump");
      void count.offsetWidth;
      count.classList.add("on", "bump");
    };

    go.addEventListener("click", async () => {
      const todo = items.map((it, i) => [it, i]).filter(([it]) => it.on && !it.done);
      if (!todo.length) return;
      busy = true;
      eaten = 0;
      say("");
      paint();
      const album = where.value || null, albumName = album ? where.selectedOptions[0].textContent : "";
      setCat(0, 0);  // the mouth open, waiting to eat
      fab.classList.add("show-label");
      labelText.textContent = "采集中…";
      const tally = { ok: 0, dup: 0, fail: 0 };
      let lastError = "", offline = false;
      const flights = [];
      for (const [n, [it, i]] of todo.entries()) {
        if (offline) { it.done = "fail"; it.on = false; tally.fail += 1; continue; }
        say(`正在采集第 ${n + 1} / ${todo.length} 张…`, "note");
        try {
          const status = await send(it, page, album);
          it.done = status === "added" ? "ok" : "dup";
          tally[it.done] += 1;
          const el = grid.querySelector(`.item[data-i="${i}"]`);
          flights.push(fly(el).then(() => { gulp(); bumpCount(); }));
        } catch (err) {
          it.done = "fail";
          tally.fail += 1;
          lastError = err.message;
          offline = Boolean(err.offline);
        }
        it.on = false;
        if (n < todo.length - 1 && !offline) await sleep(GAP_MS);
      }
      await Promise.all(flights);
      await gulpDone;
      busy = false;
      paint();
      fab.classList.remove("show-label");
      labelText.textContent = "采集 meme";
      const into = albumName ? ` · 放进「${albumName}」` : "";
      if (tally.ok + tally.dup) {
        await spitOut();  // the bubble comes back: done
        say(`新采集 ${tally.ok} 张 · 库里已有 ${tally.dup} 张${into} · 一分钟内就能搜到` +
          (tally.fail ? ` · ${tally.fail} 张没采到（${lastError}）` : ""), tally.fail ? "err" : "ok");
      } else {
        await shut();  // the mouth stays shut: nothing was caught
        say(`${tally.fail} 张没采到：${lastError}`, "err");
      }
      setTimeout(() => count.classList.remove("on"), 1500);
    });

    document.documentElement.append(host);
    placeFab();
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
