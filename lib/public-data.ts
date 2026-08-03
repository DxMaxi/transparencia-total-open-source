import "server-only";

import { cache } from "react";
import { demoPolitician, demoPromises } from "@/lib/demo-data";
import { interestGraphDemo, speechVoteDemo } from "@/lib/v2-demo-data";
import type {
  GovernmentPromise,
  OfficialSource,
  PoliticianProfileData,
  PromiseStatus,
  VoteChoice,
} from "@/types/domain";
import type {
  PublicDataStatus,
  PublicInvestigatorDataset,
  PublicPersonSummary,
  SourceSyncState,
} from "@/types/public-data";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status?: number };

type RawSource = {
  publisher: string;
  label: string;
  url: string;
  retrieved_at?: string;
  content_sha256?: string | null;
};

type RawDataStatus = {
  mode: "LIVE" | "EMPTY" | "UNAVAILABLE";
  generated_at: string;
  database_configured: boolean;
  counts: {
    politicians: number;
    promises: number;
    contracts: number;
    relationships: number;
    news: number;
    citizen_alerts: number;
  };
  sources: Array<{
    source_name: string;
    status: SourceSyncState["status"];
    started_at?: string | null;
    finished_at?: string | null;
    records_read: number;
    records_written: number;
    warning_count: number;
    dataset_url?: string | null;
    code_version?: string | null;
  }>;
  message: string;
  publication_rule: string;
};

type RawPerson = {
  id: string;
  slug: string;
  name: string;
  role: string;
  party: string;
  party_short: string;
  constituency: string;
  legislature: string;
  portrait_url?: string | null;
  verified_at: string;
  profile_source: RawSource;
};

type RawProfile = RawPerson & {
  attendance_rate?: number | null;
  attendance_label: string;
  nominal_votes_available: boolean;
  nominal_vote_count: number;
  declaration_source: RawSource;
  votes: Array<{
    id: string;
    title: string;
    date?: string | null;
    choice: string;
    result: string;
    initiative_number: string;
    source: RawSource;
    is_nominal: boolean;
  }>;
};

type RawPromise = {
  id: string;
  title: string;
  area: string;
  status: string;
  progress: number;
  programme_page: string;
  programme_source: RawSource;
  rationale: string;
  last_reviewed_at: string;
  evidence: Array<{
    id: string;
    legal_reference: string;
    summary: string;
    source: RawSource;
    published_at?: string | null;
  }>;
};

type RawInvestigator = {
  nodes: Array<{
    id: string;
    label: string;
    subtitle: string;
    kind: "person" | "public" | "company" | "party" | "other";
    verified: true;
  }>;
  edges: Array<{
    id: string;
    source_id: string;
    target_id: string;
    label: string;
    period: string;
    review_state: "Revisto";
    source: RawSource;
    year?: number | null;
    party?: string | null;
    amount?: string | number | null;
    company?: string | null;
  }>;
  comparisons: Array<{
    id: string;
    subject: string;
    statement: { quote: string; speaker: string; stated_at?: string | null; source: RawSource };
    vote: { choice: string; initiative: string; voted_at?: string | null; source: RawSource };
    comparison: {
      outcome: "CONSISTENT" | "INCONSISTENT" | "INCONCLUSIVE";
      score?: string | number | null;
      comparable_pairs: number;
      total_statements: number;
      methodology_version: string;
      rationale: string;
    };
  }>;
};

export type LoadedData<T> = {
  data: T;
  status: PublicDataStatus;
  showingFallback: boolean;
};

async function apiFetch<T>(path: string): Promise<ApiResult<T>> {
  if (!apiBaseUrl) return { ok: false };
  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(4_000),
    });
    if (!response.ok) return { ok: false, status: response.status };
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return { ok: false };
  }
}

function formatDate(value?: string | null): string {
  if (!value) return "Data não indicada";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("pt-PT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Europe/Lisbon",
  }).format(date);
}

