// 迷因捕手 · the web app: pages and what you can do on them (docs/design.md, "Pages and navigation").
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const view = $("#view");

// Build elements: h("a.card", { href }, child, ...). Strings become text, never HTML.
function h(spec, attrs = {}, ...kids) {
  const [tag, ...classes] = spec.split(".");
  const el = document.createElement(tag || "div");
  if (classes.length) el.className = classes.join(" ");
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...kids.flat().filter((x) => x !== null && x !== undefined && x !== false));
  return el;
}

// ---------------- the server ----------------
async function request(method, path, body) {
  const init = { method, credentials: "same-origin", headers: {} };
  if (body instanceof Blob) { init.headers["Content-Type"] = body.type; init.body = body; }  // an upload: the image itself
  else if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `请求失败（${res.status}）`);
    err.status = res.status;
    throw err;
  }
  return data;
}
const api = (path) => request("GET", path);

function toast(text, error = false) {
  const t = $("#toast");
  t.querySelector("span").textContent = text;
  t.classList.toggle("error", error);
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 2200);
}

// ---------------- pieces ----------------
const pad = (n) => (n ? `No.${String(n).padStart(4, "0")}` : "");
const siteOf = (item) => (item.source && item.source.site) || "本地";
const firstLine = (text) => (text || "").split(/[\s，。！？,.!?]+/).find((s) => s.length >= 2) || "";

function card(item) {
  return h("a.card", { href: `?view=meme&id=${item.id}` },
    h("img", { src: item.thumb, alt: item.text ? item.text.slice(0, 60) : "梗图", loading: "lazy", decoding: "async" }),
    h("div.label", {}, h("span.no", { text: pad(item.no) }), h("span.src", { text: siteOf(item) })));
}

const grid = (items) => h("div.grid", {}, items.map((it) => (it instanceof Node ? it : card(it))));

function blank(closed, title, text, ...extra) {
  return h("section.blank", {}, Cat.make({ closed, bubble: 0 }), h("h2", { text: title }), h("p", { text }), ...extra);
}

function searchForm(value = "") {
  const form = h("form.search", { role: "search" },
    h("input", { name: "q", type: "search", autocomplete: "off", enterkeyhint: "search", value,
      placeholder: "描述你记得的那张梗图，比如：上班的时候想下班", "aria-label": "描述你记得的那张梗图" }),
    h("button", { type: "submit", text: "搜" }));
  form.dataset.search = "";
  return form;
}

function albumCard(a) {
  const cover = a.cover ? h("img", { src: a.cover, alt: "", loading: "lazy" }) : Cat.make({ closed: 1, bubble: 0 });
  return h("a.album", { href: `?view=album&id=${a.id}` },
    h("div.cover", {}, cover), h("div.name", { text: a.name }), h("div.meta", { text: `${a.count} 张` }));
}

function newAlbumTile(onCreated) {
  const tile = h("button.album.new", { type: "button", text: "+ 新建图集" });
  tile.addEventListener("click", () => {
    const input = h("input", { name: "name", maxlength: 40, placeholder: "图集的名字", "aria-label": "图集的名字", autocomplete: "off" });
    const form = h("form", {}, input, h("button.btn.primary", { type: "submit", text: "新建" }));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { onCreated(await request("POST", "/api/albums", { name: input.value })); } catch (err) { toast(err.message, true); }
    });
    const box = h("div.album.new", {}, form);
    tile.replaceWith(box);
    input.focus();
  });
  return tile;
}

function connectSteps() {
  return [
    h("ol.connect", {},
      h("li", { text: "给浏览器装扩展 Violentmonkey（在 Firefox 附加组件或 Chrome 应用商店里搜 Violentmonkey）。" }),
      h("li", {}, h("a", { href: "/api/inbox/memeseeks.user.js", text: "安装采集 meme 脚本" }), "，在弹出的页面点「确认安装」。"),
      h("li", { text: "在贴吧、小红书、豆瓣或任何网页上点那只猫，勾选要的图采集进来，一分钟内就能在这里搜到。" })),
    h("p.hint", { text: "脚本只在你点它时采集你正在看的这一页，不自动翻页、不在后台抓取。采集来的图是 inbox 文件夹里的普通图片文件，并记下来自哪个帖子。" })];
}

// ---------------- settings (docs/design.md, Settings) ----------------
let settings = { theme: "paper", frame: true, intro: true, motion: "full", online: true };

function applySettings(s) {
  settings = s;
  const root = document.documentElement;
  if (s.theme === "night") root.dataset.theme = "night"; else delete root.dataset.theme;
  if (s.frame) delete root.dataset.frame; else root.dataset.frame = "off";
  if (s.motion === "reduced") root.dataset.motion = "reduced"; else delete root.dataset.motion;
  try {  // so the next visit paints in the right theme before the settings arrive (index.html)
    localStorage.setItem("memeseeks-theme", s.theme);
    localStorage.setItem("memeseeks-frame", s.frame ? "on" : "off");
    localStorage.setItem("memeseeks-motion", s.motion);
    localStorage.setItem("memeseeks-intro", s.intro ? "on" : "off");
  } catch (e) { /* storage blocked */ }
  $('meta[name="theme-color"]').content = getComputedStyle(root).getPropertyValue("--paper").trim();
  Frame.draw();
  return s;
}
const settingsReady = api("/api/settings").then(applySettings).catch(() => settings);

// ---------------- upload: the button, and dropping files anywhere ----------------
const IMAGE_NAME = /\.(jpe?g|png|gif|webp|bmp|heic|heif|avif)$/i;
let uploadTarget = null;  // the 图集 on screen, if any: uploads go into it

async function upload(files, album) {
  const images = [...files].filter((f) => f.type.startsWith("image/") || IMAGE_NAME.test(f.name));
  if (!images.length) { toast("这些不是图片", true); return; }
  const path = `/api/upload${album ? `?album=${encodeURIComponent(album.id)}` : ""}`;
  let added = 0, had = 0;
  const failed = [];
  for (const [i, f] of images.entries()) {
    toast(`正在上传 ${i + 1} / ${images.length}`);
    const type = f.type.startsWith("image/") ? f.type : `image/${f.name.split(".").pop().toLowerCase().replace("jpg", "jpeg")}`;
    try {
      const r = await request("POST", path, f.slice(0, f.size, type));
      if (r.status === "added") added++; else had++;
    } catch (err) { failed.push(err.message); }
  }
  const into = album ? `「${album.name}」` : "图库";
  const parts = [added && `已上传 ${added} 张到${into}，建好索引后就会出现`, had && `${had} 张本来就在图库里`, failed.length && `${failed.length} 张没传上：${failed[0]}`];
  toast(parts.filter(Boolean).join("；"), failed.length > 0);
  if (added) watchReady();  // the bar shows the indexing; the page refreshes when it is done
  else if (had && album) render({ slide: false });
}

function uploadButton(album) {
  const input = h("input", { type: "file", accept: "image/*", multiple: true });
  input.addEventListener("change", () => { upload(input.files, album); input.value = ""; });
  return h("label.btn.upload", { title: "也可以直接把图片拖进这个页面" }, "上传", input);
}

