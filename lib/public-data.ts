import "server-only";

import { cache } from "react";
import { initialGovernmentCommitments } from "@/lib/government-programme";
import {
  classifyPublicApiError,
  publicApiEndpointLabel,
  PUBLIC_API_REVALIDATE_SECONDS,
  PUBLIC_API_TIMEOUT_MS,
  type PublicApiFailureReason,
} from "@/lib/public-api-policy";
import type {
  AttendanceSummary,
  GovernmentPromise,
  OfficialLookup,
  OfficialSource,
  PoliticianProfileData,
  PoliticianProfileCoverage,
  ProfileCoverageArea,
  PromiseStatus,
  VoteChoice,
} from "@/types/domain";
import type {
  PublicDataStatus,
  PublicGlobalSearch,
  PublicAiExplanation,
  PublicAiExplanationList,
  PublicAiPublicationHistoryItem,
  PublicInvestigatorDataset,
  PublicParliamentActivity,
  PublicParliamentExplorer,
  PublicParliamentPublicationHistoryItem,
  PublicParliamentaryInitiative,
  PublicParliamentarySession,
  PublicParliamentaryVote,
  PublicPoliticianDirectory,
  PublicPersonSummary,
  SourceSyncState,
} from "@/types/public-data";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";
type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; reason: PublicApiFailureReason; status?: number };

type RawSource = {
  publisher: string;
  label: string;
  url: string;
  retrieved_at?: string;
  content_sha256?: string | null;
};

type RawGlobalSearch = {
  query: string;
  legislature: string;
  section_limit: number;
  total_results: number;
  available_sections: number;
  unavailable_sections: number;
  sections: Array<{
    kind:
      | "politicians"
      | "parliament_sessions"
      | "parliament_initiatives"
      | "parliament_votes"
      | "promises"
      | "ai_explanations";
    label: string;
    availability: "AVAILABLE" | "UNAVAILABLE";
    total?: number | null;
    total_is_exact: boolean;
    items: Array<{
      id: string;
      kind:
        | "politicians"
        | "parliament_sessions"
        | "parliament_initiatives"
        | "parliament_votes"
        | "promises"
        | "ai_explanations";
      title: string;
      description: string;
      href: string;
      source: RawSource;
      verified_at: string;
      observed_at?: string | null;
      coverage_state: "AVAILABLE";
      coverage_note: string;
    }>;
    view_all_href: string;
    coverage_note: string;
  }>;
  publication_rule: string;
  search_rule: string;
};

type RawAiExplanation = {
  id: string;
  content_kind: "AI_EXPLANATION";
  label: "Explicação gerada por IA — revista por humano";
  ai_generated: true;
  ai_is_source: false;
  human_review_required: true;
  not_prediction: true;
  no_voting_recommendation: true;
  abstained: boolean;
  summary: {
    title: string;
    summary_2_minutes: string;
    what_changes: string[];
    who_is_affected: string[];
    dates_and_deadlines: string[];
    duties_and_rights: string[];
    uncertainties: string[];
    glossary: Array<{ term: string; explanation: string }>;
    source_anchors: Array<{ section: string; reason: string }>;
  };
  source: {
    publisher: "DRE";
    label: string;
    title: string;
    official_identifier?: string | null;
    url: string;
    retrieved_at: string;
    published_at?: string | null;
    content_sha256: string;
    normalised_text_sha256: string;
  };
  generation: {
    provider: string;
    model: string;
    prompt_version: string;
    prompt_sha256: string;
    input_sha256: string;
    output_sha256: string;
    generated_at: string;
    source_characters: number;
    processed_characters: number;
    source_truncated: boolean;
    provider_store: false;
  };
  editorial: {
    human_reviewed: true;
    reviewed_by: string;
    published_at: string;
    editorial_version_sha256: string;
    publication_proof_sha256: string;
    publication_event_reference_sha256: string;
  };
  limitations: string[];
};

type RawAiExplanationList = {
  items: RawAiExplanation[];
  total: number;
  limit: number;
  offset: number;
  query?: string | null;
  total_is_exact: true;
  publication_rule: string;
};

type RawAiPublicationHistoryItem = {
  event_reference_sha256: string;
  action: "PUBLISHED" | "WITHDRAWN";
  public_id: string;
  title: string;
  decided_at: string;
  actor_alias: string;
  public_rationale: string;
  reason_category?: string | null;
  source: RawAiExplanation["source"];
  editorial_version_sha256: string;
  publication_proof_sha256: string;
  public_effect?: null | {
    kind: "DATA_UNAVAILABLE";
    public_id: string;
    message: string;
  };
  public_effect_sha256?: string | null;
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
  observed_at?: string | null;
  verified_at: string;
  profile_source: RawSource;
};

type RawPoliticianDirectory = {
  items: RawPerson[];
  total: number;
  limit: number;
  next_cursor?: string | null;
  query?: string | null;
  party_short?: string | null;
  parties: Array<{
    value: string;
    label: string;
    count: number;
  }>;
  total_is_exact: true;
  pagination: "CURSOR";
  search_rule: string;
};

type RawCoverageArea = {
  state: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE";
  record_count: number;
  note: string;
  observed_from?: string | null;
  observed_through?: string | null;
  source?: RawSource | null;
};

