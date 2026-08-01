"use client";

import { useState } from "react";
import { BellIcon } from "@/components/icons";

type SubscribeState = "idle" | "loading" | "enabled" | "unsupported" | "error";

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

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((character) => character.charCodeAt(0)));
}

export function PushSubscribe() {
  const [state, setState] = useState<SubscribeState>("idle");
  const [district, setDistrict] = useState("");
  const [municipality, setMunicipality] = useState("");

  async function subscribe() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }

    const publicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!publicKey || !apiUrl) {
      setState("error");
      return;
    }

    try {
      setState("loading");
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState("error");
        return;
      }

      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });

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
      setState("enabled");
    } catch {
      setState("error");
    }
  }

  const labels: Record<SubscribeState, string> = {
    idle: "Ativar alertas da minha região",
    loading: "A ativar…",
    enabled: "Alertas ativados",
    unsupported: "Alertas não suportados neste navegador",
    error: "Configuração necessária para ativar alertas",
  };

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
      <button
        className="button button--light"
        type="button"
        onClick={subscribe}
        disabled={
          !district || state === "loading" || state === "enabled" || state === "unsupported"
        }
      >
        <BellIcon /> {labels[state]}
      </button>
      <small>A região é indicada por si; não usamos geolocalização automática.</small>
    </div>
  );
}