{
  const zone = h("div.dropzone", { hidden: true }, h("div"));
  document.body.append(zone);
  const hasFiles = (e) => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
  let depth = 0;
  addEventListener("dragenter", (e) => {
    if (!hasFiles(e)) return;
    if (depth++ === 0) { zone.firstChild.textContent = `松手，上传到${uploadTarget ? `「${uploadTarget.name}」` : "图库"}`; zone.hidden = false; }
  });
  addEventListener("dragleave", (e) => { if (hasFiles(e) && --depth <= 0) { depth = 0; zone.hidden = true; } });
  addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
  addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    zone.hidden = true;
    upload(e.dataTransfer.files, uploadTarget);
  });
}

// ---------------- copy, save, share ----------------
const canCopy = window.isSecureContext && navigator.clipboard && "write" in navigator.clipboard && typeof window.ClipboardItem === "function";
const EXT = { "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp" };

async function imageFile(item) {
  const res = await fetch(item.image, item.online ? { credentials: "omit", referrerPolicy: "no-referrer" } : { credentials: "same-origin" });
  if (!res.ok) throw new Error(`读取原图失败（${res.status}）`);
  const blob = await res.blob();
  let name = (item.relpath || "meme").split("/").pop();
  if (item.online) name += EXT[blob.type] || "";
  return new File([blob], name, { type: blob.type || "image/jpeg" });
}

async function toPng(blob) {
  const bitmap = await createImageBitmap(blob);
  const canvas = h("canvas", { width: bitmap.width, height: bitmap.height });
  canvas.getContext("2d").drawImage(bitmap, 0, 0);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("转换失败"))), "image/png"));
}

function shareButtons(item) {
  const out = [];
  if (canCopy) {
    out.push(h("button.btn", { type: "button", text: "复制", onclick: async () => {
      try {
        const png = imageFile(item).then(toPng);  // a pending promise: write() must run inside the click (Safari)
        await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
        reportShare(item);
        toast("已复制");
      } catch (err) { toast(`复制失败：${err.message}`, true); }
    } }));
  }
  const save = h("a.btn", { href: item.online ? item.image : `${item.image}?download=1`, download: "", text: "保存" });
  if (item.online) {  // a cross-origin link ignores download: save from a blob
    save.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        const file = await imageFile(item);
        const link = h("a", { href: URL.createObjectURL(file), download: file.name });
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 10000);
        reportShare(item);
      } catch (err) { toast(`保存失败：${err.message}`, true); }
    });
  }
  out.push(save);
  if (navigator.canShare) {
    out.push(h("button.btn", { type: "button", text: "分享", onclick: async () => {
      try {
        const file = await imageFile(item);
        if (!navigator.canShare({ files: [file] })) throw new Error("这个浏览器不能分享图片，请用保存");
        await navigator.share({ files: [file] });
        reportShare(item);
      } catch (err) { if (err.name !== "AbortError") toast(`分享失败：${err.message}`, true); }
    } }));
  }
  return out;
}

// ---------------- web results (off unless the server was started with --online) ----------------
// The provider's terms: the browser asks it directly, images load from its own URLs, results are shown as returned.
let onlineConfig = null;
const getOnlineConfig = () => (onlineConfig = onlineConfig || api("/api/online/config").catch(() => ({ enabled: false })));

function pickFile(files, sizes) {
  for (const size of sizes) {
    const set = files && files[size];
    const picked = set && (set.png || set.webp || set.jpg || set.gif);
    if (picked && picked.url) return picked.url;
  }
  return "";
}

function reportShare(item) {  // the provider asks to be told when a result is used; best effort
  if (!item || !item.online) return;
  const { config, slug, query } = item.online;
  fetch(`${config.share_url}${encodeURIComponent(slug)}`, {
    method: "POST", credentials: "omit", referrerPolicy: "no-referrer", keepalive: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: config.params.customer_id, q: query }),
  }).catch(() => {});
}

function openViewer(item) {
  $("#viewer-img").src = item.image;
  $("#viewer-img").alt = item.text ? item.text.slice(0, 120) : "梗图";
  $("#viewer-text").textContent = item.text || "";
  $("#viewer-actions").replaceChildren(...shareButtons(item));
  $("#viewer").showModal();
}

