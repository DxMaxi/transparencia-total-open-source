import { CheckIcon, ClockIcon } from "@/components/icons";
import type { PublicDataStatus } from "@/types/public-data";

const sourceLabels: Record<string, string> = {
  PARLIAMENT_DEPUTIES: "Deputados AR",
  PARLIAMENT_ACTIVITY: "Atividade AR",
  PARLIAMENT_VOTES: "Votações AR",
  BASE_CONTRACTS: "Catálogo BASE",
  DRE: "Índice DRE",
  TRANSPARENCY_ENTITY: "Índice EPT",
  LOCAL_SNS: "Índice SNS",
};

const syncStateLabels: Record<string, string> = {
  NEVER: "Sem recolha",
  RUNNING: "A atualizar",
  SUCCEEDED: "Atualizado",
  PARTIAL: "Parcial",
  FAILED: "Falhou",
};

export function DataStatusCard({ status }: { status: PublicDataStatus }) {
  const live = status.mode === "LIVE";
  const total = Object.values(status.counts).reduce((sum, count) => sum + count, 0);
  return (
    <div className="hero-dashboard" aria-label="Estado auditável dos dados">
      <div className="hero-dashboard__header">
        <div><span className={live ? "live-dot" : "live-dot live-dot--idle"} /><span>Estado dos dados</span></div>
        <span className={`mode-chip mode-chip--${status.mode.toLowerCase()}`}>
          {live ? "Dados publicados" : status.mode === "EMPTY" ? "Em revisão" : "Indisponível"}
        </span>
      </div>
      <div className="hero-dashboard__body">
        <div className="dashboard-title-row">
          <div><span>Publicação controlada</span><strong>{total} registos aprovados</strong></div>
          {live ? <CheckIcon /> : <ClockIcon />}
        </div>
        <div className="dashboard-public-counts">
          <div><strong>{status.counts.politicians}</strong><span>perfis</span></div>
          <div><strong>{status.counts.parliamentInitiatives}</strong><span>iniciativas</span></div>
          <div><strong>{status.counts.parliamentVotes}</strong><span>votações</span></div>
          <div><strong>{status.counts.parliamentSessions}</strong><span>reuniões</span></div>
        </div>
        <div className="sync-source-list" aria-label="Cobertura das sincronizações">
          {status.sources.slice(0, 7).map((source) => (
            <div key={source.sourceName}>
              <span>{sourceLabels[source.sourceName] ?? source.sourceName}</span>
              <strong className={`sync-state sync-state--${source.status.toLowerCase()}`}>
                {syncStateLabels[source.status] ?? "Estado desconhecido"}
              </strong>
            </div>
          ))}
        </div>
        <div className="audit-note"><CheckIcon /> Recolha e publicação são etapas separadas; índices recolhidos não equivalem a factos aprovados.</div>
      </div>
    </div>
  );
}
