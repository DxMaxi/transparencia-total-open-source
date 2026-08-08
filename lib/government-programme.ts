import type { GovernmentPromise, OfficialSource } from "@/types/domain";
import catalogue from "@/data/xxv-government-programme.json";

export const XXV_GOVERNMENT_PROGRAMME_URL =
  catalogue.sourceUrl;

export const XXV_GOVERNMENT_PROGRAMME_SHA256 =
  catalogue.sourceSha256;

const programmeSource: OfficialSource = {
  label: "Programa do XXV Governo Constitucional",
  url: XXV_GOVERNMENT_PROGRAMME_URL,
  publisher: "OFICIAL",
  retrievedAt: catalogue.retrievedAt,
  sha256: XXV_GOVERNMENT_PROGRAMME_SHA256,
};

function commitment(item: (typeof catalogue.commitments)[number]): GovernmentPromise {
  return {
    id: item.stableKey,
    title: item.title,
    area: item.area,
    status: "UNVERIFIED",
    progress: 0,
    programmePage: item.programmePage,
    programmeSource,
    rationale:
      "Compromisso localizado no programa oficial. O estado de execução ainda não foi avaliado porque não existe prova oficial de implementação associada.",
    lastReviewedAt: "08 ago 2026",
    evidence: [],
  };
}

/**
 * Cobertura editorial inicial das medidas prioritárias do Programa do XXV Governo.
 * O catálogo prova que o compromisso existe; não prova execução. Novas avaliações
 * só substituem UNVERIFIED quando têm evidência oficial e revisão humana.
 */
export const initialGovernmentCommitments: GovernmentPromise[] = [
  ...catalogue.commitments.map(commitment),
];
