// Caches ONLY the static app shell listed below. Anything else (health, status,
// features, self-check, the API root) is never touched here, so live account and
// health data can never be served from cache.
const CACHE_NAME = 'jarvis-dashboard-v3';
const APP_SHELL = [
  '/dashboard',
  '/dashboard.css',
  '/dashboard.js',
  '/manifest.webmanifest',
  '/icon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-512.png',
  '/icons/apple-touch-icon.png',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !APP_SHELL.includes(url.pathname)) return;

  // Stale-while-revalidate: launch instantly from cache (works offline), refresh in the
  // background so the next launch picks up shell changes without a manual cache bump.
  const key = url.pathname;
  event.respondWith(
    caches.open(CACHE_NAME).then(async cache => {
      const cached = await cache.match(key);
      const refresh = fetch(request)
        .then(response => {
          if (response.ok) cache.put(key, response.clone());
          return response;
        })
        .catch(() => undefined);
      if (cached) {
        event.waitUntil(refresh);
        return cached;
      }
      return (await refresh) || Response.error();
    })
  );
});
