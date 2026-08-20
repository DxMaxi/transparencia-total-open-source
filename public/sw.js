const CACHE_PREFIX = "transparencia-total-";
const CACHE_VERSION = "v5";
const STATIC_CACHE = `${CACHE_PREFIX}${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_PREFIX}${CACHE_VERSION}-runtime`;
const OFFLINE_PREFERENCE_CACHE = `${CACHE_PREFIX}offline-preference`;
const OFFLINE_MARKER = "/__tt-offline-enabled__";
const OFFLINE_URL = "/offline.html";
let offlineModeEnabled = false;
const PRECACHE = [
  "/",
  "/politicos",
  "/atividade-parlamentar",
  "/promessas",
  "/pesquisa",
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
const PUBLIC_PAGE_PATHS = new Set([
  "/",
  "/acessibilidade",
  "/atividade-parlamentar",
  "/contacto",
  "/cookies",
  "/direito-de-resposta",
  "/explicacoes",
  "/guia-cidadao",
  "/investigador",
  "/metodologia",
  "/politicos",
  "/pesquisa",
  "/privacidade",
  "/promessas",
  "/termos",
  "/offline.html",
  "/manifest.json",
  "/favicon.svg",
  "/robots.txt",
  "/sitemap.xml",
]);
const PUBLIC_ASSET_PREFIXES = ["/_next/static/", "/_next/image/", "/icons/"];
const PUBLIC_RECORD_PREFIXES = ["/explicacoes/", "/politicos/"];

function isPrivatePath(pathname) {
  return PRIVATE_PATH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function isExplicitlyCacheablePath(url) {
  if (PUBLIC_ASSET_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) return true;
  if (url.search) return false;
  return (
    PUBLIC_PAGE_PATHS.has(url.pathname)
    || PUBLIC_RECORD_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))
  );
}

function isPublicRequest(request, url) {
  return (
    request.method === "GET"
    && url.origin === self.location.origin
    && !isPrivatePath(url.pathname)
    && isExplicitlyCacheablePath(url)
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

function offlineMarkerRequest() {
  return new Request(new URL(OFFLINE_MARKER, self.location.origin));
}

async function hasOfflinePreference() {
  if (!(await caches.has(OFFLINE_PREFERENCE_CACHE))) return false;
  const preference = await caches.open(OFFLINE_PREFERENCE_CACHE);
  return Boolean(await preference.match(offlineMarkerRequest()));
}

async function enableOfflineMode() {
  try {
    const staticCache = await caches.open(STATIC_CACHE);
    await staticCache.addAll(PRECACHE);
    const preference = await caches.open(OFFLINE_PREFERENCE_CACHE);
    await preference.put(offlineMarkerRequest(), new Response("enabled"));
    offlineModeEnabled = true;
  } catch (error) {
    await caches.delete(STATIC_CACHE);
    throw error;
  }
}

async function disableOfflineMode() {
  offlineModeEnabled = false;
  await Promise.all([
    caches.delete(STATIC_CACHE),
    caches.delete(RUNTIME_CACHE),
    caches.delete(OFFLINE_PREFERENCE_CACHE),
  ]);
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
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      const legacyOfflineChoice = keys.some(
        (key) =>
          key.startsWith(CACHE_PREFIX)
          && key.endsWith("-static")
          && key !== STATIC_CACHE,
      );
      if (legacyOfflineChoice && !(await hasOfflinePreference())) {
        const preference = await caches.open(OFFLINE_PREFERENCE_CACHE);
        await preference.put(offlineMarkerRequest(), new Response("enabled"));
      }
      offlineModeEnabled = await hasOfflinePreference();
      if (offlineModeEnabled) await enableOfflineMode();
      await Promise.all(
        keys
          .filter(
            (key) =>
              key.startsWith(CACHE_PREFIX)
              && ![STATIC_CACHE, RUNTIME_CACHE, OFFLINE_PREFERENCE_CACHE].includes(key),
          )
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (!["ENABLE_OFFLINE", "DISABLE_OFFLINE"].includes(event.data?.type)) return;
  const operation = event.data.type === "ENABLE_OFFLINE"
    ? enableOfflineMode()
    : disableOfflineMode();
  event.waitUntil(
    operation
      .then(() => event.ports[0]?.postMessage({ ok: true }))
      .catch(() => event.ports[0]?.postMessage({ ok: false })),
  );
});

self.addEventListener("fetch", (event) => {
  if (!offlineModeEnabled) return;
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