async function onlineSection(query) {
  const [config] = await Promise.all([getOnlineConfig(), settingsReady]);
  if (!config.enabled || !settings.online) return null;
  const credit = h("a.meta", { href: config.attribution_url, target: "_blank", rel: "noopener", text: `Powered by ${config.provider}` });
  const body = h("div", {}, h("p.notice", { text: "正在搜网上……" }));
  const section = h("section.online", {}, h("div.section-head", {}, h("h2", { text: "网上找到的" }), credit), body);
  (async () => {
    try {
      const url = new URL(config.search_url);
      for (const [k, v] of Object.entries(config.params)) url.searchParams.set(k, v);
      url.searchParams.set("q", query);
      url.searchParams.set("page", "1");
      const res = await fetch(url, { credentials: "omit", referrerPolicy: "no-referrer" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.result === false) {
        const why = data.errors && data.errors.message ? [].concat(data.errors.message).join("；") : `HTTP ${res.status}`;
        throw new Error(`${config.provider} 搜索失败：${why}`);
      }
      const list = data.data && Array.isArray(data.data.data) ? data.data.data : [];
      if (!list.length) { body.replaceChildren(h("p.notice", { text: "网上也没找到。" })); return; }
      body.replaceChildren(h("div.grid", {}, list.map((it) => {
        if (it.type === "ad") {  // shown as returned; sandboxed without same-origin, so it cannot touch this page
          const f = h("iframe.card.ad", { title: "广告", sandbox: "allow-scripts allow-popups allow-popups-to-escape-sandbox" });
          f.srcdoc = it.content || "";
          return f;
        }
        const item = { image: pickFile(it.file, ["hd", "md", "sm", "xs"]), text: it.title || "", relpath: `klipy-${it.slug || it.id}`,
          online: { config, slug: it.slug || it.id, query } };
        return h("button.card", { type: "button", onclick: () => openViewer(item) },
          h("img", { src: pickFile(it.file, ["md", "sm", "hd", "xs"]) || item.image, alt: item.text, loading: "lazy" }),
          h("div.label", {}, h("span.src", { text: config.provider })));
      })));
    } catch (err) {
      body.replaceChildren(h("p.notice.error", { text: err.message }));
    }
  })();
  return section;
}

// ---------------- pages ----------------
async function homePage() {
  const hero = h("section.hero", {},
    h("a.lockup", { href: "./", "aria-label": "迷因捕手" }, poppable(Cat.make({})),
      h("span.wordmark", {}, h("span.zh", { text: "迷因捕手" }), h("span.en", {}, [..."MEMESEEKS"].map((c) => h("i", { text: c }))))),
    h("p.tagline", { text: "梗图爱好者的宝库 · 用你记得的那句话找到它" }),
    searchForm());
  let today, albums, old;
  try {
    [today, albums, old] = await Promise.all([api("/api/today"), api("/api/albums"), api("/api/rediscover?n=12")]);
  } catch (err) {
    if (err.status !== 409) throw err;
    return [hero, emptyLibrary()];
  }
  const out = [hero];
  if (today) {
    const text = today.text.replace(/\s+/g, " ").trim();
    out.push(h("a.today", { href: `?view=meme&id=${today.id}` },
      h("div.t-img", {}, h("img", { src: today.thumb, alt: text.slice(0, 60) })),
      h("div.t-text", {}, h("div.kicker", { text: `今日一梗 · ${pad(today.no)}` }), h("h2", { text: firstLine(text) || "今天的这一张" }),
        h("p", { text: text.length > 90 ? `${text.slice(0, 90)}…` : text }), h("div.t-src", { text: `来自 ${siteOf(today)}` })),
      h("div.t-red"), h("div.t-blue"), h("div.t-blank")));
  }
  const mine = albums.filter((a) => a.id !== "all");
  out.push(h("section.section", {},
    h("div.section-head", {}, h("h2", { text: "我的图集" }), h("a.meta", { href: "?view=albums", text: "全部图集 →" })),
    h("div.albums", {}, mine.slice(0, 5).map(albumCard), newAlbumTile((a) => go(`?view=album&id=${a.id}`)))));
  let oldGrid = grid(old);
  const again = h("button.btn.quiet", { type: "button", text: "换一批", onclick: async () => {
    try { const next = grid(await api("/api/rediscover?n=12")); oldGrid.replaceWith(next); oldGrid = next; } catch (err) { toast(err.message, true); }
  } });
  out.push(h("section.section", {}, h("div.section-head", {}, h("h2", { text: "旧梗重温" }), again), oldGrid));
  return out;
}

function emptyLibrary() {
  return blank(1, "图库还是空的", "上传梗图，或者直接把图片拖进这个页面；也可以在设置里添加电脑上的梗图文件夹，或连接浏览器从社区采集。",
    h("div.blank-actions", {}, uploadButton(null), h("a.btn", { href: "?view=settings", text: "去设置" })));
}

async function searchPage({ q }) {
  document.title = `${q} · 迷因捕手`;
  let found;
  try { found = await api(`/api/search?q=${encodeURIComponent(q)}`); } catch (err) {
    if (err.status !== 503) throw err;
    watchReady();  // the bar above shows how far it has got; this page reloads when it is done
    return h("section.blank", {}, loader(), h("h2", { text: "还在准备" }), h("p", { text: "模型加载好就会自动搜索「" + q + "」。" }));
  }
  const [{ matches, maybe }, online] = await Promise.all([found, onlineSection(q)]);
  const out = [h("div.results-head", {}, h("h1.page-title", { text: matches.length ? `捕到 ${matches.length} 张` : "没有把握的结果" }),
    h("span.meta", { text: `「${q}」` }))];
  if (matches.length) out.push(grid(matches));
  else if (!maybe.length) out.push(blank(1, "这里还没有梗", "换个说法试试，或者直接写图里的字。"));
  else out.push(h("p.notice", { text: "换个说法试试，或者直接写图里的字。下面是沾点边的：" }));
  if (maybe.length) out.push(h("details.maybe", { open: !matches.length }, h("summary", { text: `可能相关（${maybe.length}）` }), grid(maybe)));
  if (online) out.push(online);
  return out;
}

async function memePage({ id }) {
  let m;
  try { m = await api(`/api/meme/${encodeURIComponent(id)}`); } catch (err) {
    if (err.status === 404) return blank(0, "这张梗被吃掉了", "它可能已经被移出图库，或者链接写错了。");
    throw err;
  }
  const text = (m.text || "").trim();
  document.title = `${firstLine(text) || "梗图"} · 迷因捕手`;
  const names = Object.fromEntries((await api("/api/albums")).map((a) => [a.id, a.name]));
  const albumChips = () => (m.albums.length
    ? h("div.chips", {}, m.albums.map((a) => h("a.chip", { href: `?view=album&id=${a}`, text: names[a] || "图集" })))
    : h("p.notice", { text: "还不在任何图集里。" }));
  let chips = albumChips();
  const like = h("button.btn", { type: "button" });
  const refresh = () => {
    like.textContent = m.liked ? "已喜欢" : "喜欢";
    like.classList.toggle("on", m.liked);
    like.setAttribute("aria-pressed", String(m.liked));
    const next = albumChips();
    chips.replaceWith(next);
    chips = next;
  };
  like.addEventListener("click", async () => {
    try {
      await request("POST", `/api/albums/liked/${m.liked ? "remove" : "add"}`, { ids: [m.id] });
      m.liked = !m.liked;
      m.albums = m.liked ? [...m.albums, "liked"] : m.albums.filter((a) => a !== "liked");
      refresh();
    } catch (err) { toast(err.message, true); }
  });
  const addTo = h("button.btn", { type: "button", text: "加入图集", onclick: () => openPicker(m, (id2, name) => { names[id2] = name; refresh(); }) });
  const own = !(m.sources && m.sources.length);
  const remove = h("button.linkish.danger", { type: "button", text: "移出图库", onclick: async () => {
    if (!confirm(own ? "把这张梗图移出图库？你文件夹里的原图不会被删除，只是不再显示。" : "把这张梗图移出图库？它会被移到图库的 rejected 文件夹。")) return;
    try { await request("POST", "/api/memes/remove", { ids: [m.id] }); toast("已移出图库"); history.back(); } catch (err) { toast(err.message, true); }
  } });
  const picture = h("img", { src: m.image, alt: text.slice(0, 120) || "梗图" });
  await Promise.race([picture.decode().catch(() => {}), new Promise((r) => setTimeout(r, 400))]);
  const added = m.added ? new Date(m.added * 1000).toISOString().slice(0, 10) : "";
  const sources = own
    ? h("p.notice", { text: `你自己的文件夹：${m.relpath}` })
    : h("ul.sources", {}, m.sources.map((s) => h("li", {}, `${s.site || "网页"} · `,
      s.page_url ? h("a", { href: s.page_url, target: "_blank", rel: "noopener noreferrer", text: `${s.page_title || "原帖"} ↗` }) : (s.page_title || ""))));
  const out = [h("div.meme", {},
    h("figure", {}, h("a", { href: `?view=feed&meme=${m.id}`, title: "全屏，接着刷相似的梗" }, picture)),
    h("aside", {},
      h("div.kicker", { text: [pad(m.no), added && `进库于 ${added}`].filter(Boolean).join(" · ") }),
      text ? [h("h3", { text: "图中文字" }), h("blockquote", { text })] : null,
      h("h3.s-src", { text: "出处" }), sources,
      h("h3.s-alb", { text: "图集" }), chips,
      h("h3.s-act", { text: "操作" }), h("div.actions", {}, like, addTo, ...shareButtons(m)),
      h("div.remove", {}, remove)))];
  refresh();
  if (m.similar && m.similar.length) out.push(h("section.section", {}, h("div.section-head", {}, h("h2", { text: "相似的梗" })), grid(m.similar)));
  return out;
}

async function albumsPage() {
  document.title = "图集 · 迷因捕手";
  const albums = await api("/api/albums");
  return [h("div.results-head", {}, h("h1.page-title", { text: "图集" })),
    h("div.albums", {}, albums.map(albumCard), newAlbumTile((a) => go(`?view=album&id=${a.id}`)))];
}

async function albumPage({ id, sort }) {
  const a = await api(`/api/albums/${encodeURIComponent(id)}?sort=${sort === "old" ? "old" : "new"}`);
  document.title = `${a.name} · 迷因捕手`;
  const target = id === "all" ? null : { id, name: a.name };
  uploadTarget = target;
  const title = h("h1.page-title", { text: a.name });
  const tools = h("div.tools", {}, h("span.seg", {},
    h("a", { href: `?view=album&id=${id}&sort=new`, "aria-current": String(sort !== "old"), text: "最新" }),
    h("a", { href: `?view=album&id=${id}&sort=old`, "aria-current": String(sort === "old"), text: "最早" })), uploadButton(target));
  if (id !== "all" && id !== "liked") {
    tools.append(
      h("button.btn.quiet", { type: "button", text: "重命名", onclick: () => {
        const input = h("input", { value: a.name, maxlength: 40, "aria-label": "新名字" });
        const form = h("form.rename", {}, input, h("button.btn.primary", { type: "submit", text: "好" }));
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          try { a.name = target.name = (await request("PATCH", `/api/albums/${id}`, { name: input.value })).name; title.textContent = a.name; form.replaceWith(title); }
          catch (err) { toast(err.message, true); }
        });
        title.replaceWith(form);
        input.select();
      } }),
      h("button.btn.quiet", { type: "button", text: "删除图集", onclick: async () => {
        if (!confirm(`删除图集「${a.name}」？里面的梗图不会被删除。`)) return;
        try { await request("DELETE", `/api/albums/${id}`); toast("已删除图集"); go("?view=albums", { replace: true }); } catch (err) { toast(err.message, true); }
      } }));
  }
  const last = remembered.get(id);  // a shuffled 刷梗 resumes shuffled; otherwise in this page's order
  const feedOrder = last.at && last.order === "shuffle" ? "shuffle" : sort === "old" ? "old" : "new";
  if (a.items.length) tools.prepend(h("a.btn.primary", { href: `?${qs({ view: "feed", album: id, order: feedOrder })}`, text: "刷梗" }));
  const head = h("div.album-head", {}, h("div", {}, title, h("div.meta", { text: `${a.count} 张` })), tools);
  if (!a.items.length) {
    const tip = id === "liked" ? ["还没有喜欢的梗图", "在梗图页点「喜欢」，它就会出现在这里。"]
      : id === "all" ? ["图库还是空的", "点「上传」，或者直接把图片拖进这个页面。"]
      : ["这个图集还是空的", "在梗图页点「加入图集」把图放进来，或者直接上传。"];
    return [head, blank(1, ...tip)];
  }
  return [head, grid(a.items)];
}

