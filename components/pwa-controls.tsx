"use client";

import { useEffect, useState } from "react";

type PwaState = "checking" | "inactive" | "working" | "active" | "unsupported" | "error";

const PROJECT_CACHE_PREFIX = "transparencia-total-";

function isProjectRegistration(registration: ServiceWorkerRegistration): boolean {
  const worker = registration.installing ?? registration.waiting ?? registration.active;
  if (!worker) return false;
  const workerUrl = new URL(worker.scriptURL);
  return workerUrl.origin === window.location.origin && workerUrl.pathname === "/sw.js";
}

export function PwaControls() {
  const [state, setState] = useState<PwaState>("checking");

  useEffect(() => {
    let cancelled = false;

    async function inspect() {
      if (!("serviceWorker" in navigator)) {
        if (!cancelled) setState("unsupported");
        return;
      }
      try {
        const registrations = await navigator.serviceWorker.getRegistrations();
        if (!cancelled) {
          setState(registrations.some(isProjectRegistration) ? "active" : "inactive");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    }

    void inspect();
    return () => {
      cancelled = true;
    };
  }, []);

  async function enableOfflineMode() {
    if (!("serviceWorker" in navigator)) {
      setState("unsupported");
      return;
    }
    setState("working");
    try {
      await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      setState("active");
    } catch {
      setState("error");
    }
  }

  async function disableOfflineMode() {
    if (!("serviceWorker" in navigator)) {
      setState("unsupported");
      return;
    }
    setState("working");
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(
        registrations.filter(isProjectRegistration).map((registration) => registration.unregister()),
      );
      if ("caches" in window) {
        const keys = await window.caches.keys();
        await Promise.all(
          keys
            .filter((key) => key.startsWith(PROJECT_CACHE_PREFIX))
            .map((key) => window.caches.delete(key)),
        );
      }
      setState("inactive");
    } catch {
      setState("error");
    }
  }

  const message: Record<PwaState, string> = {
    checking: "A verificar a preferência deste navegador…",
    inactive: "Desativado. Nenhum cache offline do projeto é criado.",
    working: "A aplicar a sua escolha…",
    active: "Ativo. Páginas públicas e recursos essenciais podem ficar disponíveis sem rede.",
    unsupported: "Este navegador não suporta o modo offline.",
    error: "Não foi possível aplicar a escolha. Pode tentar novamente.",
  };

  const busy = state === "checking" || state === "working";

  return (
    <section className="pwa-controls" aria-labelledby="pwa-controls-title">
      <span className="pwa-controls__title" id="pwa-controls-title">Modo offline</span>
      <p className="pwa-controls__status" aria-live="polite">{message[state]}</p>
      {state === "active" ? (
        <button
          className="pwa-controls__button"
          type="button"
          onClick={disableOfflineMode}
          disabled={busy}
        >
          Desativar e apagar cache
        </button>
      ) : (
        <button
          className="pwa-controls__button"
          type="button"
          onClick={enableOfflineMode}
          disabled={busy || state === "unsupported"}
        >
          {state === "error" ? "Tentar ativar novamente" : "Ativar modo offline"}
        </button>
      )}
      <a href="/cookies">Como funciona o armazenamento</a>
    </section>
  );
}
