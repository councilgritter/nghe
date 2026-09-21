// Cache the app shell up front and keep it fresh: the shell is fetched from the network
// first and the cache is only the offline fallback. Audio clips are cached the first time
// each is heard.
// Bump SHELL when the caching logic changes so installed copies drop the old cache.
const SHELL = 'nghe-shell-v2';
const CLIPS = 'nghe-clips-v1';
const FILES = ['./', 'index.html', 'data.json', 'manifest.webmanifest', 'icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(
    ks.filter(k => k !== SHELL && k !== CLIPS).map(k => caches.delete(k))
  )).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;           // let fonts go to the network

  if (url.pathname.includes('/audio/')) {               // clips: cache-first, keep forever
    e.respondWith(caches.open(CLIPS).then(async c => {
      const hit = await c.match(e.request);
      if (hit) return hit;
      const res = await fetch(e.request);
      if (res.ok) c.put(e.request, res.clone());
      return res;
    }));
    return;
  }

  e.respondWith(fetch(e.request).then(res => {          // shell: network first, cache if offline
    if (res.ok) { const copy = res.clone(); caches.open(SHELL).then(c => c.put(e.request, copy)); }
    return res;
  }).catch(() => caches.match(e.request)));
});