async function reviewPage() {
  document.title = "待确认 · 迷因捕手";
  const { pending, progress } = await api("/api/review");
  const note = h("p.meta");
  const showProgress = (p) => { note.textContent = `已确认 ${p.decided} 次，其中不要 ${p.rejected} 次`; };
  showProgress(progress);
  const markDecided = (c, decision) => {
    c.classList.add("decided");
    const done = h("div.done", {}, h("span", { text: decision === "keep" ? "已放进图库" : "已移到 rejected" }),
      decision === "reject" ? h("button.linkish", { type: "button", text: "撤销", onclick: () => decide([c], "keep") }) : null);
    c.querySelector(".choices, .done").replaceWith(done);
  };
  const decide = async (cards, decision) => {
    if (!cards.length) return;
    try {
      const body = cards.length === 1 ? { id: cards[0].dataset.id, decision } : { ids: cards.map((c) => c.dataset.id), decision };
      showProgress((await request("POST", "/api/review", body)).progress);
      cards.forEach((c) => markDecided(c, decision));
      refreshReviewCount();
    } catch (err) { toast(err.message, true); }
  };
  const cards = pending.map((item) => {
    const c = h("div.review-card", {}, card(item), h("div.choices", {},
      h("button.keep", { type: "button", text: "要", onclick: () => decide([c], "keep") }),
      h("button", { type: "button", text: "不要", onclick: () => decide([c], "reject") })));
    c.dataset.id = item.id;
    return c;
  });
  const all = h("button.btn", { type: "button", text: "全要", onclick: () => decide(cards.filter((c) => !c.classList.contains("decided")), "keep") });
  const head = h("div.album-head", {}, h("div", {}, h("h1.page-title", { text: "待确认" }), note), pending.length ? h("div.tools", {}, all) : null);
  if (!pending.length) return [head, blank(1, "没有待确认的图了", "采集来的图里如果有像表情包的，会先放在这里等你决定。")];
  return [head, h("p.review-note", { text: "这些是采集来的、字比较少的图，可能是表情包。「要」放进图库，「不要」移到图库的 rejected 文件夹（不删除，可以撤销）。" }),
    h("div.grid", {}, cards)];
}

async function settingsPage() {
  document.title = "设置 · 迷因捕手";
  const [s, sources, online] = await Promise.all([api("/api/settings"), api("/api/sources"), getOnlineConfig()]);
  applySettings(s);
  const choice = (key, options) => {  // [[value, label], ...]: saved and applied at once
    const seg = h("span.seg", { role: "group" });
    const paint = () => [...seg.children].forEach((b, i) => b.setAttribute("aria-pressed", String(options[i][0] === settings[key])));
    for (const [value, label] of options) {
      seg.append(h("button", { type: "button", text: label, onclick: async () => {
        if (settings[key] === value) return;
        try { applySettings(await request("PUT", "/api/settings", { [key]: value })); paint(); } catch (err) { toast(err.message, true); }
      } }));
    }
    paint();
    return seg;
  };
  const row = (title, ...body) => h("section.setting", {}, h("h2", { text: title }), h("div", {}, ...body));

  const folders = h("ul.folders");
  const showFolders = (list) => folders.replaceChildren(...list.map((f) => h("li", {},
    h("span", { text: f.path }),
    f.inbox ? h("span.tag", { text: "采集收件箱" }) : null,
    f.exists ? null : h("span.tag.gone", { text: "找不到这个文件夹" }),
    f.inbox ? null : h("button.linkish.danger", { type: "button", text: "移除", onclick: async () => {
      if (!confirm("不再收录这个文件夹？文件夹里的图片不会被删除，只是不再出现在迷因捕手里。")) return;
      try { showFolders(await request("POST", "/api/sources/remove", { path: f.path })); toast("已移除"); } catch (err) { toast(err.message, true); }
    } }))));
  showFolders(sources);
  const path = h("input", { name: "path", autocomplete: "off", spellcheck: "false", placeholder: "文件夹的完整路径，比如 D:\\梗图", "aria-label": "文件夹的完整路径" });
  const add = h("form.add-folder", {}, path, h("button.btn", { type: "submit", text: "添加" }));
  add.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { showFolders(await request("POST", "/api/sources", { path: path.value })); path.value = ""; toast("已添加，正在建立索引"); watchReady(); } catch (err) { toast(err.message, true); }
  });

  return [h("div.results-head", {}, h("h1.page-title", { text: "设置" }), h("span.meta", { text: "保存在图库里，用手机打开也一样" })),
    h("div.settings", {},
      row("主题", choice("theme", [["paper", "纸色"], ["night", "夜间"]])),
      row("蒙德里安边框", choice("frame", [[true, "开"], [false, "关"]])),
      row("开场动画", choice("intro", [[true, "开"], [false, "关"]]), h("p.hint", { text: "每次打开迷因捕手时播放一次。" })),
      row("动效", choice("motion", [["full", "完整"], ["reduced", "减少"]]),
        h("p.hint", { text: "减少：不播放小猫动画和翻页滑动。系统设置了减少动态效果时，总是减少。" })),
      online.enabled ? row("网上搜索", choice("online", [[true, "开"], [false, "关"]]),
        h("p.hint", { text: `搜索时也到 ${online.provider} 上找，结果单独列在最后。` })) : null,
      row("来源文件夹", folders, add,
        h("p.hint", { text: "这些文件夹里（包括子文件夹）的图片会被收录。原图留在原处，迷因捕手不会移动或修改它们。填的是运行迷因捕手的这台电脑上的路径。" })),
      row("连接浏览器", ...connectSteps()))];
}

