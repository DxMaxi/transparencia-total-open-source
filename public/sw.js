const CACHE_PREFIX = "transparencia-total-";
const CACHE_VERSION = "v4";
const STATIC_CACHE = `${CACHE_PREFIX}${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_PREFIX}${CACHE_VERSION}-runtime`;
const OFFLINE_URL = "/offline.html";
const PRECACHE = [
  "/",
  "/politicos",
  "/atividade-parlamentar",
  "/promessas",
  "/guia-cidadao",
  "/metodologia",
  "/direito-de-resposta",
  OFFLINE_URL,
  "/manifest.json",
  "/favicon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];
const PRIVATE_PATH_PREFIXES = ["/admin", "/auth", "/api"];

function isPrivatePath(pathname) {
  return PRIVATE_PATH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function isPublicRequest(request, url) {
  return (
    request.method === "GET"
    && url.origin === self.location.origin
    && !isPrivatePath(url.pathname)
    && !request.headers.has("authorization")
  );
}

function isCacheableResponse(response) {
  if (!response || !response.ok || response.type === "opaque") return false;
  const cacheControl = (response.headers.get("cache-control") || "").toLowerCase();
  return !/(^|,)\s*(private|no-store)(\s|,|$)/.test(cacheControl);
}

async function storeRuntime(request, response) {
  if (!isCacheableResponse(response)) return;
  const cache = await caches.open(RUNTIME_CACHE);
  await cache.put(request, response.clone());
}

function safeNotificationTarget(value) {
  try {
    const target = new URL(typeof value === "string" ? value : "/", self.location.origin);
    if (target.origin !== self.location.origin || isPrivatePath(target.pathname)) return "/";
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return "/";
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter(
            (key) =>
              key.startsWith(CACHE_PREFIX)
              && ![STATIC_CACHE, RUNTIME_CACHE].includes(key),
          )
          .map((key) => caches.delete(key)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (!isPublicRequest(request, url)) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then(async (response) => {
          await storeRuntime(request, response);
          return response;
        })
        .catch(async () => (await caches.match(request)) || (await caches.match(OFFLINE_URL))),
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cached = await caches.match(request);
      if (cached) return cached;
      return fetch(request).then(async (response) => {
        await storeRuntime(request, response);
        return response;
      });
    })(),
  );
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data?.text() };
  }
  const title = data.title || "Transparência Total";
  const options = {
    body: data.body || "Há uma nova atualização oficial.",
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-96.png",
    tag: data.tag || "transparencia-total-update",
    renotify: false,
    data: { url: safeNotificationTarget(data.url) },
    actions: [{ action: "open", title: "Ver fonte" }],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(
    safeNotificationTarget(event.notification.data?.url),
    self.location.origin,
  ).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url === target && "focus" in client) return client.focus();
      }
      return self.clients.openWindow ? self.clients.openWindow(target) : undefined;
    }),
  );
});
