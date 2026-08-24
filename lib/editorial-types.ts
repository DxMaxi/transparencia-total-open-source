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

export type AiDreSnapshotCandidate = {
  snapshot_id: string;
  official_identifier: string | null;
  title: string;
  source_url: string;
  source_content_sha256: string;
  normalised_text_sha256: string;
  source_characters: number;
  retrieved_at: string;
  published_at: string | null;
  collected_at: string;
  parser_version: string;
  archive: {
    storage_backend: string;
    byte_size: number;
    archived_at: string;
    attestation_sha256: string;
  };
  existing_case: null | {
    id: string;
    state: EditorialState;
    revision: number;
    version_number: number;
    normalized_sha256: string;
    updated_at: string;
  };
  generation_eligible: boolean;
};

export type AiDreSnapshotList = {
  items: AiDreSnapshotCandidate[];
  excluded_invalid_snapshots: number;
  provider: {
    enabled: boolean;
    name: "disabled" | "openai";
    model: string;
    prompt_version: string;
    prompt_sha256: string;
    store: false;
  };
  daily_limit: number;
  attempts_today: number;
  remaining_today: number;
  publication_performed: false;
  generation_rule: string;
};

export type AiDreSourceEvidence = {
  case_id: string;
  case_revision: number;
  current_version_sha256: string;
  snapshot_id: string;
  official_identifier: string | null;
  title: string;
  source_url: string;
  retrieved_at: string;
  published_at: string | null;
  collected_at: string;
  source_content_sha256: string;
  normalised_text_sha256: string;
  parser_version: string;
  source_characters: number;
  text_limit: number;
  text_offset: number;
  text_end: number;
  has_previous_text: boolean;
  has_next_text: boolean;
  extracted_text: string;
  archive: {
    storage_backend: string;
    byte_size: number;
    archived_at: string;
    attestation_sha256: string;
  };
  review_rule: string;
  publication_performed: false;
};

export type AiDreProposalResult = {
  case: EditorialCaseDetail;
  created: boolean;
  reused: boolean;
  regenerated?: boolean;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
};

export type AiEditorialPublicSource = {
  publisher: "DRE";
  label: string;
  title: string;
  official_identifier: string | null;
  url: string;
  retrieved_at: string;
  published_at: string | null;
  content_sha256: string;
  normalised_text_sha256: string;
};

