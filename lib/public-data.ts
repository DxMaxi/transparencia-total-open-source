import "server-only";

import { cache } from "react";
import { initialGovernmentCommitments } from "@/lib/government-programme";
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
  PublicParliamentActivity,
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
    parliament_sessions: number;
    parliament_initiatives: number;
    parliament_votes: number;
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
    sha256: source.content_sha256 ?? undefined,
  };
}

type RawParliamentarySession = {
  id: string;
  source_id: string;
  legislature: string;
  session_number?: string | null;
  title: string;
  starts_at: string;
  ends_at?: string | null;
  verified_at: string;
  source: RawSource;
};

type RawParliamentaryInitiative = {
  id: string;
  source_id: string;
  legislature: string;
  number: string;
  initiative_type: string;
  title: string;
  description?: string | null;
  introduced_at?: string | null;
  status?: string | null;
  official_url: string;
  verified_at: string;
  source: RawSource;
};

type RawParliamentaryVote = {
  id: string;
  source_id: string;
  legislature: string;
  title: string;
  initiative_number?: string | null;
  voted_at?: string | null;
  result?: string | null;
  is_nominal: boolean;
  records: Array<{
    actor_label: string;
    actor_type: "PERSON" | "PARTY" | "UNKNOWN";
    choice: "FAVOR" | "AGAINST" | "ABSTENTION" | "ABSENT" | "UNKNOWN";
  }>;
  verified_at: string;
  source: RawSource;
};

type RawParliamentPublicationHistoryItem = {
  event_reference_sha256: string;
  action: "PUBLISHED" | "WITHDRAWN";
  scope: "activity" | "votes";
  scope_label: string;
  legislature: string;
  target_reference_sha256: string;
  decided_at: string;
  actor_alias: string;
  public_rationale: string;
  reason_category?: string | null;
  source: RawSource;
  snapshot_sha256: string;
  manifest_counts: {
    sessions: number;
    initiatives: number;
    votes: number;
    vote_records: number;
  };
  public_effect?: null | {
    kind: "DATA_UNAVAILABLE" | "FALLBACK_TO_PREVIOUS_SNAPSHOT";
    scope: "activity" | "votes";
    legislature: string;
    message: string;
    snapshot_reference_sha256?: string | null;
    snapshot_sha256?: string | null;
    source_sha256?: string | null;
  };
  public_effect_sha256?: string | null;
};