function formatRole(value: string): string {
  const labels: Record<string, string> = {
    DEPUTY: "Deputado/a à Assembleia da República",
    MINISTER: "Ministro/a",
    SECRETARY_OF_STATE: "Secretário/a de Estado",
    MAYOR: "Presidente de Câmara",
    OTHER_PUBLIC_OFFICE: "Titular de cargo público",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function toOfficialSource(source: RawSource): OfficialSource {
  return {
    label: source.label,
    url: source.url,
    publisher: source.publisher as OfficialSource["publisher"],
    retrievedAt: source.retrieved_at,
  };
}

function mapStatus(raw: RawDataStatus): PublicDataStatus {
  return {
    mode: raw.mode,
    generatedAt: raw.generated_at,
    databaseConfigured: raw.database_configured,
    counts: {
      politicians: raw.counts.politicians,
      promises: raw.counts.promises,
      contracts: raw.counts.contracts,
      relationships: raw.counts.relationships,
      news: raw.counts.news,
      citizenAlerts: raw.counts.citizen_alerts,
    },
    sources: raw.sources.map((source) => ({
      sourceName: source.source_name,
      status: source.status,
      startedAt: source.started_at ?? undefined,
      finishedAt: source.finished_at ?? undefined,
      recordsRead: source.records_read,
      recordsWritten: source.records_written,
      warningCount: source.warning_count,
      datasetUrl: source.dataset_url ?? undefined,
      codeVersion: source.code_version ?? undefined,
    })),
    message: raw.message,
    publicationRule: raw.publication_rule,
  };
}

function fallbackStatus(mode: "DEMO" | "UNAVAILABLE"): PublicDataStatus {
  const configured = Boolean(apiBaseUrl);
  return {
    mode,
    generatedAt: new Date().toISOString(),
    databaseConfigured: false,
    counts: {
      politicians: 0,
      promises: 0,
      contracts: 0,
      relationships: 0,
      news: 0,
      citizenAlerts: 0,
    },
    sources: [
      "PARLIAMENT_DEPUTIES",
      "PARLIAMENT_VOTES",
      "BASE_CONTRACTS",
      "DRE",
      "TRANSPARENCY_ENTITY",
      "LOCAL_SNS",
    ].map((sourceName) => ({
      sourceName,
      status: "NEVER",
      recordsRead: 0,
      recordsWritten: 0,
      warningCount: 0,
    })),
    message: configured
      ? "A API não respondeu; a interface não apresenta estes exemplos como factos reais."
      : "A URL da API ainda não está configurada; a interface encontra-se em demonstração.",
    publicationRule:
      "Amostras fictícias permanecem isoladas até existirem registos oficiais aprovados.",
  };
}

export const loadPublicDataStatus = cache(async (): Promise<PublicDataStatus> => {
  const result = await apiFetch<RawDataStatus>("/api/v1/public/data-status");
  if (result.ok) return mapStatus(result.data);
  return fallbackStatus(apiBaseUrl ? "UNAVAILABLE" : "DEMO");
});

function mapPerson(raw: RawPerson): PublicPersonSummary {
  return {
    id: raw.id,
    slug: raw.slug,
    name: raw.name,
    role: raw.role,
    party: raw.party,
    partyShort: raw.party_short,
    constituency: raw.constituency,
    legislature: raw.legislature,
    portraitUrl: raw.portrait_url ?? undefined,
    verifiedAt: formatDate(raw.verified_at),
    profileSource: toOfficialSource(raw.profile_source),
  };
}

export async function loadPublicPoliticians(): Promise<LoadedData<PublicPersonSummary[]>> {
  const [status, result] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawPerson[]>("/api/v1/public/politicians?limit=250"),
  ]);
  if (result.ok && result.data.length) {
    return { data: result.data.map(mapPerson), status, showingFallback: false };
  }
  const fallback: PublicPersonSummary = {
    id: demoPolitician.id,
    slug: demoPolitician.slug,
    name: demoPolitician.name,
    role: demoPolitician.role,
    party: demoPolitician.party,
    partyShort: demoPolitician.partyShort,
    constituency: demoPolitician.constituency,
    legislature: demoPolitician.legislature,
    verifiedAt: demoPolitician.verifiedAt,
    profileSource: demoPolitician.profileSource,
  };
  return { data: [fallback], status, showingFallback: true };
}

