import { CheckIcon, ClockIcon, ShieldCheckIcon } from "@/components/icons";
import type { PublicDataStatus } from "@/types/public-data";

export function DataModeBanner({
  status,
  showingFallback,
}: {
  status: PublicDataStatus;
  showingFallback: boolean;
}) {
  if (status.mode === "LIVE" && !showingFallback) {
    return (
      <aside className="data-mode-banner data-mode-banner--live" role="status">
        <CheckIcon />
        <div>
          <strong>Dados oficiais publicados.</strong>
          <span>{status.message} Cada registo conserva fonte e revisão.</span>
        </div>
      </aside>
    );
  }

  const unavailable = status.mode === "UNAVAILABLE";
  const empty = status.mode === "EMPTY";
  const liveWithoutDataset = status.mode === "LIVE" && showingFallback;
  return (
    <aside className="data-mode-banner data-mode-banner--fallback" role="note">
      {unavailable ? <ClockIcon /> : <ShieldCheckIcon />}
      <div>
        <strong>
          {liveWithoutDataset
            ? "Sem registos publicados neste módulo."
            : empty
            ? "Base ligada, ainda sem registos aprovados."
            : unavailable
              ? "API temporariamente indisponível."
              : "Protótipo com dados demonstrativos."}
        </strong>
        <span>
          {showingFallback
            ? "A amostra abaixo é fictícia e está isolada dos dados oficiais."
            : status.message}
        </span>
      </div>
    </aside>
  );
}