type RawProfile = RawPerson & {
  contract_version?: "v5.6";
  membership_observations?: Array<{
    id: string;
    legislature: string;
    parliamentary_name: string;
    party: string;
    party_short: string;
    constituency: string;
    observed_at: string;
    verified_at: string;
    source: RawSource;
  }>;
  mandates?: Array<{
    id: string;
    office_title: string;
    legislature?: string | null;
    party?: string | null;
    party_short?: string | null;
    constituency?: string | null;
    started_at: string;
    ended_at?: string | null;
    verified_at: string;
    source: RawSource;
  }>;
  attendance?: {
    available: boolean;
    record_count: number;
    present_count: number;
    absent_count: number;
    excused_count: number;
    attendance_rate?: number | null;
    observed_from?: string | null;
    observed_through?: string | null;
    note: string;
    source?: RawSource | null;
  };
  attendance_rate?: number | null;
  attendance_label: string;
  nominal_votes_available: boolean;
  nominal_vote_count: number;
  initiatives?: Array<{
    id: string;
    number: string;
    initiative_type: string;
    title: string;
    status?: string | null;
    introduced_at?: string | null;
    relation: "AUTHOR" | "COAUTHOR" | "PROPOSER";
    source: RawSource;
  }>;
  declarations?: Array<{
    id: string;
    declaration_type: string;
    declared_at?: string | null;
    period_label?: string | null;
    public_access_status: string;
    verified_at: string;
    source: RawSource;
  }>;
  declaration?: {
    id: string;
    declaration_type: string;
    declared_at?: string | null;
    period_label?: string | null;
    public_access_status: string;
    verified_at: string;
    source: RawSource;
  } | null;
  declaration_source?: RawSource | null;
  declaration_lookup_source?: {
    publisher: string;
    label: string;
    url: string;
    note: string;
  };
  coverage?: {
    identity: RawCoverageArea;
    membership_observations: RawCoverageArea;
    mandates: RawCoverageArea;
    attendance: RawCoverageArea;
    initiatives: RawCoverageArea;
    nominal_votes: RawCoverageArea;
    declarations: RawCoverageArea;
    matching_rule: string;
  };
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

let missingApiConfigurationReported = false;

function reportPublicApiFailure(
  path: string,
  reason: PublicApiFailureReason,
  startedAt: number,
  status?: number,
): void {
  console.warn("public_api_fetch_failed", {
    endpoint: publicApiEndpointLabel(path),
    reason,
    status: status ?? null,
    elapsed_ms: Math.max(0, Date.now() - startedAt),
    timeout_ms: PUBLIC_API_TIMEOUT_MS,
    retry_policy: "none",
  });
}

async function apiFetch<T>(path: string): Promise<ApiResult<T>> {
  const startedAt = Date.now();
  if (!apiBaseUrl) {
    if (!missingApiConfigurationReported) {
      reportPublicApiFailure(path, "not_configured", startedAt);
      missingApiConfigurationReported = true;
    }
    return { ok: false, reason: "not_configured" };
  }

  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      headers: { Accept: "application/json" },
      next: { revalidate: PUBLIC_API_REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(PUBLIC_API_TIMEOUT_MS),
    });
    if (!response.ok) {
      reportPublicApiFailure(path, "http", startedAt, response.status);
      return { ok: false, reason: "http", status: response.status };
    }

    try {
      return { ok: true, data: (await response.json()) as T };
    } catch (error) {
      const reason = classifyPublicApiError(error);
      reportPublicApiFailure(path, reason, startedAt, response.status);
      return { ok: false, reason, status: response.status };
    }
  } catch (error) {
    const reason = classifyPublicApiError(error);
    reportPublicApiFailure(path, reason, startedAt);
    return { ok: false, reason };
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

const globalSearchKinds = new Set([
  "politicians",
  "parliament_sessions",
  "parliament_initiatives",
  "parliament_votes",
  "promises",
  "ai_explanations",
]);

function isValidRawGlobalSearch(value: unknown): value is RawGlobalSearch {
  if (!value || typeof value !== "object") return false;
  const candidate = value as RawGlobalSearch;
  if (
    typeof candidate.query !== "string"
    || candidate.query.length < 2
    || typeof candidate.legislature !== "string"
    || !Number.isSafeInteger(candidate.section_limit)
    || candidate.section_limit < 1
    || candidate.section_limit > 20
    || !Number.isSafeInteger(candidate.total_results)
    || candidate.total_results < 0
    || !Number.isSafeInteger(candidate.available_sections)
    || candidate.available_sections < 1
    || !Number.isSafeInteger(candidate.unavailable_sections)
    || !Array.isArray(candidate.sections)
    || candidate.sections.length !== globalSearchKinds.size
    || typeof candidate.publication_rule !== "string"
    || typeof candidate.search_rule !== "string"
  ) {
    return false;
  }
  if (!candidate.sections.every((section) => section && typeof section === "object")) {
    return false;
  }
  const kinds = new Set(candidate.sections.map((section) => section.kind));
  if (kinds.size !== globalSearchKinds.size) return false;
  const sectionsAreValid = candidate.sections.every((section) => {
    if (
      !globalSearchKinds.has(section.kind)
      || !["AVAILABLE", "UNAVAILABLE"].includes(section.availability)
      || typeof section.label !== "string"
      || typeof section.coverage_note !== "string"
      || typeof section.view_all_href !== "string"
      || !section.view_all_href.startsWith("/")
      || !Array.isArray(section.items)
    ) {
      return false;
    }
    if (
      section.availability === "AVAILABLE"
      && (
        !Number.isSafeInteger(section.total)
        || (section.total ?? -1) < 0
        || section.total_is_exact !== true
        || section.items.length > candidate.section_limit
      )
    ) {
      return false;
    }
    if (
      section.availability === "UNAVAILABLE"
      && (section.total != null || section.total_is_exact || section.items.length)
    ) {
      return false;
    }
    return section.items.every((item) => (
      Boolean(item)
      && typeof item === "object"
      && item.kind === section.kind
      && typeof item.id === "string"
      && typeof item.title === "string"
      && typeof item.description === "string"
      && typeof item.href === "string"
      && item.href.startsWith("/")
      && typeof item.verified_at === "string"
      && item.coverage_state === "AVAILABLE"
      && typeof item.coverage_note === "string"
      && Boolean(item.source)
      && typeof item.source.url === "string"
      && typeof item.source.retrieved_at === "string"
      && typeof item.source.content_sha256 === "string"
      && /^[0-9a-f]{64}$/.test(item.source.content_sha256)
    ));
  });
  if (!sectionsAreValid) return false;
  const available = candidate.sections.filter(
    (section) => section.availability === "AVAILABLE",
  );
  return (
    candidate.available_sections === available.length
    && candidate.unavailable_sections === candidate.sections.length - available.length
    && candidate.total_results === available.reduce(
      (total, section) => total + (section.total ?? 0),
      0,
    )
  );
}

export async function loadPublicGlobalSearch(
  rawQuery: string,
  legislature = "XVII",
): Promise<PublicGlobalSearch> {
  const queryText = rawQuery.trim().slice(0, 120);
  const parameters = new URLSearchParams({
    q: queryText,
    legislature,
    section_limit: "5",
  });
  const result = await apiFetch<RawGlobalSearch>(
    `/api/v1/public/search?${parameters.toString()}`,
  );
  if (result.ok && isValidRawGlobalSearch(result.data)) {
    return {
      query: result.data.query,
      legislature: result.data.legislature,
      sectionLimit: result.data.section_limit,
      totalResults: result.data.total_results,
      availableSections: result.data.available_sections,
      unavailableSections: result.data.unavailable_sections,
      sections: result.data.sections.map((section) => ({
        kind: section.kind,
        label: section.label,
        availability: section.availability,
        total: section.total ?? undefined,
        totalIsExact: section.total_is_exact,
        items: section.items.map((item) => ({
          id: item.id,
          kind: item.kind,
          title: item.title,
          description: item.description,
          href: item.href,
          source: toOfficialSource(item.source),
          verifiedAt: item.verified_at,
          observedAt: item.observed_at ?? undefined,
          coverageState: item.coverage_state,
          coverageNote: item.coverage_note,
        })),
        viewAllHref: section.view_all_href,
        coverageNote: section.coverage_note,
      })),
      publicationRule: result.data.publication_rule,
      searchRule: result.data.search_rule,
      available: true,
    };
  }

  return {
    query: queryText,
    legislature,
    sectionLimit: 5,
    totalResults: 0,
    availableSections: 0,
    unavailableSections: 6,
    sections: [],
    publicationRule: (
      "A consulta não substitui projeções publicadas por listas antigas, exemplos locais ou "
      + "conteúdo por rever."
    ),
    searchRule: "Pesquisar nunca cria associações, conclusões ou conteúdo de IA.",
    available: false,
  };
}

function mapCoverageArea(area: RawCoverageArea): ProfileCoverageArea {
  return {
    state: area.state,
    recordCount: area.record_count,
    note: area.note,
    observedFrom: area.observed_from ? formatDate(area.observed_from) : undefined,
    observedThrough: area.observed_through ? formatDate(area.observed_through) : undefined,
    source: area.source ? toOfficialSource(area.source) : undefined,
  };
}

function unavailableCoverage(note: string): ProfileCoverageArea {
  return { state: "UNAVAILABLE", recordCount: 0, note };
}

function legacyProfileCoverage(
  raw: RawProfile,
  profileSource: OfficialSource,
): PoliticianProfileCoverage {
  const attendanceState = raw.attendance_rate == null ? "UNAVAILABLE" : "PARTIAL";
  const voteState = raw.nominal_vote_count > 0 ? "PARTIAL" : "UNAVAILABLE";
  return {
    identity: {
      state: "AVAILABLE",
      recordCount: 1,
      note: "Identidade publicada no contrato anterior da API.",
      observedFrom: formatDate(raw.observed_at ?? raw.verified_at),
      observedThrough: formatDate(raw.observed_at ?? raw.verified_at),
      source: profileSource,
    },
    membershipObservations: {
      state: "PARTIAL",
      recordCount: 1,
      note: (
        "A API anterior expõe apenas a observação mais recente; não a transforma numa data "
        + "de início de mandato."
      ),
      observedFrom: formatDate(raw.observed_at ?? raw.verified_at),
      observedThrough: formatDate(raw.observed_at ?? raw.verified_at),
      source: profileSource,
    },
    mandates: unavailableCoverage(
      "A API em produção ainda não expõe períodos de mandato revistos individualmente.",
    ),
    attendance: {
      state: attendanceState,
      recordCount: 0,
      note: raw.attendance_label,
    },
    initiatives: unavailableCoverage(
      "Não existe associação individual por identificador oficial neste contrato da API.",
    ),
    nominalVotes: {
      state: voteState,
      recordCount: raw.nominal_vote_count,
      note: raw.nominal_vote_count > 0
        ? "Votos nominais publicados pela API anterior; cobertura temporal não exposta."
        : "A API anterior não devolveu votos individuais publicáveis.",
    },
    declarations: unavailableCoverage(
      "Uma ligação geral ao portal institucional não prova uma declaração individual.",
    ),
    matchingRule: (
      "Associações individuais exigem um identificador oficial inequívoco. Nomes, siglas "
      + "ou posições coletivas nunca são convertidos em atividade pessoal."
    ),
  };
}

function mapParliamentSession(item: RawParliamentarySession): PublicParliamentarySession {
  return {
    id: item.id,
    sourceId: item.source_id,
    legislature: item.legislature,
    sessionNumber: item.session_number ?? undefined,
    title: item.title,
    startsAt: formatDate(item.starts_at),
    endsAt: item.ends_at ? formatDate(item.ends_at) : undefined,
    verifiedAt: formatDate(item.verified_at),
    source: toOfficialSource(item.source),
  };
}

function mapParliamentInitiative(
  item: RawParliamentaryInitiative,
): PublicParliamentaryInitiative {
  return {
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
  };
}

function mapParliamentVote(item: RawParliamentaryVote): PublicParliamentaryVote {
  return {
    id: item.id,
    sourceId: item.source_id,
    legislature: item.legislature,
    title: item.title,
    initiativeNumber: item.initiative_number ?? undefined,
    votedAt: item.voted_at ? formatDate(item.voted_at) : undefined,
    result: item.result ?? undefined,
    isNominal: item.is_nominal,
    initiativeType: item.initiative_type ?? undefined,
    initiativeTitle: item.initiative_title ?? undefined,
    initiativeStatus: item.initiative_status ?? undefined,
    initiativeOfficialUrl: item.initiative_official_url ?? undefined,
    records: item.records.map((record) => ({
      actorLabel: record.actor_label,
      actorType: record.actor_type,
      choice: record.choice,
      personSourceId: record.person_source_id ?? undefined,
      partySourceId: record.party_source_id ?? undefined,
    })),
    verifiedAt: formatDate(item.verified_at),
    source: toOfficialSource(item.source),
  };
}

function mapParliamentPublicationHistory(
  item: RawParliamentPublicationHistoryItem,
): PublicParliamentPublicationHistoryItem {
  return {
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
  initiative_type?: string | null;
  initiative_title?: string | null;
  initiative_status?: string | null;
  initiative_official_url?: string | null;
  records: Array<{
    actor_label: string;
    actor_type: "PERSON" | "PARTY" | "UNKNOWN";
    choice: "FAVOR" | "AGAINST" | "ABSTENTION" | "ABSENT" | "UNKNOWN";
    person_source_id?: string | null;
    party_source_id?: string | null;
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

type RawParliamentFacetOption = {
  value: string;
  label: string;
  count: number;
};

type RawParliamentExplorer = {
  kind: "sessions" | "initiatives" | "votes";
  legislature: string;
  query?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  sessions: RawParliamentarySession[];
  initiatives: RawParliamentaryInitiative[];
  votes: RawParliamentaryVote[];
  total: number;
  limit: number;
  offset: number;
  facets: {
    legislatures: string[];
    initiative_types: RawParliamentFacetOption[];
    initiative_statuses: RawParliamentFacetOption[];
    vote_results: RawParliamentFacetOption[];
    parties: RawParliamentFacetOption[];
    topics_available: false;
    topics_note: string;
  };
  explanation_rule: string;
};

function mapAiSource(
  source: RawAiExplanation["source"],
): PublicAiExplanation["source"] {
  return {
    publisher: source.publisher,
    label: source.label,
    title: source.title,
    officialIdentifier: source.official_identifier ?? undefined,
    url: source.url,
    retrievedAt: source.retrieved_at,
    publishedAt: source.published_at ?? undefined,
    contentSha256: source.content_sha256,
    normalisedTextSha256: source.normalised_text_sha256,
  };
}

function mapAiExplanation(item: RawAiExplanation): PublicAiExplanation {
  return {
    id: item.id,
    contentKind: item.content_kind,
    label: item.label,
    aiGenerated: item.ai_generated,
    aiIsSource: item.ai_is_source,
    humanReviewRequired: item.human_review_required,
    notPrediction: item.not_prediction,
    noVotingRecommendation: item.no_voting_recommendation,
    abstained: item.abstained,
    summary: {
      title: item.summary.title,
      summary2Minutes: item.summary.summary_2_minutes,
      whatChanges: item.summary.what_changes,
      whoIsAffected: item.summary.who_is_affected,
      datesAndDeadlines: item.summary.dates_and_deadlines,
      dutiesAndRights: item.summary.duties_and_rights,
      uncertainties: item.summary.uncertainties,
      glossary: item.summary.glossary,
      sourceAnchors: item.summary.source_anchors,
    },
    source: mapAiSource(item.source),
    generation: {
      provider: item.generation.provider,
      model: item.generation.model,
      promptVersion: item.generation.prompt_version,
      promptSha256: item.generation.prompt_sha256,
      inputSha256: item.generation.input_sha256,
      outputSha256: item.generation.output_sha256,
      generatedAt: item.generation.generated_at,
      sourceCharacters: item.generation.source_characters,
      processedCharacters: item.generation.processed_characters,
      sourceTruncated: item.generation.source_truncated,
      providerStore: item.generation.provider_store,
    },
    editorial: {
      humanReviewed: item.editorial.human_reviewed,
      reviewedBy: item.editorial.reviewed_by,
      publishedAt: item.editorial.published_at,
      editorialVersionSha256: item.editorial.editorial_version_sha256,
      publicationProofSha256: item.editorial.publication_proof_sha256,
      publicationEventReferenceSha256:
        item.editorial.publication_event_reference_sha256,
    },
    limitations: item.limitations,
  };
}

function mapAiPublicationHistory(
  item: RawAiPublicationHistoryItem,
): PublicAiPublicationHistoryItem {
  return {
    eventReferenceSha256: item.event_reference_sha256,
    action: item.action,
    publicId: item.public_id,
    title: item.title,
    decidedAt: item.decided_at,
    actorAlias: item.actor_alias,
    publicRationale: item.public_rationale,
    reasonCategory: item.reason_category ?? undefined,
    source: mapAiSource(item.source),
    editorialVersionSha256: item.editorial_version_sha256,
    publicationProofSha256: item.publication_proof_sha256,
    publicEffect: item.public_effect
      ? {
          kind: item.public_effect.kind,
          publicId: item.public_effect.public_id,
          message: item.public_effect.message,
        }
      : undefined,
    publicEffectSha256: item.public_effect_sha256 ?? undefined,
  };
}

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

export type PublicAiExplanationFilters = {
  query?: string;
  page?: number;
  pageSize?: number;
};

export type LoadedPublicAiExplanations = {
  data: PublicAiExplanationList;
  history: PublicAiPublicationHistoryItem[];
};

export async function loadPublicAiExplanations(
  filters: PublicAiExplanationFilters = {},
): Promise<LoadedPublicAiExplanations> {
  const limit = Math.min(100, Math.max(1, filters.pageSize ?? 12));
  const page = Math.min(500, Math.max(1, filters.page ?? 1));
  const offset = (page - 1) * limit;
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (filters.query?.trim()) query.set("q", filters.query.trim().slice(0, 120));
  const [listing, history] = await Promise.all([
    apiFetch<RawAiExplanationList>(`/api/v1/public/ai-explanations?${query.toString()}`),
    apiFetch<RawAiPublicationHistoryItem[]>(
      "/api/v1/public/ai-explanations/publication-history?limit=30",
    ),
  ]);

  if (
    listing.ok
    && Array.isArray(listing.data.items)
    && Number.isSafeInteger(listing.data.total)
    && listing.data.total >= 0
    && listing.data.total_is_exact === true
  ) {
    return {
      data: {
        items: listing.data.items.map(mapAiExplanation),
        total: listing.data.total,
        limit: listing.data.limit,
        offset: listing.data.offset,
        query: listing.data.query ?? undefined,
        totalIsExact: true,
        publicationRule: listing.data.publication_rule,
        available: true,
      },
      history: history.ok && Array.isArray(history.data)
        ? history.data.map(mapAiPublicationHistory)
        : [],
    };
  }

  return {
    data: {
      items: [],
      total: 0,
      limit,
      offset,
      query: filters.query,
      totalIsExact: true,
      publicationRule: (
        "A consulta não substitui explicações oficiais revistas por amostras, notícias ou "
        +
        "conteúdo gerado localmente."
      ),
      available: false,
    },
    history: history.ok && Array.isArray(history.data)
      ? history.data.map(mapAiPublicationHistory)
      : [],
  };
}

export async function loadPublicAiExplanation(
  publicId: string,
): Promise<{ data: PublicAiExplanation | null; available: boolean }> {
  if (!/^dre-[0-9a-f]{64}$/.test(publicId)) return { data: null, available: true };
  const result = await apiFetch<RawAiExplanation>(
    `/api/v1/public/ai-explanations/${encodeURIComponent(publicId)}`,
  );
  if (result.ok) return { data: mapAiExplanation(result.data), available: true };
  return { data: null, available: result.status === 404 };
}

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
    observedAt: formatDate(raw.observed_at ?? raw.verified_at),
    verifiedAt: formatDate(raw.verified_at),
    profileSource: toOfficialSource(raw.profile_source),
  };
}

const POLITICIAN_DIRECTORY_PAGE_SIZE = 24;
const LEGACY_POLITICIAN_LIMIT = 500;

function normaliseDirectorySearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-PT");
}

function filterLegacyPoliticians(
  people: PublicPersonSummary[],
  query?: string,
  partyShort?: string,
): PublicPersonSummary[] {
  const needle = normaliseDirectorySearch(query?.trim() ?? "");
  return people.filter((person) => {
    const matchesParty = !partyShort || person.partyShort === partyShort;
    const haystack = normaliseDirectorySearch(
      `${person.name} ${person.party} ${person.partyShort} ${person.constituency} ${person.legislature}`,
    );
    return matchesParty && (!needle || haystack.includes(needle));
  });
}

function legacyPartyFacets(
  people: PublicPersonSummary[],
  query?: string,
): PublicPoliticianDirectory["parties"] {
  const queryMatches = filterLegacyPoliticians(people, query);
  const counts = new Map<string, { label: string; count: number }>();
  queryMatches.forEach((person) => {
    const current = counts.get(person.partyShort);
    counts.set(person.partyShort, {
      label: current?.label ?? person.party,
      count: (current?.count ?? 0) + 1,
    });
  });
  return [...counts.entries()]
    .map(([value, item]) => ({ value, label: item.label, count: item.count }))
    .sort((left, right) => left.value.localeCompare(right.value, "pt-PT"));
}

export type PublicPoliticianDirectoryFilters = {
  query?: string;
  partyShort?: string;
  cursor?: string;
  page?: number;
  pageSize?: number;
};

function politicianDirectoryPath(filters: PublicPoliticianDirectoryFilters): string {
  const query = new URLSearchParams();
  if (filters.query) query.set("q", filters.query);
  if (filters.partyShort) query.set("party_short", filters.partyShort);
  if (filters.cursor) query.set("cursor", filters.cursor);
  query.set("limit", String(filters.pageSize ?? POLITICIAN_DIRECTORY_PAGE_SIZE));
  return `/api/v1/public/politicians/explore?${query.toString()}`;
}

export async function loadPublicPoliticianDirectory(
  filters: PublicPoliticianDirectoryFilters = {},
): Promise<LoadedData<PublicPoliticianDirectory>> {
  const limit = Math.min(100, Math.max(1, filters.pageSize ?? POLITICIAN_DIRECTORY_PAGE_SIZE));
  const requestedPage = Math.min(500, Math.max(1, filters.page ?? 1));
  const normalizedFilters = { ...filters, pageSize: limit };
  const [status, current] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawPoliticianDirectory>(politicianDirectoryPath(normalizedFilters)),
  ]);

  if (
    current.ok
    && Array.isArray(current.data.items)
    && Array.isArray(current.data.parties)
    && Number.isSafeInteger(current.data.total)
    && current.data.total >= 0
    && Number.isSafeInteger(current.data.limit)
    && current.data.limit >= 1
    && current.data.limit <= 100
    && current.data.total_is_exact === true
    && current.data.pagination === "CURSOR"
  ) {
    return {
      status,
      showingFallback: false,
      data: {
        people: current.data.items.map(mapPerson),
        total: current.data.total,
        totalIsExact: true,
        limit: current.data.limit,
        nextCursor: current.data.next_cursor ?? undefined,
        query: current.data.query ?? undefined,
        partyShort: current.data.party_short ?? undefined,
        parties: current.data.parties,
        paginationMode: "CURSOR",
        compatibilityMode: "CURRENT",
        currentPage: 1,
        hasNext: Boolean(current.data.next_cursor),
        hasPrevious: Boolean(filters.cursor),
        cursorRejected: false,
        searchRule: current.data.search_rule
          || "A pesquisa limita apenas identidades publicadas e nunca cria correspondências.",
      },
    };
  }

  if (!current.ok && current.status === 422 && filters.cursor) {
    return {
      status,
      showingFallback: false,
      data: {
        people: [],
        total: 0,
        totalIsExact: false,
        limit,
        query: filters.query,
        partyShort: filters.partyShort,
        parties: [],
        paginationMode: "CURSOR",
        compatibilityMode: "UNAVAILABLE",
        currentPage: 1,
        hasNext: false,
        hasPrevious: false,
        cursorRejected: true,
        searchRule:
          "A ligação da página não é válida para estes filtros; a consulta recomeça no início.",
      },
    };
  }

  const legacy = await apiFetch<RawPerson[]>(
    `/api/v1/public/politicians?limit=${LEGACY_POLITICIAN_LIMIT}`,
  );
  if (!legacy.ok || !Array.isArray(legacy.data)) {
    return {
      status,
      showingFallback: false,
      data: {
        people: [],
        total: 0,
        totalIsExact: false,
        limit,
        query: filters.query,
        partyShort: filters.partyShort,
        parties: [],
        paginationMode: "LEGACY_PAGE",
        compatibilityMode: "UNAVAILABLE",
        currentPage: 1,
        hasNext: false,
        hasPrevious: false,
        cursorRejected: false,
        searchRule:
          "A pesquisa limita apenas identidades publicadas e nunca cria correspondências.",
      },
    };
  }

  const legacyPeople = legacy.data.map(mapPerson);
  const filtered = filterLegacyPoliticians(
    legacyPeople,
    filters.query,
    filters.partyShort,
  );
  const complete =
    status.mode !== "UNAVAILABLE"
    && status.counts.politicians === legacyPeople.length
    && legacyPeople.length <= LEGACY_POLITICIAN_LIMIT;
  const offset = (requestedPage - 1) * limit;
  const page = filtered.slice(offset, offset + limit);

  return {
    status,
    showingFallback: false,
    data: {
      people: page,
      total: filtered.length,
      totalIsExact: complete,
      limit,
      query: filters.query,
      partyShort: filters.partyShort,
      parties: legacyPartyFacets(legacyPeople, filters.query),
      paginationMode: "LEGACY_PAGE",
      compatibilityMode: complete ? "LEGACY_COMPLETE" : "LEGACY_LIMITED",
      currentPage: requestedPage,
      hasNext: offset + limit < filtered.length,
      hasPrevious: requestedPage > 1,
      cursorRejected: false,
      searchRule:
        "A pesquisa limita apenas identidades já publicadas e nunca cria correspondências.",
    },
  };
}