// ---------------- the cat's eggs (docs/design.md, "The cat") ----------------
// a click on the logo's cat pops it (the name still goes home); quick clicks count up, a nod to popcat.click
const popBadge = h("div.popcount", { "aria-hidden": "true" });
document.body.append(popBadge);
let pops = 0, lastPop = 0;
function popCat(e) {
  const svg = e.currentTarget;
  e.preventDefault();
  e.stopPropagation();
  const now = performance.now();
  pops = now - lastPop < 700 ? pops + 1 : 1;
  lastPop = now;
  if (pops >= 2) {
    const r = svg.getBoundingClientRect();
    popBadge.style.left = `${r.left}px`;
    popBadge.style.top = r.top > 90 ? `${r.top - 34}px` : `${r.bottom + 6}px`;
    popBadge.replaceChildren("POP ", h("b", { text: `×${pops}` }));
    popBadge.classList.remove("bump");
    void popBadge.offsetWidth;
    popBadge.classList.add("bump", "on");
  }
  clearTimeout(popCat.timer);
  popCat.timer = setTimeout(() => { popBadge.classList.remove("on"); pops = 0; }, 1200);
  Cat.pop(svg, pops >= 2);
}
const poppable = (svg) => { svg.classList.add("pop-cat"); svg.addEventListener("click", popCat); return svg; };

// pull to refresh (touch): the cat starts open; pulling swallows the bubble and shuts the mouth, and it
// stays shut while held; letting go opens it and spits the bubble out while the page reloads its content
{
  const ptr = h("div.ptr", { "aria-hidden": "true" }, Cat.make({}));
  const cat = ptr.firstChild, wrap = $(".wrap");
  document.body.append(ptr);  // outside .wrap: a transformed ancestor would carry a fixed element along
  const MAX = 120, GO = 84;
  let y0 = null, pull = 0;
  const setPull = (px, animate) => {
    pull = px;
    const tr = animate ? "transform .35s cubic-bezier(.2, .8, .2, 1), opacity .35s" : "none";
    wrap.style.transition = tr;
    ptr.style.transition = tr;
    wrap.style.transform = px ? `translateY(${px}px)` : "";
    ptr.style.transform = `translate(-50%, ${px - cat.getBoundingClientRect().height - 10}px)`;  // in the gap, above the page
    ptr.style.opacity = px > 6 ? 1 : 0;
  };
  addEventListener("touchstart", (e) => {
    const off = document.body.dataset.view === "feed" || document.querySelector("dialog[open]") || Cat.still();
    y0 = !off && scrollY <= 0 && e.touches.length === 1 ? e.touches[0].clientY : null;
  }, { passive: true });
  addEventListener("touchmove", (e) => {
    if (y0 === null) return;
    const dy = e.touches[0].clientY - y0;
    if (dy <= 0) { setPull(0); return; }
    e.preventDefault();
    const px = Math.min(MAX, dy * 0.55);
    setPull(px, false);
    Cat.set(cat, Cat.ease(Math.min(1, px / (GO * 0.85))), Math.max(0, 1 - px / 36));  // the bubble goes in first
  }, { passive: false });
  addEventListener("touchend", () => {
    if (y0 === null) return;
    y0 = null;
    if (pull < GO) { setPull(0, true); Cat.set(cat, 0, 1); return; }
    setPull(GO * 0.8, true);  // hold the page down while it reloads
    const done = render({ slide: false });  // reload in place
    const t0 = performance.now();
    const step = (now) => {  // open (220 ms), then spit the bubble (200 ms)
      const t = now - t0;
      Cat.set(cat, t < 150 ? 1 : t < 370 ? 1 - Cat.ease((t - 150) / 220) : 0, t < 370 ? 0 : Cat.spit(Math.min(1, (t - 370) / 200)));
      if (t < 570) requestAnimationFrame(step);
      else done.finally(() => setTimeout(() => setPull(0, true), 150));
    };
    requestAnimationFrame(step);
  });
}

// loading: the cat opens into the logo and shuts again until the page is ready
function loader() {
  const cat = Cat.make({ closed: 1, bubble: 0 });
  Cat.loop(cat);
  return h("div.loading", { role: "status" }, cat, h("span.visually-hidden", { text: "正在加载" }));
}

// ---------------- work behind the page: the models (downloading on the first run), then indexing ----------------
const readyBar = h("div.readybar", { role: "status", hidden: true });
$(".bar").after(readyBar);
let modelsReady = true, wasIndexing = false, readyTimer = null;
const gb = (n) => (n / 1e9).toFixed(1);
const STAGES = { ocr: "第 1 步：识别图里的文字", vlm: "写图的描述", clip: "第 2 步：看图" };

function showBar(text, share, error = false) {
  readyBar.replaceChildren(h("span", { text }),
    ...(share === null ? [] : [h("div.track", {}, h("i", { style: `width: ${(Math.min(0.99, share) * 100).toFixed(1)}%` }))]));
  readyBar.classList.toggle("error", error);
  readyBar.hidden = false;
}

async function watchReady() {  // checks often while something runs, now and then otherwise (new files in a folder)
  clearTimeout(readyTimer);
  let s;
  try { s = await api("/api/ready"); } catch (err) { readyTimer = setTimeout(watchReady, 10000); return; }
  const was = modelsReady;
  modelsReady = s.state === "ready";
  if (!modelsReady) {
    const d = s.download;
    if (s.state === "error") { showBar(`模型没能加载：${s.error}`, null, true); return; }  // needs a restart
    showBar(d ? `第一次启动，正在下载模型：${gb(d.done)} / 约 ${gb(d.total)} GB。下完就能搜索，其他功能现在就能用。`
      : "正在加载模型，马上就能搜索。", d ? d.done / d.total : null);
    readyTimer = setTimeout(watchReady, 1500);
    return;
  }
  if (!was && route().view === "search") render({ slide: false });  // the search that had to wait
  const ix = s.indexing, busy = Boolean(ix && (ix.running || ix.pending)), p = ix && ix.progress;
  if (busy) wasIndexing = true;
  if (busy && p && p.total) {
    showBar(`正在建立索引：${p.done} / ${p.total} 张（${STAGES[p.stage] || p.stage}）。建好后就能搜到，不用在这里等。`, p.done / p.total);
  } else readyBar.hidden = true;
  if (wasIndexing && !busy) {  // done: pages that list memes pick up the new ones, unless you are typing
    wasIndexing = false;
    const typing = document.activeElement && document.activeElement.matches("input, textarea, select");
    if (!typing && ["home", "albums", "album"].includes(route().view)) render({ slide: false });
  }
  readyTimer = setTimeout(watchReady, busy ? 1500 : 10000);
}
watchReady();