export async function loadPublicPolitician(
  slug: string,
): Promise<LoadedData<PoliticianProfileData | null>> {
  const [status, result] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawProfile>(`/api/v1/public/politicians/${encodeURIComponent(slug)}`),
  ]);
  if (result.ok) {
    const allowedChoices = new Set(["FAVOR", "AGAINST", "ABSTENTION", "ABSENT"]);
    return {
      status,
      showingFallback: false,
      data: {
        ...mapPerson(result.data),
        role: formatRole(result.data.role),
        attendanceRate: result.data.attendance_rate ?? undefined,
        attendanceLabel: result.data.attendance_label,
        nominalVotesAvailable: result.data.nominal_votes_available,
        nominalVoteCount: result.data.nominal_vote_count,
        declarationSource: toOfficialSource(result.data.declaration_source),
        votes: result.data.votes
          .filter((vote) => allowedChoices.has(vote.choice))
          .map((vote) => ({
            id: vote.id,
            title: vote.title,
            date: formatDate(vote.date),
            choice: vote.choice as VoteChoice,
            result: vote.result,
            initiativeNumber: vote.initiative_number,
            source: toOfficialSource(vote.source),
            isNominal: vote.is_nominal,
          })),
        isDemonstration: false,
      },
    };
  }
  if (slug === demoPolitician.slug) {
    return { data: demoPolitician, status, showingFallback: true };
  }
  return { data: null, status, showingFallback: false };
}

export async function loadPublicPromises(): Promise<LoadedData<GovernmentPromise[]>> {
  const [status, result] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawPromise[]>("/api/v1/public/promises?limit=1000"),
  ]);
  if (result.ok && result.data.length) {
    const allowedStatuses = new Set(["FULFILLED", "IN_PROGRESS", "BROKEN", "ABANDONED"]);
    return {
      status,
      showingFallback: false,
      data: result.data.filter((item) => allowedStatuses.has(item.status)).map((item) => ({
        id: item.id,
        title: item.title,
        area: item.area,
        status: item.status as PromiseStatus,
        progress: item.progress,
        programmePage: item.programme_page,
        programmeSource: toOfficialSource(item.programme_source),
        rationale: item.rationale,
        lastReviewedAt: formatDate(item.last_reviewed_at),
        evidence: item.evidence.map((evidence) => ({
          id: evidence.id,
          legalReference: evidence.legal_reference,
          summary: evidence.summary,
          source: toOfficialSource(evidence.source),
          publishedAt: evidence.published_at ? formatDate(evidence.published_at) : "Não indicada",
        })),
        isDemonstration: false,
      })),
    };
  }
  return { data: demoPromises, status, showingFallback: true };
}

export async function loadPublicInvestigator(): Promise<LoadedData<PublicInvestigatorDataset>> {
  const [status, result] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawInvestigator>("/api/v1/public/investigator?limit=300"),
  ]);
  if (result.ok && (result.data.edges.length || result.data.comparisons.length)) {
    return {
      status,
      showingFallback: false,
      data: {
        isDemonstration: false,
        nodes: result.data.nodes.map((node) => ({
          id: node.id,
          data: { ...node, isDemonstration: false },
        })),
        edges: result.data.edges.map((edge) => ({
          id: edge.id,
          source: edge.source_id,
          target: edge.target_id,
          label: edge.label,
          data: {
            label: edge.label,
            period: edge.period,
            reviewState: edge.review_state,
            source: {
              label: edge.source.label,
              url: edge.source.url,
              publisher: edge.source.publisher,
              sha256: edge.source.content_sha256 ?? "hash não disponibilizado",
            },
            year: edge.year ?? undefined,
            party: edge.party ?? undefined,
            amount: edge.amount == null ? undefined : Number(edge.amount),
            company: edge.company ?? undefined,
            isDemonstration: false,
          },
        })),
        comparisons: result.data.comparisons.map((item) => ({
          id: item.id,
          isDemonstration: false,
          subject: item.subject,
          statement: {
            quote: item.statement.quote,
            speaker: item.statement.speaker,
            date: formatDate(item.statement.stated_at),
            source: {
              label: item.statement.source.label,
              url: item.statement.source.url,
              publisher: item.statement.source.publisher,
              sha256: item.statement.source.content_sha256 ?? "hash não disponibilizado",
            },
          },
          vote: {
            choice: item.vote.choice,
            initiative: item.vote.initiative,
            date: formatDate(item.vote.voted_at),
            source: {
              label: item.vote.source.label,
              url: item.vote.source.url,
              publisher: item.vote.source.publisher,
              sha256: item.vote.source.content_sha256 ?? "hash não disponibilizado",
            },
          },
          comparison: {
            outcome: item.comparison.outcome,
            score: item.comparison.score == null ? null : Number(item.comparison.score),
            comparablePairs: item.comparison.comparable_pairs,
            totalStatements: item.comparison.total_statements,
            methodologyVersion: item.comparison.methodology_version,
            rationale: item.comparison.rationale,
          },
        })),
      },
    };
  }
  return {
    status,
    showingFallback: true,
    data: {
      ...interestGraphDemo,
      comparisons: [speechVoteDemo],
    },
  };
}
