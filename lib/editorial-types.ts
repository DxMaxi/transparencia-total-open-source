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
    exact_person_records: number;
    unproven_person_records: number;
    linked_person_records: number;
    unlinked_person_records: number;
    mismatched_person_links: number;
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

export type EptPublicInterestEditorialCandidate = {
  observation_id: string;
  source_document_id: string;
  official_declaration_id: string;
  official_subject_reference_sha256: string;
  public_subject_name: string;
  declaration_type: "INTEREST_REGISTER";
  declared_at: string | null;
  period_label: string | null;
  observed_at: string;
  source_record_sha256: string;
  source: {
    title: string;
    official_identifier: string | null;
    url: string;
    retrieved_at: string;
    content_sha256: string;
    mime_type: string | null;
  };
  archive: null | {
    storage_backend: string;
    byte_size: number;
    archived_at: string;
    attestation_sha256: string;
  };
  legal_review_status: "REQUIRES_INDEPENDENT_LEGAL_REVIEW";
  identity_link_status: "UNLINKED_PRIVATE";
  existing_case: PoliticianProfileEditorialCandidate["editorial_case"];
  proposal_eligible: boolean;
  blocked_reasons: string[];
  public_projection_allowed: false;
  person_link_allowed: false;
  name_matching_allowed: false;
  income_or_asset_content_present: false;
};

export type EptPublicInterestEditorialCandidateList = {
  items: EptPublicInterestEditorialCandidate[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  publication_performed: false;
  identity_link_performed: false;
  search_rule: string;
  legal_scope: string;
};

export type EptPublicInterestEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
  declaration_created: false;
  person_link_created: false;
  public_review_created: false;
  independent_legal_review_completed: false;
};

export type BaseContractEditorialCandidate = {
  contract_snapshot_id: string;
  source_document_id: string;
  official_contract_id: string;
  object: string;
  procedure: string;
  cpv_code: string | null;
  base_value: string | null;
  contract_value: string | null;
  currency: string;
  decision_at: string | null;
  signed_at: string | null;
  published_at: string | null;
  execution_days: number | null;
  direct_official_url: string | null;
  parties: Array<{
    id: string;
    ordinal: number;
    role: "CONTRACTING_AUTHORITY" | "CONTRACTOR" | "CO_CONTRACTOR";
    source_name: string;
    protected_identifier_observed: boolean;
  }>;
  protected_identifier_count: number;
  protected_identifier_exposed: false;
  source_record_sha256: string;
  batch: {
    id: string;
    resource_year: number;
    resource_title: string;
    parser_version: string;
    normalised_sha256: string;
    contract_count: number;
    party_count: number;
    actual_contract_count: number;
    actual_party_count: number;
    collected_at: string;
    sync_status: string;
    sync_finished_at: string | null;
    records_read: number;
    records_written: number;
    warnings: string[];
    counts_match: boolean;
  };
  source: {
    title: string;
    url: string;
    retrieved_at: string;
    content_sha256: string;
    mime_type: string | null;
  };
  archive: null | {
    storage_backend: string;
    byte_size: number;
    archived_at: string;
    attestation_sha256: string;
  };
  catalogue: null | {
    scope_id: string;
    scope_sha256: string;
    source_sha256: string;
    archive_attestation_sha256: string;
    resource_id: string;
    resource_year: number;
    coverage_state: "HISTORICAL_CLOSED_YEAR" | "CURRENT_ROLLING_YEAR";
    versioned_url: string;
    stable_url: string;
    source_modified_at: string;
    byte_size: number;
    metadata_sha256: string;
  };
  existing_case: PoliticianProfileEditorialCandidate["editorial_case"];
  proposal_eligible: boolean;
  blocked_reasons: string[];
  coverage_claim: "SPECIFIC_SOURCE_RECORD_ONLY";
  annual_source_completeness_claimed: false;
  public_contract_creation_allowed: false;
  organisation_creation_allowed: false;
  identity_or_name_matching_allowed: false;
  relationship_creation_allowed: false;
  publication_allowed: false;
};

