/* Автогенерация generate_js_rules.py: кэш версионируется хэшем каждого precache-ресурса. */
const CACHE = "humanizer-ru-0c11663f8d02";
const STATIC = ["./", "./index.html", "./brand.css", "./markers.js", "./engine.js", "./sample.js", "./favicon.svg", "./manifest.json", "./cleaner-rules.js", "./cleaner.js"];
self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC)));
});
self.addEventListener("activate", (e) => {
  clients.claim();
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k.startsWith("humanizer-ru-") && k !== CACHE)
      .map((k) => caches.delete(k)))));
});
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const requestUrl = new URL(e.request.url);
  if (requestUrl.pathname.endsWith("/status.json")) {
    e.respondWith(fetch(e.request));
    return;
  }
  e.respondWith(caches.open(CACHE).then((c) => c.match(e.request).then((hit) => hit ||
    fetch(e.request).then((res) => {
      const copy = res.clone();
      c.put(e.request, copy);
      return res;
    }))));
});