export type AiEditorialGenerationProof = {
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

export type AiEditorialPublicationPreview = {
  case_id: string;
  case_state: EditorialState;
  revision: number;
  public_id: string;
  source: AiEditorialPublicSource | null;
  generation: AiEditorialGenerationProof | null;
  editorial_version_sha256: string;
  output_sha256: string;
  publication_proof_sha256: string;
  public_projection: Record<string, unknown> | null;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_publication: false;
  publication_rule: string;
};

export type AiEditorialPublicationResult = {
  created: true;
  case_id: string;
  state: "PUBLISHED";
  revision: number;
  public_id: string;
  decision_sha256: string;
  event_sha256: string;
  publication_review_id: string;
  audit_event_id: string;
  publication_rule: string;
};

export type AiEditorialWithdrawalPreview = {
  case_id: string;
  case_state: EditorialState;
  revision: number;
  public_id: string;
  source: AiEditorialPublicSource | null;
  generation: AiEditorialGenerationProof | null;
  editorial_version_sha256: string;
  output_sha256: string;
  publication_proof_sha256: string;
  public_review_id: string;
  publication_audit_event_id: string;
  publication_event_id: string;
  publication_event_sha256: string;
  public_effect: {
    kind: "DATA_UNAVAILABLE";
    public_id: string;
    message: string;
  };
  public_effect_sha256: string;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  withdrawal_rule: string;
};

export type AiEditorialWithdrawalResult = {
  created: true;
  case_id: string;
  state: "WITHDRAWN";
  revision: number;
  public_id: string;
  reason_category: ParliamentWithdrawalReason;
  decision_sha256: string;
  event_sha256: string;
  publication_review_id: string;
  audit_event_id: string;
  public_effect: AiEditorialWithdrawalPreview["public_effect"];
  public_effect_sha256: string;
  withdrawal_rule: string;
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

export const PARLIAMENT_WITHDRAWAL_REASON_LABELS = {
  EXTRACTION_OR_NORMALISATION_ERROR: "Erro de recolha, extração ou normalização",
  SOURCE_DIVERGENCE: "Divergência reproduzível com a fonte",
  OFFICIAL_SOURCE_CORRECTION: "Correção ou substituição pela fonte oficial",
  DUPLICATE_OR_CORRUPT_DATA: "Duplicação ou corrupção de dados",
  PROVEN_IDENTITY_ERROR: "Erro de identidade demonstrado",
  DOCUMENTED_METHODOLOGY_CHANGE: "Alteração metodológica documentada",
  LEGAL_OR_AUTHORITY_ORDER: "Obrigação legal ou decisão de autoridade",
  DATA_PROTECTION_OR_PERSONALITY_RIGHTS: "Proteção de dados ou direitos de personalidade",
  SECURITY_RISK: "Risco de segurança",
  THIRD_PARTY_RIGHTS: "Direitos de terceiros",
  DECLARED_SCOPE_ERROR: "Publicação fora do âmbito declarado",
} as const;

export type ParliamentWithdrawalReason = keyof typeof PARLIAMENT_WITHDRAWAL_REASON_LABELS;

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

export type PoliticianProfilePeriod = {
  source_id: string | null;
  starts_at: string | null;
  ends_at: string | null;
};

export type PoliticianProfileEditorialCandidate = {
  observation_id: string;
  source_document_id: string;
  snapshot_id: string;
  official_deputy_id: string;
  official_candidate_id: string | null;
  parliamentary_name: string;
  full_name: string | null;
  legislature: string;
  constituency: { source_id: string | null; label: string | null };
  parliamentary_groups: Array<
    PoliticianProfilePeriod & { short_name: string }
  >;
  mandate_situations: Array<
    Omit<PoliticianProfilePeriod, "source_id"> & { description: string }
  >;
  offices: Array<PoliticianProfilePeriod & { title: string }>;
  observation_sha256: string;
  snapshot: {
    parser_version: string;
    normalised_sha256: string;
    collected_at: string;
  };
  source: ParliamentEditorialSnapshot["source"];
  archive: ParliamentEditorialSnapshot["archive"];
  manifest_counts: {
    deputies: number;
    group_periods: number;
    situation_periods: number;
    office_periods: number;
  };
  materialised_counts: {
    deputies: number;
    group_periods: number;
    situation_periods: number;
    office_periods: number;
  };
  manifest_matches: boolean;
  structure_valid: boolean;
  warnings: string[];
  editorial_case: null | {
    id: string;
    state: EditorialState;
    revision: number;
    origin: "HUMAN" | "INGESTION" | "AI";
  };
  proposal_eligible: boolean;
  mandate_inference_allowed: false;
  publication_state: "PRIVATE_ONLY";
};

export type PoliticianProfileEditorialCandidateList = {
  items: PoliticianProfileEditorialCandidate[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  publication_performed: false;
  search_rule: string;
};

export type PoliticianProfileEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
  person_created: false;
  mandate_created: false;
};

export type PoliticianProfilePublicationReadiness = {
  snapshot_id: string;
  source_document_id: string;
  legislature: string;
  parser_version: string;
  normalised_sha256: string;
  collected_at: string;
  source: ParliamentEditorialSnapshot["source"] & {
    publisher: string;
    kind: string;
  };
  archive: ParliamentEditorialSnapshot["archive"] | null;
  archive_attested: boolean;
  manifest_counts: PoliticianProfileEditorialCandidate["manifest_counts"];
  materialised_counts: PoliticianProfileEditorialCandidate["materialised_counts"];
  manifest_matches: boolean;
  editorial_counts: Record<EditorialState | "MISSING", number>;
  identity_projection: {
    exact_existing_people: number;
    new_people_required: number;
    existing_memberships: number;
    existing_party_links: number;
    legacy_review_decisions: number;
    legacy_positive_reviews: number;
  };
  readiness_proof_sha256: string | null;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string; count: number }>;
  publication_performed: false;
  public_write_performed: false;
  mandate_inference_allowed: false;
  publication_state: "PRIVATE_READINESS_ONLY";
  publication_rule: string;
};

export type PoliticianProfilePublicationReadinessList = {
  items: PoliticianProfilePublicationReadiness[];
  limit: number;
  publication_performed: false;
  readiness_rule: string;
};

export type PoliticianProfileSnapshotPublicationPreview = {
  snapshot_id: string;
  legislature: string;
  parser_version: string;
  normalised_sha256: string;
  collected_at: string;
  source: PoliticianProfilePublicationReadiness["source"];
  archive: PoliticianProfilePublicationReadiness["archive"];
  manifest_counts: PoliticianProfilePublicationReadiness["manifest_counts"];
  materialised_counts: PoliticianProfilePublicationReadiness["materialised_counts"];
  editorial_counts: PoliticianProfilePublicationReadiness["editorial_counts"];
  identity_projection: PoliticianProfilePublicationReadiness["identity_projection"];
  readiness_proof_sha256: string | null;
  publication_proof_sha256: string | null;
  public_effect: {
    people_to_create: number;
    people_to_reuse_by_exact_depid: number;
    memberships_to_create: number;
    memberships_to_reuse: number;
    person_reviews_to_append: number;
    cases_to_publish: number;
    mandates_to_create: 0;
    party_links_to_create: 0;
  };
  eligible: boolean;
  blockers: Array<{ code: string; detail: string; count: number }>;
  automatic_publication: false;
  mandate_inference_allowed: false;
  party_inference_allowed: false;
  publication_rule: string;
};

export type PoliticianProfileSnapshotPublicationResult = {
  created: true;
  snapshot_id: string;
  legislature: string;
  state: "PUBLISHED";
  deputy_count: number;
  people_created: number;
  people_reused: number;
  memberships_created: number;
  memberships_reused: number;
  person_reviews_created: number;
  person_audits_created: number;
  editorial_decisions_created: number;
  publication_events_created: number;
  snapshot_review_id: string;
  snapshot_audit_id: string;
  readiness_proof_sha256: string;
  publication_proof_sha256: string;
  mandates_created: 0;
  party_links_created: 0;
  publication_rule: string;
};

export type PoliticianProfileSnapshotPublicEffect =
  | {
      kind: "DATA_UNAVAILABLE";
      legislature: string;
      message: string;
    }
  | {
      kind: "FALLBACK_TO_PREVIOUS_SNAPSHOT";
      legislature: string;
      source_document_reference_sha256: string;
      profile_count: number;
      source_url: string;
      source_retrieved_at: string;
      source_sha256: string;
      verified_at: string;
      message: string;
    };

export type PoliticianProfileSnapshotWithdrawalPreview = {
  snapshot_id: string;
  legislature: string;
  source: {
    url: string;
    retrieved_at: string;
    content_sha256: string;
  };
  normalised_sha256: string;
  collected_at: string;
  manifest_counts: PoliticianProfilePublicationReadiness["manifest_counts"];
  materialised_counts: PoliticianProfilePublicationReadiness["materialised_counts"];
  publication_proof_sha256: string;
  withdrawal_proof_sha256: string | null;
  public_effect: PoliticianProfileSnapshotPublicEffect;
  public_effect_sha256: string;
  published_profile_count: number;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string; count: number }>;
  automatic_withdrawal: false;
  people_to_delete: 0;
  memberships_to_delete: 0;
  versions_to_delete: 0;
  withdrawal_rule: string;
};