export async function loadPublicPoliticians(): Promise<LoadedData<PublicPersonSummary[]>> {
  const statusPromise = loadPublicDataStatus();
  let pageRequest = apiFetch<RawPoliticianDirectory>(
    politicianDirectoryPath({ pageSize: 100 }),
  );
  const people: PublicPersonSummary[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;

  for (let page = 0; page < 100; page += 1) {
    const result = await pageRequest;
    if (!result.ok || !Array.isArray(result.data.items)) break;
    people.push(...result.data.items.map(mapPerson));
    const nextCursor = result.data.next_cursor ?? undefined;
    if (!nextCursor) {
      const complete = people.length === result.data.total;
      return {
        data: complete ? people : [],
        status: await statusPromise,
        showingFallback: false,
      };
    }
    if (seenCursors.has(nextCursor)) break;
    seenCursors.add(nextCursor);
    cursor = nextCursor;
    pageRequest = apiFetch<RawPoliticianDirectory>(
      politicianDirectoryPath({ cursor, pageSize: 100 }),
    );
  }

  const [status, legacy] = await Promise.all([
    statusPromise,
    apiFetch<RawPerson[]>(
      `/api/v1/public/politicians?limit=${LEGACY_POLITICIAN_LIMIT}`,
    ),
  ]);
  if (
    legacy.ok
    && Array.isArray(legacy.data)
    && status.mode !== "UNAVAILABLE"
    && legacy.data.length === status.counts.politicians
    && legacy.data.length <= LEGACY_POLITICIAN_LIMIT
  ) {
    return { data: legacy.data.map(mapPerson), status, showingFallback: false };
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
      sessions: sessions.ok ? sessions.data.map(mapParliamentSession) : [],
      initiatives: initiatives.ok ? initiatives.data.map(mapParliamentInitiative) : [],
      votes: votes.ok ? votes.data.map(mapParliamentVote) : [],
      publicationHistory: publicationHistory.ok
        ? publicationHistory.data.map(mapParliamentPublicationHistory)
        : [],
    },
  };
}

