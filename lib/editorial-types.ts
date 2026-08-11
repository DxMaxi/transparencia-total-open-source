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
