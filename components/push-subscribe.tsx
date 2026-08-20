"use client";

import { useEffect, useState } from "react";
import { BellIcon } from "@/components/icons";

type SubscribeState =
  | "checking"
  | "idle"
  | "loading"
  | "enabled"
  | "disabling"
  | "removal-pending"
  | "unsupported"
  | "unavailable"
  | "error";

const regions = [
  "Aveiro",
  "Beja",
  "Braga",
  "Bragança",
  "Castelo Branco",
  "Coimbra",
  "Évora",
  "Faro",
  "Guarda",
  "Leiria",
  "Lisboa",
  "Portalegre",
  "Porto",
  "Santarém",
  "Setúbal",
  "Viana do Castelo",
  "Vila Real",
  "Viseu",
  "Região Autónoma dos Açores",
  "Região Autónoma da Madeira",
];
const OFFLINE_PREFERENCE_CACHE = "transparencia-total-offline-preference";

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((character) => character.charCodeAt(0)));
}

export function PushSubscribe() {
  const [state, setState] = useState<SubscribeState>("checking");
  const [district, setDistrict] = useState("");
  const [municipality, setMunicipality] = useState("");
  const [consent, setConsent] = useState(false);
  const [pendingRemovalEndpoint, setPendingRemovalEndpoint] = useState<string | null>(null);

  const publicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  useEffect(() => {
    let cancelled = false;

    async function inspect() {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        if (!cancelled) setState("unsupported");
        return;
      }
      try {
        const registration = await navigator.serviceWorker.getRegistration("/");
        const subscription = await registration?.pushManager.getSubscription();
        if (!cancelled) {
          setState(subscription ? "enabled" : publicKey && apiUrl ? "idle" : "unavailable");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    }

    void inspect();
    return () => {
      cancelled = true;
    };
  }, [apiUrl, publicKey]);

  async function subscribe() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }

    let createdSubscription: PushSubscription | null = null;
    let subscriptionRegistration: ServiceWorkerRegistration | null = null;
    try {
      setState("loading");
      let registration = await navigator.serviceWorker.getRegistration("/");
      let subscription = await registration?.pushManager.getSubscription();
      if (!subscription) {
        if (!consent) {
          setState("idle");
          return;
        }
        if (!publicKey || !apiUrl) {
          setState("unavailable");
          return;
        }
        const permission = await Notification.requestPermission();
        if (permission !== "granted") {
          setState("error");
          return;
        }
        registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
        await navigator.serviceWorker.ready;
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        });
        createdSubscription = subscription;
        subscriptionRegistration = registration;
      }

      if (!apiUrl) {
        setState("unavailable");
        return;
      }

      const response = await fetch(`${apiUrl}/api/v1/push/subscriptions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subscription: subscription.toJSON(),
          districts: district ? [district] : [],
          municipalities: municipality.trim() ? [municipality.trim()] : [],
        }),
      });

      if (!response.ok) throw new Error("Subscription rejected");
      setPendingRemovalEndpoint(null);
      setState("enabled");
    } catch {
      if (createdSubscription) await createdSubscription.unsubscribe().catch(() => false);
      if (subscriptionRegistration) {
        const keepForOffline = "caches" in window
          && await window.caches.has(OFFLINE_PREFERENCE_CACHE).catch(() => false);
        if (!keepForOffline) await subscriptionRegistration.unregister().catch(() => false);
      }
      setState("error");
    }
  }

  async function unsubscribe() {
    if (!("serviceWorker" in navigator)) {
      setState("unsupported");
      return;
    }
    try {
      setState("disabling");
      const registration = await navigator.serviceWorker.getRegistration("/");
      const subscription = await registration?.pushManager.getSubscription();
      const endpoint = pendingRemovalEndpoint || subscription?.endpoint;
      if (!endpoint) {
        setConsent(false);
        setState("idle");
        return;
      }

      let backendRemoved = false;
      if (apiUrl) {
        try {
          const response = await fetch(`${apiUrl}/api/v1/push/subscriptions`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint }),
          });
          backendRemoved = response.ok;
        } catch {
          backendRemoved = false;
        }
      }

      if (subscription) {
        const browserRemoved = await subscription.unsubscribe();
        if (!browserRemoved) throw new Error("Browser subscription removal failed");
        const keepForOffline = "caches" in window
          && await window.caches.has(OFFLINE_PREFERENCE_CACHE);
        if (!keepForOffline) await registration?.unregister();
      }

      setConsent(false);
      setPendingRemovalEndpoint(backendRemoved ? null : endpoint);
      setState(backendRemoved ? "idle" : "removal-pending");
    } catch {
      setState("error");
    }
  }

  const labels: Record<SubscribeState, string> = {
    checking: "A verificar este navegador…",
    idle: "Ativar alertas da minha região",
    loading: "A guardar…",
    enabled: "Guardar preferências",
    disabling: "A desativar…",
    "removal-pending": "Tentar apagar o registo no servidor",
    unsupported: "Alertas não suportados neste navegador",
    unavailable: "Alertas ainda indisponíveis",
    error: "Não foi possível aplicar a escolha",
  };

  const busy = state === "checking" || state === "loading" || state === "disabling";
  const canSubscribe = Boolean(
    apiUrl && district && (state === "enabled" || (publicKey && consent)),
  );
  const showConsent = state === "idle" || state === "loading" || state === "error";

  return (
    <div className="push-subscribe">
      <div className="push-region-fields">
        <label>
          <span>Distrito ou região</span>
          <select value={district} onChange={(event) => setDistrict(event.target.value)}>
            <option value="">Escolher região</option>
            {regions.map((region) => <option value={region} key={region}>{region}</option>)}
          </select>
        </label>
        <label>
          <span>Concelho (opcional)</span>
          <input
            value={municipality}
            onChange={(event) => setMunicipality(event.target.value)}
            placeholder="Ex.: Sintra"
            autoComplete="address-level2"
          />
        </label>
      </div>
      {showConsent ? (
        <label className="push-consent">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            disabled={busy}
          />
          <span>
            Quero receber alertas desta região. Compreendo que isto ativa o serviço técnico
            necessário no navegador e que posso apagar a subscrição a qualquer momento.
          </span>
        </label>
      ) : null}
      <div className="push-actions">
        {state !== "removal-pending" ? (
          <button
            className="button button--light"
            type="button"
            onClick={subscribe}
            disabled={
              !canSubscribe
              || busy
              || state === "unsupported"
              || state === "unavailable"
            }
          >
            <BellIcon /> {labels[state]}
          </button>
        ) : null}
        {state === "enabled" || state === "removal-pending" ? (
          <button
            className="button button--ghost push-remove"
            type="button"
            onClick={unsubscribe}
            disabled={busy}
          >
            {state === "removal-pending"
              ? "Tentar apagar o registo no servidor"
              : "Desativar e apagar alertas"}
          </button>
        ) : null}
      </div>
      <p className="push-status" role="status" aria-live="polite">
        {state === "enabled"
          ? "Alertas ativos neste navegador. Pode alterar a região ou apagar a subscrição."
          : state === "removal-pending"
            ? "Os alertas já estão desligados neste navegador. Falta confirmar a eliminação do registo no servidor; pode tentar novamente."
            : labels[state]}
      </p>
      <small>
        A região é indicada por si; não usamos geolocalização, publicidade nem perfis de navegação.
        Só conteúdo aprovado pode originar um alerta. Consulte a <a href="/privacidade">política de
        privacidade</a>.
      </small>
    </div>
  );
}
