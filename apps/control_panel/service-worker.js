const CACHE = "jarvis-control-shell-v2";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon.svg", "./icons/apple-touch-icon.png", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/icon-maskable-512.png"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes("/functions/") || url.pathname.includes("/rest/")) return;
  if (!SHELL.some(path => new URL(path, self.registration.scope).pathname === url.pathname)) return;
  event.respondWith(fetch(request).then(response => {
    if (response.ok) {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, copy)));
    }
    return response;
  }).catch(async () => (await caches.match(request)) || (await caches.match("./index.html")) || Response.error()));
});

const PUSH_CATEGORIES = new Set([
  "forex_watch", "risk_incident", "system_health", "job_matches",
  "affiliate_updates", "marketplace_updates", "jaeo_tasks"
]);
self.addEventListener("push", event => {
  if (!event.data) return;
  event.waitUntil((async () => {
    let payload;
    try { payload = event.data.json(); } catch { return; }
    if (!payload || !PUSH_CATEGORIES.has(payload.category)) return;
    const title = typeof payload.title === "string" ? payload.title.slice(0, 80) : "Jarvis update";
    const body = typeof payload.body === "string" ? payload.body.slice(0, 240) : "You have a new update.";
    const target = typeof payload.url === "string" ? new URL(payload.url, self.location.origin) : new URL("./index.html", self.registration.scope);
    if (target.origin !== self.location.origin) target.href = new URL("./index.html", self.registration.scope).href;
    await self.registration.showNotification(title, {
      body, tag: typeof payload.dedupe_key === "string" ? payload.dedupe_key.slice(0, 100) : payload.category,
      icon: "./icons/icon-192.png", badge: "./icons/icon-192.png",
      data: { url: target.href, category: payload.category }
    });
  })());
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const raw = event.notification.data && event.notification.data.url;
  let target = new URL("./index.html", self.registration.scope);
  try {
    const candidate = new URL(typeof raw === "string" ? raw : "./index.html", self.location.origin);
    if (candidate.origin === self.location.origin) target = candidate;
  } catch { /* retain the safe same-origin fallback */ }
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(target.href);
        return client.focus();
      }
    }
    return self.clients.openWindow(target.href);
  })());
});