export type BaseContractEditorialCandidateList = {
  items: BaseContractEditorialCandidate[];
  total: number;
  limit: number;
  next_cursor: string | null;
  filter_required: boolean;
  publication_performed: false;
  organisation_created: false;
  relationship_created: false;
  protected_identifier_exposed: false;
  search_rule: string;
  coverage_rule: string;
};

export type BaseContractEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
  public_contract_created: false;
  organisation_created: false;
  interest_entity_created: false;
  match_review_created: false;
  relationship_created: false;
};

export type EptPublicInterestGate = {
  case_id: string;
  case_state: EditorialState;
  case_revision: number;
  version_id: string;
  version_sha256: string;
  observation_id: string;
  source_record_sha256: string;
  source: {
    url: string;
    retrieved_at: string;
    content_sha256: string;
    archive_attestation_sha256: string;
  };
  legal_assessment: null | {
    id: string;
    outcome:
      | "PERMITS_PUBLIC_INTEREST_METADATA_ONLY"
      | "DOES_NOT_PERMIT_PUBLICATION"
      | "REQUIRES_CHANGES";
    document_sha256: string;
    assessed_at: string;
    valid_until: string | null;
    assessment_proof_sha256: string;
    document_private_and_encrypted: true;
    system_issued_legal_opinion: false;
  };
  identity_link: null | {
    id: string;
    person_id: string;
    person_source_id: string;
    evidence_document_id: string;
    evidence_sha256: string;
    link_proof_sha256: string;
    name_matching_used: false;
    fuzzy_matching_used: false;
    raw_identifier_persisted: false;
  };
  blockers: Array<{ code: string; detail: string }>;
  publication_performed: false;
  legal_notice: string;
};

export type EptPublicInterestPublicationPreview = EptPublicInterestGate & {
  declaration_id: string;
  legal_assessment_proof_sha256: string | null;
  publication_proof_sha256: string | null;
  public_metadata: {
    declaration_type: "Registo público de interesses";
    declared_at: string | null;
    period_label: string | null;
    public_access_status: "PUBLIC_METADATA";
    income_or_asset_content_included: false;
    protected_identifier_included: false;
  };
  eligible: boolean;
  automatic_publication: false;
  publication_rule: string;
};

export type EptLegalAssessmentResult = {
  created: boolean;
  assessment: NonNullable<EptPublicInterestGate["legal_assessment"]>;
  publication_performed: false;
};

export type EptExactIdentityLinkResult = {
  created: boolean;
  identity_link: NonNullable<EptPublicInterestGate["identity_link"]>;
  publication_performed: false;
  raw_identifier_persisted: false;
};

export type EptPublicInterestPublicationResult = {
  created: true;
  case_id: string;
  state: "PUBLISHED";
  revision: number;
  declaration_id: string;
  decision_sha256: string;
  event_sha256: string;
  publication_review_id: string;
  audit_event_id: string;
  publication_proof_sha256: string;
  automatic_publication: false;
};

export type EptPublicInterestWithdrawalPreview = {
  case_id: string;
  case_state: "PUBLISHED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  declaration_id: string;
  source_sha256: string;
  publication_proof_sha256: string;
  withdrawal_proof_sha256: string;
  public_review_id: string;
  publication_audit_event_id: string;
  publication_event_id: string;
  publication_event_sha256: string;
  public_effect: {
    kind: "DECLARATION_METADATA_HIDDEN_HISTORY_PRESERVED";
    declaration_reference_sha256: string;
    active_public_metadata_after_withdrawal: false;
    declaration_row_preserved: true;
    identity_link_preserved_private: true;
    legal_assessment_preserved_private: true;
    message: string;
  };
  public_effect_sha256: string;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_withdrawal: false;
  withdrawal_rule: string;
};

export type EptPublicInterestWithdrawalResult = {
  created: true;
  case_id: string;
  state: "WITHDRAWN";
  revision: number;
  declaration_id: string;
  reason_category: ParliamentWithdrawalReason;
  decision_sha256: string;
  event_sha256: string;
  publication_review_id: string;
  audit_event_id: string;
  public_effect: EptPublicInterestWithdrawalPreview["public_effect"];
  public_effect_sha256: string;
};

