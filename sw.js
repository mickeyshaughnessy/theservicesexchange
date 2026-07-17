/* The RSE — lightweight service worker (install shell + offline fallback) */
const CACHE = 'rse-shell-v6';
const PRECACHE = [
  '/',
  '/index.html',
  '/styles.css?v=22',
  '/script.js?v=22',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/favicon.ico'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE).catch(() => undefined)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isVersionedAsset(url) {
  // Always revalidate JS/CSS (and anything with a cache-bust query) so cancel/edit
  // UI and other fixes ship without a hard-reset of the service worker.
  if (url.search && url.search.length > 1) return true;
  return /\.(js|css)(\?|$)/i.test(url.pathname);
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // Never cache API traffic
  if (url.hostname.includes('rse-api.com') || url.pathname.startsWith('/api')) return;

  // Network-first for HTML navigations
  const isNav = req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html');
  if (isNav) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => undefined);
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match('/index.html')))
    );
    return;
  }

  if (url.origin !== self.location.origin) return;

  // Network-first for JS/CSS and versioned assets (avoids sticky stale UI)
  if (isVersionedAsset(url)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => undefined);
          }
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Cache-first for icons / other static shell assets
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req).then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => undefined);
        }
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