function mapStatus(raw: RawDataStatus): PublicDataStatus {
  return {
    mode: raw.mode,
    generatedAt: raw.generated_at,
    databaseConfigured: raw.database_configured,
    counts: {
      politicians: raw.counts.politicians,
      parliamentSessions: raw.counts.parliament_sessions,
      parliamentInitiatives: raw.counts.parliament_initiatives,
      parliamentVotes: raw.counts.parliament_votes,
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

function fallbackStatus(): PublicDataStatus {
  const configured = Boolean(apiBaseUrl);
  return {
    mode: "UNAVAILABLE",
    generatedAt: new Date().toISOString(),
    databaseConfigured: false,
    counts: {
      politicians: 0,
      parliamentSessions: 0,
      parliamentInitiatives: 0,
      parliamentVotes: 0,
      promises: 0,
      contracts: 0,
      relationships: 0,
      news: 0,
      citizenAlerts: 0,
    },
    sources: [
      "PARLIAMENT_DEPUTIES",
      "PARLIAMENT_ACTIVITY",
      "PARLIAMENT_VOTES",
      "BASE_CONTRACTS",
      "DRE",
      "TRANSPARENCY_ENTITY",
      "COURT_OF_AUDIT",
      "EUROPEAN_PARLIAMENT",
      "LOCAL_SNS",
    ].map((sourceName) => ({
      sourceName,
      status: "NEVER",
      recordsRead: 0,
      recordsWritten: 0,
      warningCount: 0,
    })),
    message: configured
      ? "A API não respondeu; os dados oficiais estão temporariamente indisponíveis."
      : "A URL da API não está configurada; os dados oficiais estão indisponíveis.",
    publicationRule:
      "A interface pública nunca substitui dados oficiais indisponíveis por amostras fictícias.",
  };
}

export const loadPublicDataStatus = cache(async (): Promise<PublicDataStatus> => {
  const result = await apiFetch<RawDataStatus>("/api/v1/public/data-status");
  if (result.ok) return mapStatus(result.data);
  return fallbackStatus();
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
    apiFetch<RawPerson[]>("/api/v1/public/politicians?limit=500"),
  ]);
  if (result.ok && result.data.length) {
    return { data: result.data.map(mapPerson), status, showingFallback: false };
  }
  return { data: [], status, showingFallback: false };
}

export async function loadPublicParliamentActivity(
  legislature = "XVII",
  pagination: {
    sessions?: { limit: number; offset: number };
    initiatives?: { limit: number; offset: number };
    votes?: { limit: number; offset: number };
  } = {},
): Promise<LoadedData<PublicParliamentActivity>> {
  const legislatureQuery = `legislature=${encodeURIComponent(legislature)}`;
  const sessionsPage = pagination.sessions ?? { limit: 24, offset: 0 };
  const initiativesPage = pagination.initiatives ?? { limit: 25, offset: 0 };
  const votesPage = pagination.votes ?? { limit: 20, offset: 0 };
  const [status, sessions, initiatives, votes, publicationHistory] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawParliamentarySession[]>(
      `/api/v1/public/parliament/sessions?${legislatureQuery}&limit=${sessionsPage.limit}&offset=${sessionsPage.offset}`,
    ),
    apiFetch<RawParliamentaryInitiative[]>(
      `/api/v1/public/parliament/initiatives?${legislatureQuery}&limit=${initiativesPage.limit}&offset=${initiativesPage.offset}`,
    ),
    apiFetch<RawParliamentaryVote[]>(
      `/api/v1/public/parliament/votes?${legislatureQuery}&limit=${votesPage.limit}&offset=${votesPage.offset}`,
    ),
    apiFetch<RawParliamentPublicationHistoryItem[]>(
      `/api/v1/public/parliament/publication-history?${legislatureQuery}&limit=20`,
    ),
  ]);
  return {
    status,
    showingFallback: false,
    data: {
      availability: {
        sessions: sessions.ok,
        initiatives: initiatives.ok,
        votes: votes.ok,
        publicationHistory: publicationHistory.ok,
      },
      sessions: sessions.ok
        ? sessions.data.map((item) => ({
            id: item.id,
            sourceId: item.source_id,
            legislature: item.legislature,
            sessionNumber: item.session_number ?? undefined,
            title: item.title,
            startsAt: formatDate(item.starts_at),
            endsAt: item.ends_at ? formatDate(item.ends_at) : undefined,
            verifiedAt: formatDate(item.verified_at),
            source: toOfficialSource(item.source),
          }))
        : [],
      initiatives: initiatives.ok
        ? initiatives.data.map((item) => ({
            id: item.id,
            sourceId: item.source_id,
            legislature: item.legislature,
            number: item.number,
            initiativeType: item.initiative_type,
            title: item.title,
            description: item.description ?? undefined,
            introducedAt: item.introduced_at ? formatDate(item.introduced_at) : undefined,
            status: item.status ?? undefined,
            officialUrl: item.official_url,
            verifiedAt: formatDate(item.verified_at),
            source: toOfficialSource(item.source),
          }))
        : [],
      votes: votes.ok
        ? votes.data.map((item) => ({
            id: item.id,
            sourceId: item.source_id,
            legislature: item.legislature,
            title: item.title,
            initiativeNumber: item.initiative_number ?? undefined,
            votedAt: item.voted_at ? formatDate(item.voted_at) : undefined,
            result: item.result ?? undefined,
            isNominal: item.is_nominal,
            records: item.records.map((record) => ({
              actorLabel: record.actor_label,
              actorType: record.actor_type,
              choice: record.choice,
            })),
            verifiedAt: formatDate(item.verified_at),
            source: toOfficialSource(item.source),
          }))
        : [],
      publicationHistory: publicationHistory.ok
        ? publicationHistory.data.map((item) => ({
            eventReferenceSha256: item.event_reference_sha256,
            action: item.action,
            scope: item.scope,
            scopeLabel: item.scope_label,
            legislature: item.legislature,
            targetReferenceSha256: item.target_reference_sha256,
            decidedAt: formatDate(item.decided_at),
            actorAlias: item.actor_alias,
            publicRationale: item.public_rationale,
            reasonCategory: item.reason_category ?? undefined,
            source: toOfficialSource(item.source),
            snapshotSha256: item.snapshot_sha256,
            manifestCounts: {
              sessions: item.manifest_counts.sessions,
              initiatives: item.manifest_counts.initiatives,
              votes: item.manifest_counts.votes,
              voteRecords: item.manifest_counts.vote_records,
            },
            publicEffect: item.public_effect
              ? {
                  kind: item.public_effect.kind,
                  scope: item.public_effect.scope,
                  legislature: item.public_effect.legislature,
                  message: item.public_effect.message,
                  snapshotReferenceSha256:
                    item.public_effect.snapshot_reference_sha256 ?? undefined,
                  snapshotSha256: item.public_effect.snapshot_sha256 ?? undefined,
                  sourceSha256: item.public_effect.source_sha256 ?? undefined,
                }
              : undefined,
            publicEffectSha256: item.public_effect_sha256 ?? undefined,
          }))
        : [],
    },
  };
}

