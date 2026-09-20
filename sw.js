// Cache the app shell up front; cache audio clips the first time each is heard.
const SHELL = 'nghe-shell-v1';
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

  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});
