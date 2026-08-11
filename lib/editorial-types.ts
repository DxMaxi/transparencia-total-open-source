export const EDITORIAL_STATES = [
  "PENDING",
  "IN_REVIEW",
  "APPROVED",
  "REJECTED",
  "PUBLISHED",
  "WITHDRAWN",
] as const;

export const EDITORIAL_KINDS = [
  "PARLIAMENT_ACTIVITY",
  "PARLIAMENT_VOTE",
  "POLITICIAN_PROFILE",
  "GOVERNMENT_PROMISE",
  "PUBLIC_CONTRACT",
  "INTEREST_RELATIONSHIP",
  "RIGHT_OF_REPLY",
  "AI_EXPLANATION",
  "OTHER",
] as const;

export type EditorialState = (typeof EDITORIAL_STATES)[number];
export type EditorialKind = (typeof EDITORIAL_KINDS)[number];

export type StaffSession = {
  staff_id: string;
  auth_user_id: string;
  public_alias: string;
  role: "ADMIN" | "REVIEWER";
  assurance_level: "aal1" | "aal2";
  mfa_required: boolean;
};

export type EditorialSourceSummary = {
  title: string;
  publisher: string;
  url: string;
  retrieved_at: string;
  content_sha256: string;
};

export type EditorialCaseSummary = {
  id: string;
  kind: EditorialKind;
  subject_type: string;
  subject_id: string;
  current_state: EditorialState;
  revision: number;
  origin: "HUMAN" | "INGESTION" | "AI";
  created_by_alias: string;
  created_at: string;
  updated_at: string;
  version_number: number;
  normalized_sha256: string;
  source: EditorialSourceSummary;
};

export type EditorialCaseList = {
  items: EditorialCaseSummary[];
  next_cursor: string | null;
  counts: Record<EditorialState, number>;
};

export type EditorialSourceCandidate = {
  id: string;
  publisher: string;
  kind: string;
  title: string;
  official_identifier: string | null;
  url: string;
  retrieved_at: string;
  published_at: string | null;
  content_sha256: string;
  mime_type: string | null;
  editorial_case_count: number;
  archive_attested: true;
};

export type EditorialVersion = {
  id: string;
  version_number: number;
  normalized_data: Record<string, unknown>;
  normalized_sha256: string;
  previous_version_id: string | null;
  origin: "HUMAN" | "INGESTION" | "AI";
  created_by_alias: string;
  created_at: string;
  is_current: boolean;
};

export type EditorialDecision = {
  id: string;
  version_id: string;
  action: string;
  previous_state: EditorialState | null;
  resulting_state: EditorialState;
  case_revision: number;
  rationale: string;
  source_confirmed: boolean;
  actor_alias: string;
  decision_sha256: string;
  created_at: string;
};

export type EditorialCaseDetail = {
  id: string;
  kind: EditorialKind;
  subject_type: string;
  subject_id: string;
  current_state: EditorialState;
  revision: number;
  origin: "HUMAN" | "INGESTION" | "AI";
  created_by_alias: string;
  created_at: string;
  updated_at: string;
  current_version_id: string;
  source: {
    id: string;
    publisher: string;
    kind: string;
    title: string;
    official_identifier: string | null;
    url: string;
    retrieved_at: string;
    published_at: string | null;
    content_sha256: string;
    mime_type: string | null;
    archive: null | {
      storage_backend: string;
      byte_size: number;
      archived_at: string;
      attestation_sha256: string;
    };
  };
  versions: EditorialVersion[];
  decisions: EditorialDecision[];
  publication_events: Array<{
    id: string;
    version_id: string;
    action: string;
    target_type: string;
    target_id: string;
    rationale: string;
    actor_alias: string;
    event_sha256: string;
    created_at: string;
  }>;
  publishable: false;
  publication_notice: string;
};

export type ParliamentEditorialScope = "activity" | "votes";

export type ParliamentSnapshotDifference = {
  added: number;
  removed: number;
  changed: number;
  unchanged: number;
};

