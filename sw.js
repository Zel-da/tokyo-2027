/* 오프라인용 서비스 워커
   - 일정·경로·환율: 네트워크를 3초만 기다리고, 늦으면 저장본을 보여 줘요(역 와이파이·지하철 대비).
   - 라이브러리: 설치할 때 미리 저장해요.
   - 지도 타일: 한 번 본 것만 저장해요(최대 800장). */
const V = "tokyo27-v7";
const CORE = ["./", "index.html", "paths.json", "rates.json", "manifest.webmanifest", "icons/icon-192.png", "icons/apple-touch-icon.png"];
const LIBS = [
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  "https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js",
  "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore-compat.js",
  "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
];
const TILE_HOSTS = ["tile.openstreetmap.org", "cyberjapandata.gsi.go.jp"];
const LIB_HOSTS = ["cdnjs.cloudflare.com", "cdn.jsdelivr.net", "www.gstatic.com"];
const MAX_TILES = 800;
const NET_TIMEOUT = 3000;

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    await (await caches.open(V)).addAll(CORE);
    const libs = await caches.open(V + "-libs");
    await Promise.allSettled(LIBS.map(u => libs.add(u)));
    await self.skipWaiting();
  })());
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => !k.startsWith(V)).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function safePut(cache, req, res) {
  try { await cache.put(req, res); } catch (e) { /* 용량 초과 등: 저장만 건너뛰어요 */ }
}

async function networkFirst(req, cacheName) {
  const c = await caches.open(cacheName);
  const cached = await c.match(req) || (req.mode === "navigate" ? await c.match("index.html") : undefined);
  const net = fetch(req).then(r => { if (r.ok) safePut(c, req, r.clone()); return r; });
  if (!cached) return net;
  // 저장본이 있으면 네트워크는 3초까지만 기다려요.
  const timeout = new Promise(res => setTimeout(() => res(cached), NET_TIMEOUT));
  return Promise.race([net.catch(() => cached), timeout]);
}

async function cacheFirst(req, cacheName, limit) {
  const c = await caches.open(cacheName);
  const hit = await c.match(req);
  if (hit) return hit;
  const r = await fetch(req);
  if (r.ok) {
    await safePut(c, req, r.clone());
    if (limit) {
      const keys = await c.keys();
      if (keys.length > limit) await Promise.all(keys.slice(0, keys.length - limit).map(k => c.delete(k)));
    }
  }
  return r;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const u = new URL(req.url);
  if (u.hostname.endsWith("googleapis.com")) return; // Firestore 는 SDK 가 직접 처리
  if (u.origin === location.origin) { e.respondWith(networkFirst(req, V)); return; }
  if (TILE_HOSTS.some(h => u.hostname.endsWith(h))) { e.respondWith(cacheFirst(req, V + "-tiles", MAX_TILES)); return; }
  if (LIB_HOSTS.some(h => u.hostname.endsWith(h))) { e.respondWith(cacheFirst(req, V + "-libs")); return; }
  if (u.hostname.includes("open-meteo.com") || u.hostname.includes("frankfurter")) { e.respondWith(networkFirst(req, V + "-api")); return; }
});
