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
  const liveWithoutDataset = status.mode === "LIVE" && showingFallback;
  return (
    <aside className="data-mode-banner data-mode-banner--fallback" role="note">
      {unavailable ? <ClockIcon /> : <ShieldCheckIcon />}
      <div>
        <strong>
          {liveWithoutDataset
            ? "Sem registos publicados neste módulo."
            : unavailable
              ? "Dados oficiais temporariamente indisponíveis."
              : "Base ligada, ainda sem registos aprovados."}
        </strong>
        <span>
          {status.message}
        </span>
      </div>
    </aside>
  );
}