export async function loadPublicPolitician(
  slug: string,
): Promise<LoadedData<PoliticianProfileData | null>> {
  const [status, result, parliamentaryVotes] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawProfile>(`/api/v1/public/politicians/${encodeURIComponent(slug)}`),
    apiFetch<RawParliamentaryVote[]>(
      "/api/v1/public/parliament/votes?legislature=XVII&limit=200",
    ),
  ]);
  if (result.ok) {
    const allowedChoices = new Set(["FAVOR", "AGAINST", "ABSTENTION", "ABSENT"]);
    const partyKey = result.data.party_short.replace(/[^a-z0-9]/gi, "").toLowerCase();
    const groupPositions = parliamentaryVotes.ok
      ? parliamentaryVotes.data.flatMap((vote) => {
          const record = vote.records.find(
            (item) =>
              item.actor_type !== "PERSON" &&
              item.actor_label.replace(/[^a-z0-9]/gi, "").toLowerCase() === partyKey &&
              allowedChoices.has(item.choice),
          );
          if (!record) return [];
          return [{
            id: `group-${vote.id}`,
            title: vote.title,
            date: formatDate(vote.voted_at),
            choice: record.choice as VoteChoice,
            result: vote.result ?? "Resultado não indicado na fonte",
            initiativeNumber: vote.initiative_number ?? "Sem número indicado",
            source: toOfficialSource(vote.source),
            isNominal: false,
          }];
        }).slice(0, 30)
      : [];
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
          .filter((vote) => vote.is_nominal && allowedChoices.has(vote.choice))
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
        groupPositions,
      },
    };
  }
  return { data: null, status, showingFallback: false };
}

export async function loadPublicPromises(): Promise<LoadedData<GovernmentPromise[]>> {
  const [status, result] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawPromise[]>("/api/v1/public/promises?limit=1000"),
  ]);
  if (result.ok && result.data.length) {
    const allowedStatuses = new Set([
      "UNVERIFIED",
      "FULFILLED",
      "IN_PROGRESS",
      "BROKEN",
      "ABANDONED",
    ]);
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
      })),
    };
  }
  return { data: initialGovernmentCommitments, status, showingFallback: false };
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
        nodes: result.data.nodes.map((node) => ({
          id: node.id,
          data: node,
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
          },
        })),
        comparisons: result.data.comparisons.map((item) => ({
          id: item.id,
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
    showingFallback: false,
    data: { nodes: [], edges: [], comparisons: [] },
  };
}