// ---------------- 刷梗: full screen, one meme after another (docs/design.md, Pages and navigation) ----------------
const qs = (params) => new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString();
const reduceMotion = () => Cat.still();
const remembered = {  // where each 图集's 刷梗 stopped: this browser only, a convenience
  get(album) { try { return JSON.parse(localStorage.getItem(`memeseeks-feed:${album}`)) || {}; } catch (e) { return {}; } },
  set(album, v) { try { localStorage.setItem(`memeseeks-feed:${album}`, JSON.stringify(v)); } catch (e) { /* storage blocked */ } },
};

async function feedPage(r) {
  document.title = "刷梗 · 迷因捕手";
  const album = r.album || null, meme = r.meme || null;
  const saved = album ? remembered.get(album) : {};
  let order = ["new", "old", "shuffle"].includes(r.order) ? r.order : "new";
  let base = order === "shuffle" ? saved.base || "new" : order;  // what 顺序 means here: the 图集 page's sort
  let seed = order !== "shuffle" ? 0 : +r.seed || (saved.order === "shuffle" && saved.seed) || Math.floor(Math.random() * 1e9);
  const load = async () => (await api(`/api/feed?${qs({ album, meme, order, seed: seed || null })}`)).ids;
  const names = album ? Object.fromEntries((await api("/api/albums")).map((a) => [a.id, a.name])) : {};
  let ids = await load();
  const startAt = r.at || saved.at;
  let i = Math.max(0, ids.indexOf(startAt));

  const cache = new Map();
  const info = (id) => {
    if (!cache.has(id)) cache.set(id, api(`/api/meme/${encodeURIComponent(id)}?similar=0`).catch((err) => { cache.delete(id); throw err; }));
    return cache.get(id);
  };
  const stage = h("div.feed-stage");
  const count = h("span.feed-count");
  const like = h("button.fbtn", { type: "button" });
  const addTo = h("button.fbtn", { type: "button", text: "加入图集" });
  const more = h("a.fbtn", { text: "详情" });
  const actions = h("div.feed-actions", {}, like, addTo, more);
  let current = null, busy = false;

  const close = () => {
    if (history.state && history.state.app) history.back();
    else go(album ? `?view=album&id=${encodeURIComponent(album)}` : meme ? `?view=meme&id=${encodeURIComponent(meme)}` : "./", { replace: true });
  };
  const paint = () => {
    count.textContent = current ? `${i + 1} / ${ids.length}` : "";
    actions.hidden = !current;
    if (!current) return;
    like.textContent = current.liked ? "已喜欢" : "喜欢";
    like.classList.toggle("on", current.liked);
    like.setAttribute("aria-pressed", String(current.liked));
    more.href = `?view=meme&id=${current.id}`;
    const here = qs({ view: "feed", album, meme, order: album ? order : null, seed: seed || null, at: current.id });
    history.replaceState(history.state, "", `?${here}`);
    if (album) remembered.set(album, { order, base, seed, at: current.id });
  };

  // seen: 刷梗 from the header shows the memes not seen for longest first
  let seenQueue = [];
  const flushSeen = () => {
    if (!seenQueue.length) return;
    fetch("/api/seen", { method: "POST", credentials: "same-origin", keepalive: true,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: seenQueue }) }).catch(() => {});
    seenQueue = [];
  };

  // one slide replaces the other: the new one comes from below (next) or above (back)
  const slideIn = (fig, dir) => {
    const old = stage.firstElementChild;
    stage.append(fig);
    if (!old) return Promise.resolve();
    if (!dir || reduceMotion()) { old.remove(); return Promise.resolve(); }
    const opts = { duration: 380, easing: "cubic-bezier(.65, 0, .25, 1)" };
    old.animate([{ transform: old.style.transform || "none" }, { transform: `translateY(${-dir * 100}%)`, opacity: 0.3 }], opts)
      .finished.then(() => old.remove());
    return fig.animate([{ transform: `translateY(${dir * 100}%)` }, { transform: "none" }], opts).finished;
  };
  const endCard = (dir) => {
    current = null;
    i = ids.length;
    if (album) remembered.set(album, { order, base, seed, at: null });  // next time from the start
    const again = ids.length ? h("button.fbtn", { type: "button", text: "从头再刷", onclick: () => show(0, 1) }) : null;
    slideIn(h("div.slide.end", {}, Cat.make({ closed: 1, bubble: 0 }),
      h("h2", { text: ids.length ? "刷完了" : "这里还没有梗" }),
      h("p", { text: ids.length ? `这里的 ${ids.length} 张都看过了。` : "先往这里放几张梗图吧。" }),
      h("div.blank-actions", {}, again, h("button.fbtn", { type: "button", text: "返回", onclick: close }))), dir);
    paint();
  };
  async function show(k, dir) {
    if (busy || k < 0) return false;
    if (k >= ids.length) {
      const moved = Boolean(current);
      if (moved || !stage.firstChild) endCard(dir);
      return moved;
    }
    busy = true;
    let m;
    try { m = await info(ids[k]); } catch (err) {
      busy = false;
      if (err.status === 404) { ids.splice(k, 1); return show(k, dir); }  // removed meanwhile
      toast(err.message, true);
      return false;
    }
    try {
      const img = h("img", { src: m.image, alt: (m.text || "").slice(0, 120) || "梗图", draggable: "false" });
      await Promise.race([img.decode().catch(() => {}), new Promise((res) => setTimeout(res, 600))]);
      await slideIn(h("figure.slide", {}, img), dir);
      i = k;
      current = m;
      seenQueue.push(m.id);
      if (seenQueue.length >= 5) flushSeen();
      paint();
      ids.slice(k + 1, k + 3).forEach((id) => info(id).then((n) => { new Image().src = n.image; }).catch(() => {}));
      return true;
    } finally { busy = false; }
  }
  const step = (dir) => show(i + dir, dir);

  like.addEventListener("click", async () => {
    const m = current;
    try {
      await request("POST", `/api/albums/liked/${m.liked ? "remove" : "add"}`, { ids: [m.id] });
      m.liked = !m.liked;
      m.albums = m.liked ? [...m.albums, "liked"] : m.albums.filter((a) => a !== "liked");
      paint();
    } catch (err) { toast(err.message, true); }
  });
  addTo.addEventListener("click", () => openPicker(current, paint));

  // swipe (touch), wheel, keys, and two buttons for a mouse
  let y0 = null, dy = 0, t0 = 0;
  stage.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 1 || busy) { y0 = null; return; }
    y0 = e.touches[0].clientY; dy = 0; t0 = performance.now();
  }, { passive: true });
  stage.addEventListener("touchmove", (e) => {
    if (y0 === null) return;
    e.preventDefault();
    dy = e.touches[0].clientY - y0;
    const edge = (dy > 0 && i === 0) || (dy < 0 && i >= ids.length);
    const cur = stage.lastElementChild;
    if (cur) cur.style.transform = `translateY(${edge ? dy * 0.3 : dy}px)`;
  }, { passive: false });
  stage.addEventListener("touchend", async () => {
    if (y0 === null) return;
    y0 = null;
    const cur = stage.lastElementChild;
    const flick = Math.abs(dy) / Math.max(1, performance.now() - t0) > 0.5 && Math.abs(dy) > 30;
    if ((Math.abs(dy) > 90 || flick) && await step(dy < 0 ? 1 : -1)) return;
    if (cur && cur.isConnected && cur.style.transform) {
      cur.animate([{ transform: cur.style.transform }, { transform: "none" }], { duration: 200, easing: "cubic-bezier(.2, .8, .2, 1)" });
      cur.style.transform = "";
    }
  });
  let lastWheel = 0;
  stage.addEventListener("wheel", (e) => {  // one move per gesture: a trackpad's glide is a stream of events
    e.preventDefault();
    const now = performance.now(), fresh = now - lastWheel > 250;
    lastWheel = now;
    if (fresh && Math.abs(e.deltaY) >= 4) step(e.deltaY > 0 ? 1 : -1);
  }, { passive: false });
  const onKey = (e) => {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || $("#picker").open || e.target.closest("input, textarea")) return;
    if (e.key === " " && e.target.closest("button, a")) return;  // space presses the focused button
    if (["ArrowDown", "ArrowRight", "PageDown", " ", "j"].includes(e.key)) { e.preventDefault(); step(1); }
    else if (["ArrowUp", "ArrowLeft", "PageUp", "k"].includes(e.key)) { e.preventDefault(); step(-1); }
    else if (e.key === "Escape") close();
    else if (e.key === "l" && current) like.click();
  };
  document.addEventListener("keydown", onKey);
  addEventListener("pagehide", flushSeen);

  // 顺序 / 随机, for a 图集
  let orderSeg = null;
  if (album) {
    const pick = async (next) => {
      if (next === order || busy) return;
      const keep = current && current.id;
      order = next;
      seed = order === "shuffle" ? Math.floor(Math.random() * 1e9) : 0;
      try { ids = await load(); } catch (err) { toast(err.message, true); return; }
      [...orderSeg.children].forEach((b, n) => b.setAttribute("aria-pressed", String((n === 1) === (order === "shuffle"))));
      if (order === "shuffle") { show(0, 1); return; }  // a new random order, from its start
      i = Math.max(0, ids.indexOf(keep));  // back in order: stay on this meme
      paint();
    };
    orderSeg = h("span.seg", { role: "group", "aria-label": "顺序" },
      h("button", { type: "button", text: "顺序", "aria-pressed": String(order !== "shuffle"), onclick: () => pick(base) }),
      h("button", { type: "button", text: "随机", "aria-pressed": String(order === "shuffle"), onclick: () => pick("shuffle") }));
  }

  const title = album ? names[album] || "图集" : meme ? "从这一张刷起" : "全部";
  const feed = h("section.feed", { "aria-label": "刷梗" },
    h("div.feed-top", {}, h("button.x", { type: "button", "aria-label": "关闭", text: "×", onclick: close }),
      h("span.feed-title", { text: title }), orderSeg, count),
    stage, actions,
    h("div.feed-nav", {},
      h("button", { type: "button", "aria-label": "上一张", text: "↑", onclick: () => step(-1) }),
      h("button", { type: "button", "aria-label": "下一张", text: "↓", onclick: () => step(1) })));
  feed._leave = () => { flushSeen(); document.removeEventListener("keydown", onKey); removeEventListener("pagehide", flushSeen); };
  if (ids.length) show(i, 0); else endCard(0);
  return feed;
}

