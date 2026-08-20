"use client";

import { useEffect, useState } from "react";

type PwaState = "checking" | "inactive" | "working" | "active" | "unsupported" | "error";

const PROJECT_CACHE_PREFIX = "transparencia-total-";
const OFFLINE_PREFERENCE_CACHE = `${PROJECT_CACHE_PREFIX}offline-preference`;

function isProjectRegistration(registration: ServiceWorkerRegistration): boolean {
  const worker = registration.installing ?? registration.waiting ?? registration.active;
  if (!worker) return false;
  const workerUrl = new URL(worker.scriptURL);
  return workerUrl.origin === window.location.origin && workerUrl.pathname === "/sw.js";
}

async function sendOfflineCommand(
  registration: ServiceWorkerRegistration,
  type: "ENABLE_OFFLINE" | "DISABLE_OFFLINE",
): Promise<void> {
  const worker = registration.active;
  if (!worker) throw new Error("Service worker ainda não está ativo");

  await new Promise<void>((resolve, reject) => {
    const channel = new MessageChannel();
    const timeout = window.setTimeout(
      () => reject(new Error("Service worker não confirmou a escolha")),
      10_000,
    );
    channel.port1.onmessage = (event) => {
      window.clearTimeout(timeout);
      if (event.data?.ok === true) resolve();
      else reject(new Error("Service worker recusou a escolha"));
    };
    worker.postMessage({ type }, [channel.port2]);
  });
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
        const enabled = "caches" in window
          && await window.caches.has(OFFLINE_PREFERENCE_CACHE);
        if (!cancelled) {
          setState(enabled ? "active" : "inactive");
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
      const registration = await navigator.serviceWorker.ready;
      await sendOfflineCommand(registration, "ENABLE_OFFLINE");
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
      const projectRegistrations = registrations.filter(isProjectRegistration);
      for (const registration of projectRegistrations) {
        await sendOfflineCommand(registration, "DISABLE_OFFLINE");
        const pushSubscription = await registration.pushManager.getSubscription();
        if (!pushSubscription) await registration.unregister();
      }
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