export type ParliamentEditorialSnapshot = {
  snapshot_id: string;
  source_document_id: string;
  legislature: string;
  parser_version: string;
  normalised_sha256: string;
  collected_at: string;
  source: {
    title: string;
    official_identifier: string | null;
    url: string;
    retrieved_at: string;
    content_sha256: string;
    mime_type: string | null;
  };
  archive: {
    storage_backend: string;
    byte_size: number;
    archived_at: string;
    attestation_sha256: string;
  };
  manifest_counts: {
    sessions: number;
    initiatives: number;
    votes: number;
    vote_records: number;
  };
  materialised_counts: {
    sessions: number;
    initiatives: number;
    votes: number;
    vote_records: number;
  };
  manifest_matches: boolean;
  coverage: {
    nominal_votes: number;
    votes_without_records: number;
    person_records: number;
    linked_person_records: number;
    unlinked_person_records: number;
    party_records: number;
    linked_party_records: number;
    unlinked_party_records: number;
    unknown_actor_records: number;
    unknown_choice_records: number;
    inconsistent_actor_links: number;
  };
  previous_snapshot: null | {
    id: string;
    normalised_sha256: string;
    collected_at: string;
  };
  differences: {
    status: "NO_PREVIOUS_SNAPSHOT" | "COMPARED_BY_EXACT_SOURCE_ID";
    sessions: ParliamentSnapshotDifference | null;
    initiatives: ParliamentSnapshotDifference | null;
    votes: ParliamentSnapshotDifference | null;
  };
  limitations: string[];
  editorial_cases: Record<
    ParliamentEditorialScope,
    null | {
      id: string;
      state: EditorialState;
      revision: number;
      origin: "HUMAN" | "INGESTION" | "AI";
    }
  >;
  proposal_eligible: boolean;
  publication_state: "PRIVATE_ONLY";
};

export type ParliamentEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
};

export type ParliamentEditorialPublicationPreview = {
  case_id: string;
  case_state: EditorialState;
  revision: number;
  scope: ParliamentEditorialScope;
  scope_label: string;
  target_type: "PARLIAMENT_ACTIVITY_SNAPSHOT" | "PARLIAMENT_VOTES_SNAPSHOT";
  target_id: string;
  legislature: string;
  snapshot_sha256: string;
  parser_version: string;
  collected_at: string;
  source: ParliamentEditorialSnapshot["source"];
  archive: ParliamentEditorialSnapshot["archive"];
  manifest_counts: ParliamentEditorialSnapshot["manifest_counts"];
  materialised_counts: ParliamentEditorialSnapshot["materialised_counts"];
  coverage: ParliamentEditorialSnapshot["coverage"];
  editorial_version: {
    id: string;
    normalized_sha256: string;
    integrity_matches: boolean;
    proof_matches_snapshot: boolean;
  };
  publication_proof_sha256: string;
  public_projection: {
    publishable: boolean | null;
    reviewed_at: string | null;
    reviewed_by: string | null;
  };
  existing_publication_event: null | {
    id: string;
    version_id: string;
    target_type: string;
    target_id: string;
    created_at: string;
  };
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_publication: false;
  publication_rule: string;
};

export type ParliamentEditorialPublicationResult = {
  created: true;
  case_id: string;
  state: "PUBLISHED";
  revision: number;
  scope: ParliamentEditorialScope;
  target_type: string;
  target_id: string;
  decision_sha256: string;
  event_sha256: string;
  publication_review_id: string;
  audit_event_id: string;
  publication_rule: string;
};

export const STATE_LABELS: Record<EditorialState, string> = {
  PENDING: "Por rever",
  IN_REVIEW: "Em revisão",
  APPROVED: "Aprovado (privado)",
  REJECTED: "Rejeitado",
  PUBLISHED: "Publicado",
  WITHDRAWN: "Retirado",
};

export const KIND_LABELS: Record<EditorialKind, string> = {
  PARLIAMENT_ACTIVITY: "Atividade parlamentar",
  PARLIAMENT_VOTE: "Votação parlamentar",
  POLITICIAN_PROFILE: "Perfil político",
  GOVERNMENT_PROMISE: "Promessa do Governo",
  PUBLIC_CONTRACT: "Contrato público",
  INTEREST_RELATIONSHIP: "Relação de interesses",
  RIGHT_OF_REPLY: "Direito de resposta",
  AI_EXPLANATION: "Explicação proposta por IA",
  OTHER: "Outro",
};
