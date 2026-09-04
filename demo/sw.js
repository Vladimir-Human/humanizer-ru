/* Автогенерация generate_js_rules.py: кэш версионируется хэшем правил. */
const CACHE = "humanizer-ru-c808bde3f31b";
const STATIC = ["./", "./index.html", "./brand.css", "./markers.js",
  "./engine.js", "./sample.js", "./favicon.svg", "./manifest.json"];
self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC)));
});
self.addEventListener("activate", (e) => {
  clients.claim();
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
});
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  e.respondWith(caches.match(e.request).then((hit) => hit ||
    fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
      return res;
    })));
});