export type PublicParliamentExplorerFilters = {
  kind: "sessions" | "initiatives" | "votes";
  legislature: string;
  query?: string;
  dateFrom?: string;
  dateTo?: string;
  initiativeType?: string;
  initiativeStatus?: string;
  voteResult?: string;
  isNominal?: boolean;
  partySourceId?: string;
  choice?: "FAVOR" | "AGAINST" | "ABSTENTION" | "ABSENT" | "UNKNOWN";
  page: number;
  pageSize?: number;
};

function hasAdvancedParliamentFilters(filters: PublicParliamentExplorerFilters): boolean {
  return Boolean(
    filters.query
      || filters.dateFrom
      || filters.dateTo
      || filters.initiativeType
      || filters.initiativeStatus
      || filters.voteResult
      || filters.isNominal !== undefined
      || filters.partySourceId
      || filters.choice,
  );
}

function legacyParliamentPath(
  filters: PublicParliamentExplorerFilters,
  pageSize: number,
  offset: number,
): string {
  const segment = {
    sessions: "sessions",
    initiatives: "initiatives",
    votes: "votes",
  }[filters.kind];
  const query = new URLSearchParams({
    legislature: filters.legislature,
    limit: String(pageSize),
    offset: String(offset),
  });
  return `/api/v1/public/parliament/${segment}?${query}`;
}