// ---------------- 加入图集 ----------------
async function openPicker(m, onChange) {
  const dlg = $("#picker"), list = $("#picker-list"), form = $("#picker-new");
  const fill = async () => {
    const albums = (await api("/api/albums")).filter((a) => a.id !== "all");
    list.replaceChildren(...albums.map((a) => {
      const box = h("input", { type: "checkbox", checked: m.albums.includes(a.id) });
      box.addEventListener("change", async () => {
        try {
          await request("POST", `/api/albums/${a.id}/${box.checked ? "add" : "remove"}`, { ids: [m.id] });
          m.albums = box.checked ? [...m.albums, a.id] : m.albums.filter((x) => x !== a.id);
          m.liked = m.albums.includes("liked");
          onChange(a.id, a.name);
        } catch (err) { box.checked = !box.checked; toast(err.message, true); }
      });
      return h("li", {}, h("label", {}, box, h("span", { text: a.name }), h("span.meta", { text: String(a.count) })));
    }));
  };
  form.onsubmit = async (e) => {
    e.preventDefault();
    try {
      const a = await request("POST", "/api/albums", { name: form.elements.name.value });
      await request("POST", `/api/albums/${a.id}/add`, { ids: [m.id] });
      m.albums = [...m.albums, a.id];
      form.reset();
      onChange(a.id, a.name);
      await fill();
    } catch (err) { toast(err.message, true); }
  };
  await fill();
  dlg.showModal();
}
document.querySelectorAll("dialog [data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
document.querySelectorAll("dialog").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));

// ---------------- moving between pages ----------------
const PAGES = { home: homePage, search: searchPage, meme: memePage, albums: albumsPage, album: albumPage, review: reviewPage, settings: settingsPage, feed: feedPage };

function route() {
  const p = new URLSearchParams(location.search);
  const q = (p.get("q") || "").trim();
  return { ...Object.fromEntries(p), view: p.get("view") || (q ? "search" : "home"), q, sort: p.get("sort") || "new" };
}

function go(url, { replace = false } = {}) {
  history[replace ? "replaceState" : "pushState"]({ app: 1 }, "", url);  // app: going back stays in the app
  return render({ back: false });
}