export type PoliticianProfileSnapshotWithdrawalResult = {
  created: true;
  snapshot_id: string;
  legislature: string;
  state: "WITHDRAWN";
  reason_category: ParliamentWithdrawalReason;
  deputy_count: number;
  person_reviews_created: number;
  person_audits_created: number;
  editorial_decisions_created: number;
  withdrawal_events_created: number;
  snapshot_review_id: string;
  snapshot_audit_id: string;
  withdrawal_proof_sha256: string;
  public_effect: PoliticianProfileSnapshotPublicEffect;
  public_effect_sha256: string;
  people_deleted: 0;
  memberships_deleted: 0;
  versions_deleted: 0;
  withdrawal_rule: string;
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
    event_sha256?: string;
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

export type ParliamentEditorialPublicEffect =
  | {
      kind: "DATA_UNAVAILABLE";
      scope: ParliamentEditorialScope;
      legislature: string;
      message: string;
    }
  | {
      kind: "FALLBACK_TO_PREVIOUS_SNAPSHOT";
      scope: ParliamentEditorialScope;
      legislature: string;
      snapshot_reference_sha256: string;
      snapshot_sha256: string;
      collected_at: string;
      source_url: string;
      source_retrieved_at: string;
      source_sha256: string;
      verified_at: string;
      message: string;
    };

export type ParliamentEditorialWithdrawalPreview = {
  case_id: string;
  case_state: EditorialState;
  revision: number;
  scope: ParliamentEditorialScope;
  scope_label: string;
  target_type: "PARLIAMENT_ACTIVITY_SNAPSHOT" | "PARLIAMENT_VOTES_SNAPSHOT";
  target_id: string;
  legislature: string;
  source_sha256: string;
  snapshot_sha256: string;
  editorial_sha256: string;
  publication_proof_sha256: string;
  manifest_counts: ParliamentEditorialSnapshot["manifest_counts"];
  public_review_id: string;
  public_reviewed_at: string;
  publication_audit_event_id: string;
  publication_event_id: string;
  publication_event_sha256: string;
  publication_event_created_at: string;
  public_effect: ParliamentEditorialPublicEffect;
  public_effect_sha256: string;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_withdrawal: false;
  withdrawal_rule: string;
};

export type ParliamentEditorialWithdrawalResult = {
  created: true;
  case_id: string;
  state: "WITHDRAWN";
  revision: number;
  scope: ParliamentEditorialScope;
  target_type: string;
  target_id: string;
  reason_category: ParliamentWithdrawalReason;
  decision_sha256: string;
  event_sha256: string;
  publication_review_id: string;
  audit_event_id: string;
  public_effect: ParliamentEditorialPublicEffect;
  public_effect_sha256: string;
  withdrawal_rule: string;
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