export async function loadPublicParliamentExplorer(
  filters: PublicParliamentExplorerFilters,
): Promise<LoadedData<PublicParliamentExplorer>> {
  const pageSize = Math.min(100, Math.max(1, filters.pageSize ?? 20));
  const offset = (Math.max(1, filters.page) - 1) * pageSize;
  const query = new URLSearchParams({
    kind: filters.kind,
    legislature: filters.legislature,
    limit: String(pageSize),
    offset: String(offset),
  });
  if (filters.query) query.set("q", filters.query);
  if (filters.dateFrom) query.set("date_from", filters.dateFrom);
  if (filters.dateTo) query.set("date_to", filters.dateTo);
  if (filters.initiativeType) query.set("initiative_type", filters.initiativeType);
  if (filters.initiativeStatus) query.set("initiative_status", filters.initiativeStatus);
  if (filters.voteResult) query.set("vote_result", filters.voteResult);
  if (filters.isNominal !== undefined) query.set("is_nominal", String(filters.isNominal));
  if (filters.partySourceId) query.set("party_source_id", filters.partySourceId);
  if (filters.choice) query.set("choice", filters.choice);

  const historyQuery = new URLSearchParams({
    legislature: filters.legislature,
    limit: "20",
  });
  const [status, explorer, publicationHistory] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawParliamentExplorer>(`/api/v1/public/parliament/explore?${query}`),
    apiFetch<RawParliamentPublicationHistoryItem[]>(
      `/api/v1/public/parliament/publication-history?${historyQuery}`,
    ),
  ]);

  const canUseReviewedCompatibilityRoute =
    !explorer.ok
    && explorer.status === 404
    && !hasAdvancedParliamentFilters(filters);
  const legacy = canUseReviewedCompatibilityRoute
    ? await apiFetch<
        RawParliamentarySession[] | RawParliamentaryInitiative[] | RawParliamentaryVote[]
      >(legacyParliamentPath(filters, pageSize, offset))
    : null;

  const raw = explorer.ok ? explorer.data : null;
  const legacyRows = legacy?.ok ? legacy.data : [];
  const legacySessions = filters.kind === "sessions"
    ? (legacyRows as RawParliamentarySession[]).map(mapParliamentSession)
    : [];
  const legacyInitiatives = filters.kind === "initiatives"
    ? (legacyRows as RawParliamentaryInitiative[]).map(mapParliamentInitiative)
    : [];
  const legacyVotes = filters.kind === "votes"
    ? (legacyRows as RawParliamentaryVote[]).map(mapParliamentVote)
    : [];
  const usingCompatibilityRoute = Boolean(legacy?.ok);
  const legacyTotalIsExact = legacyRows.length < pageSize;
  const legacyTotal = offset + legacyRows.length + (legacyTotalIsExact ? 0 : 1);
  const compatibilityMode = explorer.ok
    ? "CURRENT"
    : usingCompatibilityRoute
      ? "LIMITED_READ_ONLY"
      : explorer.status === 404
        ? "API_UPGRADE_REQUIRED"
        : "UNAVAILABLE";
  const facet = (item: RawParliamentFacetOption) => ({
    value: item.value,
    label: item.label,
    count: item.count,
  });
  return {
    status,
    showingFallback: false,
    data: {
      kind: raw?.kind ?? filters.kind,
      legislature: raw?.legislature ?? filters.legislature,
      query: raw?.query ?? filters.query,
      dateFrom: raw?.date_from ?? filters.dateFrom,
      dateTo: raw?.date_to ?? filters.dateTo,
      sessions: raw ? raw.sessions.map(mapParliamentSession) : legacySessions,
      initiatives: raw ? raw.initiatives.map(mapParliamentInitiative) : legacyInitiatives,
      votes: raw ? raw.votes.map(mapParliamentVote) : legacyVotes,
      total: raw?.total ?? legacyTotal,
      totalIsExact: raw ? true : legacyTotalIsExact,
      limit: raw?.limit ?? pageSize,
      offset: raw?.offset ?? offset,
      facets: {
        legislatures:
          raw?.facets.legislatures
          ?? (usingCompatibilityRoute && legacyRows.length ? [filters.legislature] : []),
        initiativeTypes: raw?.facets.initiative_types.map(facet) ?? [],
        initiativeStatuses: raw?.facets.initiative_statuses.map(facet) ?? [],
        voteResults: raw?.facets.vote_results.map(facet) ?? [],
        parties: raw?.facets.parties.map(facet) ?? [],
        topicsAvailable: false,
        topicsNote:
          raw?.facets.topics_note
          ?? "Tema não disponibilizado pela fonte oficial publicada.",
      },
      explanationRule:
        raw?.explanation_rule
        ?? "Sem prova oficial adicional, o impacto permanece como dados indisponíveis.",
      publicationHistory: publicationHistory.ok
        ? publicationHistory.data.map(mapParliamentPublicationHistory)
        : [],
      availability: {
        explorer: explorer.ok || usingCompatibilityRoute,
        publicationHistory: publicationHistory.ok,
        compatibilityMode,
      },
    },
  };
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
    const profileSource = toOfficialSource(result.data.profile_source);
    const votes = result.data.votes
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
      }));
    const attendance: AttendanceSummary = result.data.attendance
      ? {
          available: result.data.attendance.available,
          recordCount: result.data.attendance.record_count,
          presentCount: result.data.attendance.present_count,
          absentCount: result.data.attendance.absent_count,
          excusedCount: result.data.attendance.excused_count,
          attendanceRate: result.data.attendance.attendance_rate ?? undefined,
          observedFrom: result.data.attendance.observed_from
            ? formatDate(result.data.attendance.observed_from)
            : undefined,
          observedThrough: result.data.attendance.observed_through
            ? formatDate(result.data.attendance.observed_through)
            : undefined,
          note: result.data.attendance.note,
          source: result.data.attendance.source
            ? toOfficialSource(result.data.attendance.source)
            : undefined,
        }
      : {
          available: result.data.attendance_rate != null,
          recordCount: 0,
          presentCount: 0,
          absentCount: 0,
          excusedCount: 0,
          attendanceRate: result.data.attendance_rate ?? undefined,
          note: result.data.attendance_label,
        };
    const fallbackLookupSource = result.data.declaration_source;
    const declarationLookupSource: OfficialLookup = result.data.declaration_lookup_source
      ? {
          publisher: result.data.declaration_lookup_source.publisher as OfficialSource["publisher"],
          label: result.data.declaration_lookup_source.label,
          url: result.data.declaration_lookup_source.url,
          note: result.data.declaration_lookup_source.note,
        }
      : {
          publisher: (fallbackLookupSource?.publisher ?? "EPT") as OfficialSource["publisher"],
          label: fallbackLookupSource?.label ?? "Entidade para a Transparência — portal oficial",
          url: fallbackLookupSource?.url ?? "https://www.tribunalconstitucional.pt/tc/ept/",
          note: (
            "Ligação para pesquisa institucional; não confirma a existência, o conteúdo "
            + "ou o estado de uma declaração desta pessoa."
          ),
        };
    const coverage: PoliticianProfileCoverage = result.data.coverage
      ? {
          identity: mapCoverageArea(result.data.coverage.identity),
          membershipObservations: mapCoverageArea(
            result.data.coverage.membership_observations,
          ),
          mandates: mapCoverageArea(result.data.coverage.mandates),
          attendance: mapCoverageArea(result.data.coverage.attendance),
          initiatives: mapCoverageArea(result.data.coverage.initiatives),
          nominalVotes: mapCoverageArea(result.data.coverage.nominal_votes),
          declarations: mapCoverageArea(result.data.coverage.declarations),
          matchingRule: result.data.coverage.matching_rule,
        }
      : legacyProfileCoverage(result.data, profileSource);
    const declarations = (
      result.data.declarations
      ?? (result.data.declaration ? [result.data.declaration] : [])
    ).map((item) => ({
      id: item.id,
      declarationType: item.declaration_type,
      declaredAt: item.declared_at ? formatDate(item.declared_at) : undefined,
      periodLabel: item.period_label ?? undefined,
      publicAccessStatus: item.public_access_status,
      verifiedAt: formatDate(item.verified_at),
      source: toOfficialSource(item.source),
    }));
    const membershipObservations = (result.data.membership_observations ?? []).map((item) => ({
      id: item.id,
      legislature: item.legislature,
      parliamentaryName: item.parliamentary_name,
      party: item.party,
      partyShort: item.party_short,
      constituency: item.constituency,
      observedAt: formatDate(item.observed_at),
      verifiedAt: formatDate(item.verified_at),
      source: toOfficialSource(item.source),
    }));
    if (result.data.contract_version !== "v5.6" && !membershipObservations.length) {
      membershipObservations.push({
        id: `legacy-observation-${result.data.id}`,
        legislature: result.data.legislature,
        parliamentaryName: result.data.name,
        party: result.data.party,
        partyShort: result.data.party_short,
        constituency: result.data.constituency,
        observedAt: formatDate(result.data.observed_at ?? result.data.verified_at),
        verifiedAt: formatDate(result.data.verified_at),
        source: profileSource,
      });
    }
    return {
      status,
      showingFallback: false,
      data: {
        ...mapPerson(result.data),
        contractVersion: result.data.contract_version ?? "legacy",
        role: formatRole(result.data.role),
        attendanceRate: (
          result.data.attendance?.attendance_rate
          ?? result.data.attendance_rate
          ?? undefined
        ),
        attendanceLabel: result.data.attendance?.note ?? result.data.attendance_label,
        nominalVotesAvailable: result.data.nominal_votes_available,
        nominalVoteCount: result.data.nominal_vote_count,
        membershipObservations,
        mandates: (result.data.mandates ?? []).map((item) => ({
          id: item.id,
          officeTitle: item.office_title,
          legislature: item.legislature ?? undefined,
          party: item.party ?? undefined,
          partyShort: item.party_short ?? undefined,
          constituency: item.constituency ?? undefined,
          startedAt: formatDate(item.started_at),
          endedAt: item.ended_at ? formatDate(item.ended_at) : undefined,
          verifiedAt: formatDate(item.verified_at),
          source: toOfficialSource(item.source),
        })),
        attendance,
        initiatives: (result.data.initiatives ?? []).map((item) => ({
          id: item.id,
          number: item.number,
          initiativeType: item.initiative_type,
          title: item.title,
          status: item.status ?? undefined,
          introducedAt: item.introduced_at ? formatDate(item.introduced_at) : undefined,
          relation: item.relation,
          source: toOfficialSource(item.source),
        })),
        declarations,
        declaration: declarations[0],
        declarationLookupSource,
        coverage,
        votes,
      },
    };
  }
  if (result.status === 404) {
    return { data: null, status, showingFallback: false };
  }
  return {
    data: null,
    status: {
      ...status,
      mode: "UNAVAILABLE",
      message: "O perfil está temporariamente indisponível devido a uma falha na API pública.",
    },
    showingFallback: false,
  };
}

