import { CheckIcon, ClockIcon } from "@/components/icons";
import type { PublicDataStatus } from "@/types/public-data";

const sourceLabels: Record<string, string> = {
  PARLIAMENT_DEPUTIES: "Deputados AR",
  PARLIAMENT_ACTIVITY: "Atividade AR",
  PARLIAMENT_VOTES: "Votações AR",
  BASE_CONTRACTS: "Catálogo BASE",
  DRE: "Índice DRE",
  TRANSPARENCY_ENTITY: "Índice EPT",
  COURT_OF_AUDIT: "Tribunal de Contas",
  EUROPEAN_PARLIAMENT: "Parlamento Europeu",
  LOCAL_SNS: "Portal da Transparência do SNS",
  GOVERNMENT_PROGRAMME: "Programa do Governo",
};

const syncStateLabels: Record<string, string> = {
  NEVER: "Sem recolha",
  RUNNING: "A atualizar",
  SUCCEEDED: "Atualizado",
  PARTIAL: "Parcial",
  FAILED: "Falhou",
};

const MAX_SOURCE_AGE_HOURS = 36;
const MAX_SOURCE_AGE_MS = MAX_SOURCE_AGE_HOURS * 60 * 60 * 1000;

function syncStatePresentation(
  source: PublicDataStatus["sources"][number],
  generatedAt: string,
) {
  const current = {
    label: syncStateLabels[source.status] ?? "Estado desconhecido",
    statusClass: source.status.toLowerCase(),
  };
  if (source.status !== "SUCCEEDED" && source.status !== "PARTIAL") return current;

  const referenceTime = Date.parse(generatedAt);
  const finishedAt = source.finishedAt ? Date.parse(source.finishedAt) : Number.NaN;
  const missingTimestamp = !Number.isFinite(referenceTime) || !Number.isFinite(finishedAt);
  if (missingTimestamp) {
    return {
      label: source.status === "PARTIAL" ? "Parcial sem data" : "Sem data",
      statusClass: "stale",
    };
  }
  if (referenceTime - finishedAt > MAX_SOURCE_AGE_MS) {
    return {
      label: source.status === "PARTIAL" ? "Parcial antigo" : "Desatualizado",
      statusClass: "stale",
    };
  }
  return current;
}

export function DataStatusCard({ status }: { status: PublicDataStatus }) {
  const live = status.mode === "LIVE";
  const total = Object.values(status.counts).reduce((sum, count) => sum + count, 0);
  const visibleSources = status.sources.filter((source) => source.sourceName in sourceLabels);
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
          {visibleSources.map((source) => {
            const presentation = syncStatePresentation(source, status.generatedAt);
            return (
              <div key={source.sourceName}>
                <span>{sourceLabels[source.sourceName] ?? source.sourceName}</span>
                <strong className={`sync-state sync-state--${presentation.statusClass}`}>
                  {presentation.label}
                </strong>
              </div>
            );
          })}
        </div>
        <div className="audit-note"><CheckIcon /> Recolha e publicação são etapas separadas; índices recolhidos não equivalem a factos aprovados.</div>
      </div>
    </div>
  );
}