export type PoliticianMandateEditorialCandidate = {
  subject_id: string;
  source_period_ordinal: number;
  observation_id: string;
  source_document_id: string;
  snapshot_id: string;
  official_deputy_id: string;
  parliamentary_name: string;
  full_name: string | null;
  legislature: string;
  constituency: { source_id: string | null; label: string | null };
  source_period: {
    description: string;
    starts_at: string | null;
    ends_at: string | null;
  };
  source_period_sha256: string;
  snapshot: PoliticianProfileEditorialCandidate["snapshot"];
  source: PoliticianProfileEditorialCandidate["source"];
  archive: PoliticianProfileEditorialCandidate["archive"];
  manifest_counts: PoliticianProfileEditorialCandidate["manifest_counts"];
  materialised_counts: PoliticianProfileEditorialCandidate["materialised_counts"];
  identity_publication_ready: boolean;
  existing_case: PoliticianProfileEditorialCandidate["editorial_case"];
  blocked_reasons: string[];
  warnings: string[];
  proposal_eligible: boolean;
  public_projection_allowed: false;
  party_inference_allowed: false;
};

export type PoliticianMandateEditorialCandidateList = {
  items: PoliticianMandateEditorialCandidate[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  publication_performed: false;
  search_rule: string;
};

export type PoliticianMandateEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
  mandate_created: false;
  public_review_created: false;
  party_link_created: false;
};

export type PoliticianOfficeEditorialCandidate = {
  subject_id: string;
  source_period_ordinal: number;
  observation_id: string;
  source_document_id: string;
  snapshot_id: string;
  official_deputy_id: string;
  parliamentary_name: string;
  full_name: string | null;
  legislature: string;
  constituency: { source_id: string | null; label: string | null };
  source_office: {
    source_id: string | null;
    title: string;
    starts_at: string | null;
    ends_at: string | null;
  };
  source_period_sha256: string;
  snapshot: PoliticianProfileEditorialCandidate["snapshot"];
  source: PoliticianProfileEditorialCandidate["source"];
  archive: PoliticianProfileEditorialCandidate["archive"];
  manifest_counts: PoliticianProfileEditorialCandidate["manifest_counts"];
  materialised_counts: PoliticianProfileEditorialCandidate["materialised_counts"];
  identity_publication_ready: boolean;
  existing_case: PoliticianProfileEditorialCandidate["editorial_case"];
  blocked_reasons: string[];
  warnings: string[];
  proposal_eligible: boolean;
  public_projection_allowed: false;
  mandate_inference_allowed: false;
  party_inference_allowed: false;
};

export type PoliticianOfficeEditorialCandidateList = {
  items: PoliticianOfficeEditorialCandidate[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  publication_performed: false;
  search_rule: string;
};

export type PoliticianOfficeEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
  office_created: false;
  mandate_created: false;
  public_review_created: false;
  party_link_created: false;
};

export type PoliticianAttendanceCounts = {
  records: number;
  present: number;
  justified_absence: number;
  unjustified_absence: number;
  unknown: number;
};

export type PoliticianAttendanceEditorialCandidate = {
  snapshot_id: string;
  source_document_id: string;
  legislature: string;
  official_meeting_id: string;
  meeting_date: string;
  meeting_type: string;
  session_number: string | null;
  parser_version: string;
  normalised_sha256: string;
  collected_at: string;
  record_count: number;
  manifest_counts: PoliticianAttendanceCounts;
  materialised_counts: PoliticianAttendanceCounts;
  identity_reconciliation: {
    exact_identities: number;
    reviewed_identities: number;
    exact_covering_mandates: number;
    reviewed_covering_mandates: number;
  };
  source: ParliamentEditorialSnapshot["source"];
  archive: ParliamentEditorialSnapshot["archive"];
  existing_case: PoliticianProfileEditorialCandidate["editorial_case"];
  blocked_reasons: string[];
  warnings: string[];
  proposal_eligible: boolean;
  publication_blockers: string[];
  publication_ready: boolean;
  public_projection_allowed: false;
  selective_processing_allowed: false;
  name_matching_allowed: false;
};