let renderToken = 0;
let leavePage = null;  // a page can clean up (listeners) before the next one replaces it: node._leave
let rendered = false, flying = null;  // flying: the meme whose picture flies between a card and its page
// one picture may carry the name: a meme page's own picture gives way to the card that flies
const unnameMeme = () => view.querySelectorAll(".meme figure img").forEach((img) => { img.style.viewTransitionName = "none"; });
async function render({ back = false, slide = true } = {}) {
  const r = route();
  const token = ++renderToken;
  document.title = "迷因捕手";
  uploadTarget = null;
  // the header follows the page; switched with the page itself, so a slide never shows both logos at once
  const frame = () => {
    document.body.dataset.view = r.view;
    const tab = { album: "albums", albums: "albums", home: "home", review: "review", settings: "settings", feed: "feed" }[r.view] || "";
    document.querySelectorAll("[data-tab]").forEach((a) => (a.dataset.tab === tab ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    $("#bar-q").value = r.view === "search" ? r.q : "";
  };
  if (!rendered) frame();
  let nodes;
  const slow = setTimeout(() => { if (token === renderToken) view.replaceChildren(loader()); }, 350);
  try {
    nodes = await (PAGES[r.view] || homePage)(r);
  } catch (err) {
    nodes = err.status === 409 ? emptyLibrary() : h("p.notice.error", { text: err.message });
  }
  clearTimeout(slow);
  const leave = [].concat(nodes).map((n) => n && n._leave).find(Boolean) || null;
  if (token !== renderToken) { if (leave) leave(); return; }  // a newer navigation won
  const swap = () => {
    frame();
    if (leavePage) leavePage();
    leavePage = leave;
    view.replaceChildren(...[].concat(nodes));
    window.scrollTo(0, 0);
    if (back && flying) {  // back from a meme: its picture flies home into its card
      const img = view.querySelector(`a.card[href$="id=${flying}"] img`);
      if (img) { unnameMeme(); img.style.viewTransitionName = "meme"; }
    }
    if (r.view !== "meme") flying = null;
  };
  if (slide && rendered && document.startViewTransition && !reduceMotion()) {
    document.documentElement.dataset.dir = back ? "back" : "forward";
    const t = document.startViewTransition(swap);
    t.ready.catch(() => {});  // skipped (say, a second click mid-way): the page still changes
    t.finished.catch(() => {}).then(() => view.querySelectorAll("img[style*='view-transition-name']").forEach((img) => { img.style.viewTransitionName = ""; }));
    await t.updateCallbackDone;
  } else swap();
  rendered = true;
  refreshReviewCount();
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("a");
  if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target || a.hasAttribute("download")) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname !== location.pathname) return;  // /api/... links, other sites
  e.preventDefault();
  const card = a.matches("a.card") && a.querySelector("img");
  if (card) {  // the card's picture grows into the meme page's
    unnameMeme();
    card.style.viewTransitionName = "meme";
    flying = url.searchParams.get("id");
  }
  go(url.search || "./");
});
document.addEventListener("submit", (e) => {
  const form = e.target.closest("form[data-search]");
  if (!form) return;
  e.preventDefault();
  const q = form.elements.q.value.trim();
  go(q ? `?q=${encodeURIComponent(q)}` : "./");
});
addEventListener("popstate", () => render({ back: true }));

async function refreshReviewCount() {
  try {
    const { pending_review: n } = await api("/api/status");
    $("#nav-review-count").textContent = n;
    $("#nav-review").hidden = !n;
  } catch (err) { $("#nav-review").hidden = true; }
}

// ---------------- the entrance (docs/design.md, "The cat"): once per visit ----------------
// The logo and the name appear together; the cat pops twice, opens into the logo and the bubble pops; then
// the lockup glides to its place on the page while the page fades in. A click skips it.
async function intro(firstRender) {
  const root = document.documentElement;
  await settingsReady;
  if (!settings.intro || Cat.still()) { delete root.dataset.intro; return; }
  try { sessionStorage.setItem("memeseeks-intro", "1"); } catch (e) { /* storage blocked */ }
  const P = window.POPCAT, K = "#161411", [mx, my] = P.mc;
  // pop, pop (quick half-opens), then the open that lands on the logo; all as numbers between two states
  const KT = "0;0.127;0.255;0.364;0.491;0.618;0.727;1";
  const SP = "0.3 0 0.3 1;0.3 0 0.3 1;0 0 1 1;0.3 0 0.3 1;0.3 0 0.3 1;0 0 1 1;0.42 0 0.58 1";
  const morph = (a, b, extra = "") => {
    const half = Cat.lerp(a, b, 0.55);
    return `<path d="${a}" fill="${K}"><animate attributeName="d" begin="0.3s" dur="1.1s" fill="freeze" calcMode="spline"
      keyTimes="${KT}" keySplines="${SP}" values="${[a, half, a, a, half, a, a, b].join(";")}"/>${extra}</path>`;
  };
  const noseGoes = `<animate attributeName="opacity" begin="0.3s" dur="1.1s" fill="freeze" calcMode="discrete" keyTimes="0;0.884" values="1;0"/>`;
  const logo = h("div.intro-logo");
  logo.innerHTML = `<svg viewBox="${P.vb}" aria-hidden="true">
    <path d="${P.body}" fill="#FFD21F" stroke="${K}" stroke-width="15" stroke-linejoin="round"/>
    ${morph(P.closed.eyes[0], P.final.eyes[0])}${morph(P.closed.eyes[1], P.final.eyes[1])}
    ${morph(P.closed.nose, P.final.nose, noseGoes)}${morph(P.closed.mouth, P.final.mouth)}
    <g transform="translate(${mx} ${my})"><g transform="scale(0)"><animateTransform attributeName="transform" type="scale"
      begin="1.4s" dur="0.35s" fill="freeze" keyTimes="0;0.6;1" values="0;1.12;1"/>
      <g transform="translate(${-mx} ${-my})">${P.bubble}</g></g></g></svg>`;
  const name = h("span.wordmark.intro-name", {}, h("span.zh", { text: "迷因捕手" }), h("span.en", {}, [..."MEMESEEKS"].map((c) => h("i", { text: c }))));
  const stage = h("div", { id: "intro", "aria-hidden": "true" }, h("div.intro-lock", {}, logo, name));
  document.body.append(stage);
  root.dataset.intro = "run";

  let done = false, target = null;
  const finish = () => {
    done = true;
    if (target) target.forEach((el) => el.classList.remove("intro-hide"));
    stage.remove();
    delete root.dataset.intro;
  };
  stage.addEventListener("click", () => { if (!done) finish(); });
  await Promise.all([new Promise((r) => setTimeout(r, 2250)), firstRender]);
  if (done) return;
  const visible = (el) => el && el.getClientRects().length > 0;
  const onHome = $("#view .lockup");
  target = onHome ? [$(".lockup .cat"), $(".lockup .wordmark")] : [$(".brand .cat"), $(".brand .wordmark")];
  if (!target.every(visible)) { finish(); return; }
  target.forEach((el) => el.classList.add("intro-hide"));
  const fly = (from, to, by) => {
    const a = from.getBoundingClientRect(), b = to.getBoundingClientRect(), k = b[by] / a[by];
    return from.animate([{ transform: "none" }, { transform: `translate(${b.left - a.left}px, ${b.top - a.top}px) scale(${k})` }],
      { duration: 800, easing: "cubic-bezier(.65, 0, .25, 1)", fill: "forwards" }).finished;
  };
  delete root.dataset.intro;  // the page fades in while the lockup glides
  stage.classList.add("gliding");
  await Promise.all([fly(logo, target[0], "height"), fly(name, target[1], "width")]).catch(() => {});
  if (!done) finish();
}

// ---------------- start ----------------
poppable(Cat.draw($(".brand .cat")));
Frame.draw();
{
  const first = render();
  if (document.documentElement.dataset.intro) intro(first);
}

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
