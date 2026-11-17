/* BLOCK HARBOR offline cache.
   Everything is stored in the browser's private Cache Storage (not visible in phone storage, gallery or downloads).
   To force a re-download after replacing a .glb file, bump ASSET_CACHE (e.g. bh-assets-v2). */
const APP_CACHE = 'bh-app-v1';        // index.html (updated in the background on every visit)
const ASSET_CACHE = 'bh-assets-v1';   // .glb models: downloaded once, then always served from the cache
const CDN_CACHE = 'bh-cdn-v1';        // three.js from jsDelivr (pinned version) and fonts
const GLBS = ['./character.glb', './environment.glb', './AK117.glb'];

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(APP_CACHE).then(c => Promise.all(['./', './index.html'].map(u => c.add(u).catch(() => {})))));
});
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (![APP_CACHE, ASSET_CACHE, CDN_CACHE].includes(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});
async function cacheFirst(name, req) {
  const c = await caches.open(name), hit = await c.match(req, { ignoreSearch: true });
  if (hit) return hit;
  const res = await fetch(req);
  if (res && (res.ok || res.type === 'opaque')) c.put(req, res.clone()).catch(() => {});
  return res;
}
async function staleWhileRevalidate(name, req) {
  const c = await caches.open(name), hit = await c.match(req, { ignoreSearch: true });
  const net = fetch(req).then(res => { if (res && res.ok) c.put(req, res.clone()).catch(() => {}); return res; }).catch(() => null);
  return hit || (await net) || new Response('offline', { status: 503 });
}
self.addEventListener('fetch', e => {
  const r = e.request; if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin === location.origin) {
    if (/\.glb$/i.test(u.pathname)) return e.respondWith(cacheFirst(ASSET_CACHE, r));
    return e.respondWith(staleWhileRevalidate(APP_CACHE, r));
  }
  if (/(^|\.)jsdelivr\.net$|^fonts\.(googleapis|gstatic)\.com$|^cdnjs\.cloudflare\.com$/.test(u.hostname)) e.respondWith(cacheFirst(CDN_CACHE, r));
});
// the page asks us to pre-download the models once, right after the first visit
self.addEventListener('message', e => {
  if (!e.data || e.data.type !== 'warm') return;
  e.waitUntil((async () => {
    const c = await caches.open(ASSET_CACHE); let added = false;
    for (const u of GLBS) { if (!(await c.match(u))) { try { const res = await fetch(u); if (res.ok) { await c.put(u, res); added = true; } } catch (_) {} } }
    const all = await self.clients.matchAll();
    if (added) all.forEach(cl => cl.postMessage({ type: 'cached' }));
  })());
});