export type PoliticianAttendanceEditorialCandidateList = {
  items: PoliticianAttendanceEditorialCandidate[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  publication_performed: false;
  selection_rule: string;
};

export type PoliticianAttendanceEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
  session_created: false;
  attendance_records_created: 0;
  public_reviews_created: 0;
  selective_processing_allowed: false;
};

export type PoliticianInitiativeAuthorshipCounts = {
  initiatives: number;
  authorships: number;
  deputies: number;
};

export type PoliticianInitiativeAuthorshipEditorialCandidate = {
  observation_id: string;
  snapshot_id: string;
  source_document_id: string;
  legislature: string;
  initiative_source_id: string;
  official_deputy_id: string;
  parliamentary_name: string;
  parliamentary_group_label: string | null;
  relation: "AUTHOR";
  source_record_sha256: string;
  snapshot: {
    parser_version: string;
    normalised_sha256: string;
    collected_at: string;
    manifest_counts: PoliticianInitiativeAuthorshipCounts;
    materialised_counts: PoliticianInitiativeAuthorshipCounts;
  };
  initiative: {
    exact_match_count: number;
    id: string | null;
    number: string | null;
    type: string | null;
    title: string | null;
    status: string | null;
    official_url: string | null;
  };
  identity_reconciliation: {
    exact_identity: boolean;
    reviewed_identity: boolean;
    full_name: string | null;
    rule: "EXACT_AR_IDCADASTRO_ONLY";
  };
  source: ParliamentEditorialSnapshot["source"];
  archive: ParliamentEditorialSnapshot["archive"];
  existing_case: PoliticianProfileEditorialCandidate["editorial_case"];
  blocked_reasons: string[];
  warnings: string[];
  proposal_eligible: boolean;
  publication_blockers: string[];
  publication_ready: boolean;
  public_projection_allowed: false;
  name_matching_allowed: false;
  party_matching_allowed: false;
  collective_position_inference_allowed: false;
};

export type PoliticianInitiativeAuthorshipEditorialCandidateList = {
  items: PoliticianInitiativeAuthorshipEditorialCandidate[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  publication_performed: false;
  search_rule: string;
};

export type PoliticianInitiativeAuthorshipEditorialProposalResult = {
  created: boolean;
  case: EditorialCaseDetail;
  state: "PRIVATE_PENDING_REVIEW";
  publication_performed: false;
  initiative_authorship_created: false;
  people_created: 0;
  party_links_created: 0;
  public_reviews_created: 0;
  name_matching_allowed: false;
};

export type PoliticianInitiativeAuthorshipPublicationPreview = {
  case_id: string;
  case_state: "APPROVED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  source_record_sha256: string;
  source: PoliticianInitiativeAuthorshipEditorialCandidate["source"];
  archive: PoliticianInitiativeAuthorshipEditorialCandidate["archive"];
  authorship: {
    observation_reference_sha256: string;
    official_deputy_id: string;
    initiative_source_id: string;
    parliamentary_name: string;
    relation: "AUTHOR";
  };
  identity: {
    person_reference_sha256: string;
    exact_match: true;
    reviewed: boolean;
  } | null;
  initiative: {
    initiative_reference_sha256: string;
    number: string;
    type: string;
    title: string;
    status: string | null;
    introduced_at: string | null;
    official_url: string;
    activity_snapshot_sha256: string;
    activity_source: {
      url: string;
      retrieved_at: string;
      content_sha256: string;
    };
  } | null;
  public_effect: {
    authorships_to_create: 1;
    authorship_reviews_to_append: 1;
    authorship_audits_to_append: 1;
    editorial_decisions_to_append: 1;
    publication_events_to_append: 1;
    people_to_create: 0;
    initiatives_to_create: 0;
    party_links_to_create: 0;
  };
  publication_proof_sha256: string | null;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_publication: false;
  human_review_required: true;
  name_matching_allowed: false;
  party_matching_allowed: false;
  collective_position_inference_allowed: false;
  withdrawal_required_before_real_activation: true;
  publication_rule: string;
};

export type PoliticianInitiativeAuthorshipPublicationResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "PUBLISHED";
  authorship_id: string;
  authorship_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  publication_event_id: string;
  source_sha256: string;
  source_record_sha256: string;
  activity_snapshot_sha256: string;
  publication_proof_sha256: string;
  people_created: 0;
  initiatives_created: 0;
  party_links_created: 0;
  automatic_publication: false;
  publication_rule: string;
};

