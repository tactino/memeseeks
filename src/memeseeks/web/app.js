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
  if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
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

function connectBrowser() {
  return h("details.connect", {},
    h("summary", { text: "从社区采集 meme：连接浏览器" }),
    h("ol", {},
      h("li", { text: "给浏览器装扩展 Violentmonkey（在 Firefox 附加组件或 Chrome 应用商店里搜 Violentmonkey）。" }),
      h("li", {}, h("a", { href: "/api/inbox/memeseeks.user.js", text: "安装采集 meme 脚本" }), "，在弹出的页面点「确认安装」。"),
      h("li", { text: "在贴吧、小红书、豆瓣或任何网页上点那只猫，勾选要的图采集进来，一分钟内就能在这里搜到。" })),
    h("p", { text: "脚本只在你点它时采集你正在看的这一页，不自动翻页、不在后台抓取。采集来的图是 inbox 文件夹里的普通图片文件，并记下来自哪个帖子。" }));
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
  const config = await getOnlineConfig();
  if (!config.enabled) return null;
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
    h("a.lockup", { href: "./", "aria-label": "迷因捕手" }, Cat.make({}),
      h("span.wordmark", {}, h("span.zh", { text: "迷因捕手" }), h("span.en", {}, [..."MEMESEEKS"].map((c) => h("i", { text: c }))))),
    h("p.tagline", { text: "梗图爱好者的宝库 · 用你记得的那句话找到它" }),
    searchForm());
  let today, albums, old;
  try {
    [today, albums, old] = await Promise.all([api("/api/today"), api("/api/albums"), api("/api/rediscover?n=12")]);
  } catch (err) {
    if (err.status !== 409) throw err;
    return [hero, blank(1, "图库还是空的", "在电脑上运行 memeseeks add <文件夹> 把梗图加进来，或者连接浏览器，从社区采集。"), connectBrowser()];
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
  out.push(connectBrowser());
  return out;
}

async function searchPage({ q }) {
  document.title = `${q} · 迷因捕手`;
  const [{ matches, maybe }, online] = await Promise.all([api(`/api/search?q=${encodeURIComponent(q)}`), onlineSection(q)]);
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
  const added = m.added ? new Date(m.added * 1000).toISOString().slice(0, 10) : "";
  const sources = own
    ? h("p.notice", { text: `你自己的文件夹：${m.relpath}` })
    : h("ul.sources", {}, m.sources.map((s) => h("li", {}, `${s.site || "网页"} · `,
      s.page_url ? h("a", { href: s.page_url, target: "_blank", rel: "noopener noreferrer", text: `${s.page_title || "原帖"} ↗` }) : (s.page_title || ""))));
  const out = [h("div.meme", {},
    h("figure", {}, h("img", { src: m.image, alt: text.slice(0, 120) || "梗图" })),
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
  const title = h("h1.page-title", { text: a.name });
  const tools = h("div.tools", {}, h("span.seg", {},
    h("a", { href: `?view=album&id=${id}&sort=new`, "aria-current": String(sort !== "old"), text: "最新" }),
    h("a", { href: `?view=album&id=${id}&sort=old`, "aria-current": String(sort === "old"), text: "最早" })));
  if (id !== "all" && id !== "liked") {
    tools.append(
      h("button.btn.quiet", { type: "button", text: "重命名", onclick: () => {
        const input = h("input", { value: a.name, maxlength: 40, "aria-label": "新名字" });
        const form = h("form.rename", {}, input, h("button.btn.primary", { type: "submit", text: "好" }));
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          try { a.name = (await request("PATCH", `/api/albums/${id}`, { name: input.value })).name; title.textContent = a.name; form.replaceWith(title); }
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
  const head = h("div.album-head", {}, h("div", {}, title, h("div.meta", { text: `${a.count} 张` })), tools);
  if (!a.items.length) {
    const tip = id === "liked" ? ["还没有喜欢的梗图", "在梗图页点「喜欢」，它就会出现在这里。"] : ["这个图集还是空的", "在梗图页点「加入图集」，把图放进来。"];
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
const PAGES = { home: homePage, search: searchPage, meme: memePage, albums: albumsPage, album: albumPage, review: reviewPage };

function route() {
  const p = new URLSearchParams(location.search);
  const q = (p.get("q") || "").trim();
  return { view: p.get("view") || (q ? "search" : "home"), id: p.get("id"), q, sort: p.get("sort") || "new" };
}

function go(url, { replace = false } = {}) {
  history[replace ? "replaceState" : "pushState"](null, "", url);
  render();
}

let renderToken = 0;
async function render() {
  const r = route();
  const token = ++renderToken;
  document.body.dataset.view = r.view;
  document.title = "迷因捕手";
  const tab = { album: "albums", albums: "albums", home: "home", review: "review" }[r.view] || "";
  document.querySelectorAll("[data-tab]").forEach((a) => (a.dataset.tab === tab ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  $("#bar-q").value = r.view === "search" ? r.q : "";
  let nodes;
  try {
    nodes = await (PAGES[r.view] || homePage)(r);
  } catch (err) {
    nodes = err.status === 409 ? blank(1, "图库还是空的", err.message) : h("p.notice.error", { text: err.message });
  }
  if (token !== renderToken) return;  // a newer navigation won
  view.replaceChildren(...[].concat(nodes));
  window.scrollTo(0, 0);
  refreshReviewCount();
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("a");
  if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target || a.hasAttribute("download")) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname !== location.pathname) return;  // /api/... links, other sites
  e.preventDefault();
  go(url.search || "./");
});
document.addEventListener("submit", (e) => {
  const form = e.target.closest("form[data-search]");
  if (!form) return;
  e.preventDefault();
  const q = form.elements.q.value.trim();
  go(q ? `?q=${encodeURIComponent(q)}` : "./");
});
addEventListener("popstate", render);

async function refreshReviewCount() {
  try {
    const { pending_review: n } = await api("/api/status");
    $("#nav-review-count").textContent = n;
    $("#nav-review").hidden = !n;
  } catch (err) { $("#nav-review").hidden = true; }
}

// ---------------- start ----------------
Cat.draw($(".brand .cat"));
Frame.draw();
api("/api/settings").then((s) => { if (!s.frame) { document.documentElement.dataset.frame = "off"; Frame.draw(); } }).catch(() => {});
render();

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
