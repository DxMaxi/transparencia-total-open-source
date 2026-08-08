"use client";

import { useEffect } from "react";

const LEGACY_CACHE_PREFIX = "transparencia-total-";

/** Remove apenas infraestrutura PWA criada por versões públicas anteriores. */
export function BrowserStorageCleanup() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.getRegistrations()
        .then((registrations) =>
          Promise.all(
            registrations
              .filter((registration) => {
                const scriptUrl = registration.active?.scriptURL
                  ?? registration.waiting?.scriptURL
                  ?? registration.installing?.scriptURL;
                return scriptUrl ? new URL(scriptUrl).pathname === "/sw.js" : false;
              })
              .map((registration) => registration.unregister()),
          ),
        )
        .catch(() => undefined);
    }

    if ("caches" in window) {
      void caches.keys()
        .then((keys) =>
          Promise.all(
            keys
              .filter((key) => key.startsWith(LEGACY_CACHE_PREFIX))
              .map((key) => caches.delete(key)),
          ),
        )
        .catch(() => undefined);
    }
  }, []);

  return null;
}