export type PoliticianInitiativeAuthorshipPublicEffect = {
  kind: "INITIATIVE_AUTHORSHIP_HIDDEN_HISTORY_PRESERVED";
  authorship_reference_sha256: string;
  identity_publication_review_unchanged: boolean;
  initiative_publication_review_unchanged: boolean;
  exact_authorship_public_after_withdrawal: false;
  remaining_public_authorships_for_person: number;
  authorship_row_preserved: true;
  message: string;
};

export type PoliticianInitiativeAuthorshipWithdrawalPreview = {
  case_id: string;
  case_state: "PUBLISHED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  authorship_id: string;
  source: PoliticianInitiativeAuthorshipEditorialCandidate["source"];
  source_record_sha256: string;
  activity_snapshot_sha256: string;
  publication_proof_sha256: string;
  withdrawal_proof_sha256: string | null;
  public_review_id: string;
  publication_audit_event_id: string;
  publication_event_id: string;
  publication_event_sha256: string;
  public_effect: PoliticianInitiativeAuthorshipPublicEffect;
  public_effect_sha256: string;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_withdrawal: false;
  authorships_to_delete: 0;
  people_to_delete: 0;
  initiatives_to_delete: 0;
  party_links_to_delete: 0;
  withdrawal_rule: string;
};

export type PoliticianInitiativeAuthorshipWithdrawalResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "WITHDRAWN";
  revision: number;
  authorship_id: string;
  reason_category: ParliamentWithdrawalReason;
  authorship_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  withdrawal_event_id: string;
  decision_sha256: string;
  event_sha256: string;
  withdrawal_proof_sha256: string;
  public_effect: PoliticianInitiativeAuthorshipPublicEffect;
  public_effect_sha256: string;
  authorships_deleted: 0;
  people_deleted: 0;
  initiatives_deleted: 0;
  party_links_deleted: 0;
  automatic_withdrawal: false;
  withdrawal_rule: string;
};

export type PoliticianAttendancePublicationPreview = {
  case_id: string;
  case_state: "APPROVED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  snapshot_id: string;
  snapshot_sha256: string;
  source: PoliticianAttendanceEditorialCandidate["source"];
  archive: PoliticianAttendanceEditorialCandidate["archive"];
  meeting: {
    legislature: string;
    official_meeting_id: string;
    date: string;
    type: string;
    session_number: string | null;
  };
  counts: PoliticianAttendanceCounts;
  identity_reconciliation: PoliticianAttendanceEditorialCandidate["identity_reconciliation"];
  mapping_sha256: string | null;
  public_effect: {
    sessions_to_create: 1;
    attendance_records_to_create: number;
    attendance_reviews_to_append: 1;
    attendance_audits_to_append: 1;
    editorial_decisions_to_append: 1;
    publication_events_to_append: 1;
    people_to_create: 0;
    mandates_to_create: 0;
    party_links_to_create: 0;
  };
  publication_proof_sha256: string | null;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_publication: false;
  human_review_required: true;
  selective_processing_allowed: false;
  name_matching_allowed: false;
  absence_is_noncompliance: false;
  withdrawal_required_before_real_activation: true;
  publication_rule: string;
};

export type PoliticianAttendancePublicationResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "PUBLISHED";
  snapshot_id: string;
  session_id: string;
  attendance_record_count: number;
  attendance_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  publication_event_id: string;
  source_sha256: string;
  snapshot_sha256: string;
  mapping_sha256: string;
  publication_proof_sha256: string;
  people_created: 0;
  mandates_created: 0;
  party_links_created: 0;
  automatic_publication: false;
  selective_processing_allowed: false;
  absence_is_noncompliance: false;
  publication_rule: string;
};

export type PoliticianAttendancePublicEffect = {
  kind: "PARLIAMENT_ATTENDANCE_MEETING_HIDDEN_HISTORY_PRESERVED";
  snapshot_reference_sha256: string;
  exact_meeting_public_after_withdrawal: false;
  remaining_public_attendance_meetings_in_legislature: number;
  session_preserved: true;
  attendance_records_preserved: number;
  people_and_mandates_unchanged: true;
  selective_withdrawal: false;
  message: string;
};