export async function loadPublicPromises(): Promise<LoadedData<GovernmentPromise[]>> {
  const [status, result] = await Promise.all([
    loadPublicDataStatus(),
    apiFetch<RawPromise[]>("/api/v1/public/promises?limit=1000"),
  ]);
  const allowedStatuses = new Set([
    "UNVERIFIED",
    "NOT_STARTED",
    "IN_PROGRESS",
    "PARTIAL",
    "FULFILLED",
  ]);
  if (result.ok && result.data.some((item) => !allowedStatuses.has(item.status))) {
    return {
      data: initialGovernmentCommitments,
      status: {
        ...status,
        mode: "UNAVAILABLE",
        message:
          "O Promessómetro recebeu um estado editorial incompatível; a projeção publicada foi recusada.",
      },
      showingFallback: true,
    };
  }
  if (result.ok && result.data.length) {
    return {
      status,
      showingFallback: false,
      data: result.data.map((item) => ({
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
  if (result.ok) {
    return { data: initialGovernmentCommitments, status, showingFallback: true };
  }
  return {
    data: initialGovernmentCommitments,
    status: {
      ...status,
      mode: "UNAVAILABLE",
      message: "O Promessómetro está temporariamente indisponível; é apresentada apenas a base editorial inicial.",
    },
    showingFallback: true,
  };
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
