// App shell only; API calls and images always go to the network.
// Network first: a new version is picked up on the next load. The cache is only a fallback when
// the server can't be reached, so an old app.js can never outlive a server update.
const SHELL = "memeseeks-shell-v3";
const FILES = ["./", "index.html", "tokens.css", "style.css", "app.js", "manifest.webmanifest",
  "icons/logo.svg", "fonts/memeseeks-serif.woff2", "fonts/memeseeks-mono.woff2"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  event.respondWith(fetch(event.request).then((res) => {
    if (res.ok) {
      const copy = res.clone();
      event.waitUntil(caches.open(SHELL).then((cache) => cache.put(event.request, copy)));
    }
    return res;
  }).catch(() => caches.match(event.request, { ignoreSearch: true })));
});