export type PoliticianAttendanceWithdrawalPreview = {
  case_id: string;
  case_state: "PUBLISHED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  snapshot_id: string;
  snapshot_sha256: string;
  mapping_sha256: string | null;
  source: PoliticianAttendanceEditorialCandidate["source"];
  publication_proof_sha256: string | null;
  withdrawal_proof_sha256: string | null;
  public_review_id: string;
  publication_audit_event_id: string;
  publication_event_id: string;
  publication_event_sha256: string;
  record_count: number;
  public_effect: PoliticianAttendancePublicEffect;
  public_effect_sha256: string;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_withdrawal: false;
  selective_withdrawal_allowed: false;
  sessions_to_delete: 0;
  attendance_records_to_delete: 0;
  people_to_delete: 0;
  mandates_to_delete: 0;
  absence_is_noncompliance: false;
  withdrawal_rule: string;
};

export type PoliticianAttendanceWithdrawalResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "WITHDRAWN";
  revision: number;
  snapshot_id: string;
  reason_category: ParliamentWithdrawalReason;
  attendance_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  withdrawal_event_id: string;
  decision_sha256: string;
  event_sha256: string;
  withdrawal_proof_sha256: string;
  public_effect: PoliticianAttendancePublicEffect;
  public_effect_sha256: string;
  sessions_deleted: 0;
  attendance_records_deleted: 0;
  people_deleted: 0;
  mandates_deleted: 0;
  automatic_withdrawal: false;
  selective_withdrawal_allowed: false;
  absence_is_noncompliance: false;
  withdrawal_rule: string;
};

export type PoliticianOfficePublicationPreview = {
  case_id: string;
  case_state: "APPROVED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  source_period_sha256: string;
  source: PoliticianOfficeEditorialCandidate["source"];
  archive: PoliticianOfficeEditorialCandidate["archive"];
  proposed_office: {
    official_office_id: string;
    title: string;
    legislature: string;
    constituency_source_id: string;
    constituency: string;
    started_at: string;
    ended_at: string | null;
  };
  identity: {
    parliamentary_name: string;
    official_deputy_id: string;
    person_reference_sha256: string;
    exact_match: true;
  };
  source_observation_reference_sha256: string;
  source_period_ordinal: number;
  public_effect: {
    offices_to_create: 1;
    office_reviews_to_append: 1;
    office_audits_to_append: 1;
    editorial_decisions_to_append: 1;
    publication_events_to_append: 1;
    people_to_create: 0;
    mandates_to_create: 0;
    party_links_to_create: 0;
  };
  publication_proof_sha256: string | null;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_publication: false;
  human_review_required: true;
  mandate_inference_allowed: false;
  party_inference_allowed: false;
  withdrawal_required_before_real_activation: true;
  publication_rule: string;
};

export type PoliticianOfficePublicationResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "PUBLISHED";
  office_id: string;
  office_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  publication_event_id: string;
  source_sha256: string;
  source_period_sha256: string;
  publication_proof_sha256: string;
  mandate_created: false;
  party_link_created: false;
  automatic_publication: false;
  publication_rule: string;
};

export type PoliticianOfficePublicEffect = {
  kind: "PARLIAMENT_OFFICE_HIDDEN_HISTORY_PRESERVED";
  office_reference_sha256: string;
  identity_publication_review_unchanged: boolean;
  exact_office_public_after_withdrawal: false;
  remaining_public_offices_for_person: number;
  office_row_preserved: true;
  message: string;
};

export type PoliticianOfficeWithdrawalPreview = {
  case_id: string;
  case_state: "PUBLISHED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  office_id: string;
  source: PoliticianOfficeEditorialCandidate["source"];
  source_period_sha256: string;
  publication_proof_sha256: string;
  withdrawal_proof_sha256: string | null;
  public_review_id: string;
  publication_audit_event_id: string;
  publication_event_id: string;
  publication_event_sha256: string;
  public_effect: PoliticianOfficePublicEffect;
  public_effect_sha256: string;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_withdrawal: false;
  offices_to_delete: 0;
  people_to_delete: 0;
  memberships_to_delete: 0;
  withdrawal_rule: string;
};

export type PoliticianOfficeWithdrawalResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "WITHDRAWN";
  revision: number;
  office_id: string;
  reason_category: ParliamentWithdrawalReason;
  office_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  withdrawal_event_id: string;
  decision_sha256: string;
  event_sha256: string;
  withdrawal_proof_sha256: string;
  public_effect: PoliticianOfficePublicEffect;
  public_effect_sha256: string;
  offices_deleted: 0;
  people_deleted: 0;
  memberships_deleted: 0;
  automatic_withdrawal: false;
  withdrawal_rule: string;
};

export type PoliticianMandatePublicationPreview = {
  case_id: string;
  case_state: "APPROVED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  source_period_sha256: string;
  source: PoliticianMandateEditorialCandidate["source"];
  archive: PoliticianMandateEditorialCandidate["archive"];
  proposed_mandate: {
    office_title: string;
    legislature: string;
    constituency: string;
    started_at: string;
    ended_at: string | null;
    party: "dados indisponíveis";
  };
  identity: {
    parliamentary_name: string;
    official_deputy_id: string;
    person_reference_sha256: string;
    exact_match: true;
  };
  source_observation_reference_sha256: string;
  source_period_ordinal: number;
  public_effect: {
    mandates_to_create: 1;
    mandate_reviews_to_append: 1;
    mandate_audits_to_append: 1;
    editorial_decisions_to_append: 1;
    publication_events_to_append: 1;
    people_to_create: 0;
    party_links_to_create: 0;
  };
  publication_proof_sha256: string | null;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_publication: false;
  human_review_required: true;
  party_inference_allowed: false;
  withdrawal_required_before_real_activation: true;
  publication_rule: string;
};

export type PoliticianMandatePublicationResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "PUBLISHED";
  mandate_id: string;
  mandate_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  publication_event_id: string;
  source_sha256: string;
  source_period_sha256: string;
  publication_proof_sha256: string;
  party_link_created: false;
  automatic_publication: false;
  publication_rule: string;
};

export type PoliticianMandatePublicEffect = {
  kind: "MANDATE_HIDDEN_HISTORY_PRESERVED";
  mandate_reference_sha256: string;
  identity_publication_review_unchanged: boolean;
  exact_mandate_public_after_withdrawal: false;
  remaining_public_mandates_for_person: number;
  mandate_row_preserved: true;
  message: string;
};

export type PoliticianMandateWithdrawalPreview = {
  case_id: string;
  case_state: "PUBLISHED";
  case_revision: number;
  version_id: string;
  version_sha256: string;
  mandate_id: string;
  source: PoliticianMandateEditorialCandidate["source"];
  source_period_sha256: string;
  publication_proof_sha256: string;
  withdrawal_proof_sha256: string | null;
  public_review_id: string;
  publication_audit_event_id: string;
  publication_event_id: string;
  publication_event_sha256: string;
  public_effect: PoliticianMandatePublicEffect;
  public_effect_sha256: string;
  eligible: boolean;
  blockers: Array<{ code: string; detail: string }>;
  automatic_withdrawal: false;
  mandates_to_delete: 0;
  people_to_delete: 0;
  memberships_to_delete: 0;
  withdrawal_rule: string;
};

export type PoliticianMandateWithdrawalResult = {
  created: true;
  case_id: string;
  version_id: string;
  state: "WITHDRAWN";
  revision: number;
  mandate_id: string;
  reason_category: ParliamentWithdrawalReason;
  mandate_review_id: string;
  audit_event_id: string;
  editorial_decision_id: string;
  withdrawal_event_id: string;
  decision_sha256: string;
  event_sha256: string;
  withdrawal_proof_sha256: string;
  public_effect: PoliticianMandatePublicEffect;
  public_effect_sha256: string;
  mandates_deleted: 0;
  people_deleted: 0;
  memberships_deleted: 0;
  automatic_withdrawal: false;
  withdrawal_rule: string;
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
