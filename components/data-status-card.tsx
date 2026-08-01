import { CheckIcon, ClockIcon } from "@/components/icons";
import type { PublicDataStatus } from "@/types/public-data";

const sourceLabels: Record<string, string> = {
  PARLIAMENT_DEPUTIES: "Deputados AR",
  PARLIAMENT_VOTES: "Votações AR",
  BASE_CONTRACTS: "Contratos BASE",
  DRE: "Diplomas DRE",
  TRANSPARENCY_ENTITY: "Entidade Transparência",
  LOCAL_SNS: "Radar local / SNS",
};

export function DataStatusCard({ status }: { status: PublicDataStatus }) {
  const live = status.mode === "LIVE";
  const total = Object.values(status.counts).reduce((sum, count) => sum + count, 0);
  return (
    <div className="hero-dashboard" aria-label="Estado auditável dos dados">
      <div className="hero-dashboard__header">
        <div><span className={live ? "live-dot" : "live-dot live-dot--idle"} /><span>Estado dos dados</span></div>
        <span className={`mode-chip mode-chip--${status.mode.toLowerCase()}`}>
          {live ? "Dados publicados" : status.mode === "EMPTY" ? "Em revisão" : "Demonstração"}
        </span>
      </div>
      <div className="hero-dashboard__body">
        <div className="dashboard-title-row">
          <div><span>Publicação controlada</span><strong>{total} registos aprovados</strong></div>
          {live ? <CheckIcon /> : <ClockIcon />}
        </div>
        <div className="dashboard-public-counts">
          <div><strong>{status.counts.politicians}</strong><span>perfis</span></div>
          <div><strong>{status.counts.promises}</strong><span>promessas</span></div>
          <div><strong>{status.counts.contracts}</strong><span>contratos</span></div>
          <div><strong>{status.counts.relationships}</strong><span>relações</span></div>
        </div>
        <div className="sync-source-list" aria-label="Cobertura das sincronizações">
          {status.sources.slice(0, 6).map((source) => (
            <div key={source.sourceName}>
              <span>{sourceLabels[source.sourceName] ?? source.sourceName}</span>
              <strong className={`sync-state sync-state--${source.status.toLowerCase()}`}>
                {source.status === "NEVER" ? "Sem recolha" : source.status}
              </strong>
            </div>
          ))}
        </div>
        <div className="audit-note"><CheckIcon /> Ingestão e publicação são etapas separadas; falhas e lacunas permanecem visíveis.</div>
      </div>
    </div>
  );
}
