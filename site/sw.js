// START_MODULE_CONTRACT
// PURPOSE: Retire the legacy-v3 offline service worker (/humanizer-ru/sw.js), purge old CacheStorage
//          entries (humanizer-ru-*), unregister the worker, and reload open v3 tabs into v4.
// SCOPE: Fetched only by browsers that still hold a legacy-v3 service worker registration; v4 pages
//        do not register a service worker.
// DEPENDS: Browser ServiceWorkerGlobalScope API.
// LINKS: M-SITE-CHECK; V-M-SITE-CHECK.
// END_MODULE_CONTRACT
"use strict";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      try {
        await self.clients.claim();
      } catch (_) {}
      try {
        const keys = await self.caches.keys();
        await Promise.all(keys.map((key) => self.caches.delete(key)));
      } catch (_) {}
      let list = [];
      try {
        list = await self.clients.matchAll({ type: "window" });
      } catch (_) {}
      try {
        await self.registration.unregister();
      } catch (_) {}
      for (const client of list) {
        try {
          if (typeof client.navigate === "function") {
            await client.navigate(client.url);
          }
        } catch (_) {}
      }
    })()
  );
});
