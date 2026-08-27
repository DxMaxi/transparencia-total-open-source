"""Contratos privados do painel de revisão editorial V5."""

import json
import re
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PROTECTED_IDENTIFIER_SEQUENCE = re.compile(r"(?<!\d)\d(?:[\W_]*\d){8}(?!\d)")
_PROTECTED_KEY = re.compile(r"(^|_)(nif|nipc|tax_id|vat)($|_)", re.IGNORECASE)
_SAFE_DIGEST_KEY = re.compile(r"(digest|hmac|sha256)$", re.IGNORECASE)
_MAX_NORMALIZED_BYTES = 256_000
_MAX_JSON_DEPTH = 12


class StaffRole(StrEnum):
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"


class EditorialCaseKind(StrEnum):
    PARLIAMENT_ACTIVITY = "PARLIAMENT_ACTIVITY"
    PARLIAMENT_VOTE = "PARLIAMENT_VOTE"
    POLITICIAN_PROFILE = "POLITICIAN_PROFILE"
    GOVERNMENT_PROMISE = "GOVERNMENT_PROMISE"
    PUBLIC_CONTRACT = "PUBLIC_CONTRACT"
    INTEREST_RELATIONSHIP = "INTEREST_RELATIONSHIP"
    RIGHT_OF_REPLY = "RIGHT_OF_REPLY"
    AI_EXPLANATION = "AI_EXPLANATION"
    OTHER = "OTHER"


class EditorialState(StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class EditorialAction(StrEnum):
    SUBMIT = "SUBMIT"
    START_REVIEW = "START_REVIEW"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CORRECT = "CORRECT"
    PUBLISH = "PUBLISH"
    WITHDRAW = "WITHDRAW"


class EditorialOrigin(StrEnum):
    HUMAN = "HUMAN"
    INGESTION = "INGESTION"
    AI = "AI"


class ParliamentEditorialScope(StrEnum):
    ACTIVITY = "activity"
    VOTES = "votes"


class ParliamentWithdrawalReason(StrEnum):
    """Categorias públicas fechadas previstas na governação anti-interferência."""

    EXTRACTION_OR_NORMALISATION_ERROR = "EXTRACTION_OR_NORMALISATION_ERROR"
    SOURCE_DIVERGENCE = "SOURCE_DIVERGENCE"
    OFFICIAL_SOURCE_CORRECTION = "OFFICIAL_SOURCE_CORRECTION"
    DUPLICATE_OR_CORRUPT_DATA = "DUPLICATE_OR_CORRUPT_DATA"
    PROVEN_IDENTITY_ERROR = "PROVEN_IDENTITY_ERROR"
    DOCUMENTED_METHODOLOGY_CHANGE = "DOCUMENTED_METHODOLOGY_CHANGE"
    LEGAL_OR_AUTHORITY_ORDER = "LEGAL_OR_AUTHORITY_ORDER"
    DATA_PROTECTION_OR_PERSONALITY_RIGHTS = "DATA_PROTECTION_OR_PERSONALITY_RIGHTS"
    SECURITY_RISK = "SECURITY_RISK"
    THIRD_PARTY_RIGHTS = "THIRD_PARTY_RIGHTS"
    DECLARED_SCOPE_ERROR = "DECLARED_SCOPE_ERROR"


class StaffSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    staff_id: str
    auth_user_id: UUID
    public_alias: str
    role: StaffRole
    assurance_level: Literal["aal1", "aal2"]
    mfa_required: bool


def _check_normalized_value(value: Any, *, key: str | None = None, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("Os dados normalizados excedem a profundidade permitida")
    if isinstance(value, dict):
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str) or not nested_key.strip():
                raise ValueError("Todas as chaves normalizadas têm de ser texto não vazio")
            canonical_key = re.sub(r"[^a-z0-9]", "", nested_key.casefold())
            protected_key = _PROTECTED_KEY.search(nested_key) or canonical_key in {
                "nif",
                "nipc",
                "taxid",
                "vat",
                "numerocontribuinte",
                "identificadorfiscal",
            }
            if protected_key and not _SAFE_DIGEST_KEY.search(nested_key):
                raise ValueError("NIF/NIPC só pode existir como digest HMAC identificado")
            _check_normalized_value(nested_value, key=nested_key, depth=depth + 1)
        return
    if isinstance(value, list):
        for nested_value in value:
            _check_normalized_value(nested_value, key=key, depth=depth + 1)
        return
    if isinstance(value, str):
        if _SAFE_DIGEST_KEY.search(key or ""):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("Um digest protegido tem de ser SHA-256 hexadecimal")
            return
        if _PROTECTED_IDENTIFIER_SEQUENCE.search(value):
            raise ValueError("Os dados normalizados não podem conter NIF/NIPC em claro")
    elif (
        (isinstance(value, int) and not isinstance(value, bool))
        or (isinstance(value, float) and value.is_integer())
    ) and 100_000_000 <= abs(value) <= 999_999_999:
        raise ValueError("Os dados normalizados não podem conter NIF/NIPC em claro")


def validate_normalized_data(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        raise ValueError("Os dados normalizados não podem estar vazios")
    _check_normalized_value(value)
    try:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Os dados normalizados não são JSON válido") from exc
    if len(canonical) > _MAX_NORMALIZED_BYTES:
        raise ValueError("Os dados normalizados excedem 256 kB")
    return value


class EditorialCaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EditorialCaseKind
    subject_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    subject_id: str = Field(min_length=1, max_length=200)
    source_document_id: str = Field(min_length=1, max_length=200)
    normalized_data: dict[str, Any]
    confirm_private_only: Literal[True]

    @field_validator("subject_id", "source_document_id")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("O identificador não pode conter apenas espaços")
        return stripped

    @field_validator("normalized_data")
    @classmethod
    def validate_normalized_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_normalized_data(value)


class EditorialDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    rationale: str = Field(min_length=20, max_length=2000)

    @field_validator("rationale")
    @classmethod
    def strip_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        return stripped


class EditorialApprovalRequest(EditorialDecisionRequest):
    confirm_source_reviewed: Literal[True]


class EditorialCorrectionRequest(EditorialDecisionRequest):
    normalized_data: dict[str, Any]

    @field_validator("normalized_data")
    @classmethod
    def validate_normalized_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_normalized_data(value)


class ParliamentEditorialProposalRequest(BaseModel):
    """Pedido mínimo: os dados da proposta são reconstruídos no servidor."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    scope: ParliamentEditorialScope
    confirm_private_only: Literal[True]
    confirm_no_individual_inference: Literal[True]


class PoliticianProfileEditorialProposalRequest(BaseModel):
    """Confirmações para importar uma observação oficial para revisão privada."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    confirm_private_only: Literal[True]
    confirm_exact_official_id_only: Literal[True]
    confirm_no_mandate_inference: Literal[True]


class PoliticianMandateEditorialProposalRequest(BaseModel):
    """Seleciona um intervalo oficial exato para revisão privada de mandato."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,180}$")
    source_period_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_private_only: Literal[True]
    confirm_exact_official_id_only: Literal[True]
    confirm_period_semantics_require_human_review: Literal[True]
    confirm_no_party_inference: Literal[True]


class PoliticianOfficeEditorialProposalRequest(BaseModel):
    """Seleciona um cargo parlamentar oficial exato para revisão privada."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,180}$")
    source_period_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_private_only: Literal[True]
    confirm_exact_official_ids_only: Literal[True]
    confirm_observed_period_requires_human_review: Literal[True]
    confirm_no_mandate_or_party_inference: Literal[True]


class PoliticianAttendanceEditorialProposalRequest(BaseModel):
    """Seleciona uma reunião oficial completa para revisão privada."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    confirm_private_only: Literal[True]
    confirm_complete_meeting: Literal[True]
    confirm_exact_official_ids_only: Literal[True]
    confirm_no_name_matching: Literal[True]
    confirm_absence_is_not_noncompliance: Literal[True]
    confirm_no_selective_processing: Literal[True]


class PoliticianOfficePublicationRequest(BaseModel):
    """Confirma a publicação de um cargo reconstruído integralmente no servidor."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_period_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    confirm_source_reviewed: Literal[True]
    confirm_human_office_interpretation: Literal[True]
    confirm_exact_official_ids_only: Literal[True]
    confirm_no_mandate_or_party_inference: Literal[True]
    confirm_append_only_publication: Literal[True]
    confirm_publication: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_office_publication_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        return stripped


class PoliticianOfficeWithdrawalRequest(BaseModel):
    """Retira um cargo exato sem alterar a linha nem a publicação original."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_revision: int = Field(ge=1)
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_office_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_period_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_withdrawal_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_review_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_audit_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_effect_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    reason_category: ParliamentWithdrawalReason
    confirm_source_and_publication_reviewed: Literal[True]
    confirm_exact_office: Literal[True]
    confirm_public_effect_reviewed: Literal[True]
    confirm_office_and_history_preserved: Literal[True]
    confirm_no_selective_identity_or_mandate_change: Literal[True]
    confirm_withdrawal: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_office_withdrawal_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        return stripped


class PoliticianMandatePublicationRequest(BaseModel):
    """Confirma uma publicação de mandato reconstruída integralmente no servidor."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_period_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    confirm_source_reviewed: Literal[True]
    confirm_human_period_interpretation: Literal[True]
    confirm_exact_official_id_only: Literal[True]
    confirm_no_party_inference: Literal[True]
    confirm_append_only_publication: Literal[True]
    confirm_publication: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_mandate_publication_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        return stripped


class PoliticianMandateWithdrawalRequest(BaseModel):
    """Retira um mandato exato sem alterar a linha nem a publicação original."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_revision: int = Field(ge=1)
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_mandate_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_period_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_withdrawal_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_review_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_audit_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_effect_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    reason_category: ParliamentWithdrawalReason
    confirm_source_and_publication_reviewed: Literal[True]
    confirm_exact_mandate: Literal[True]
    confirm_public_effect_reviewed: Literal[True]
    confirm_mandate_and_history_preserved: Literal[True]
    confirm_no_selective_identity_change: Literal[True]
    confirm_withdrawal: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_mandate_withdrawal_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        return stripped


class PoliticianProfileSnapshotPublicationRequest(BaseModel):
    """Confirma a publicação integral de uma fotografia já pronta e novamente provada."""

    model_config = ConfigDict(extra="forbid")

    expected_snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_readiness_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_deputy_count: int = Field(ge=1, le=500)
    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    confirm_source_reviewed: Literal[True]
    confirm_complete_snapshot: Literal[True]
    confirm_exact_official_id_only: Literal[True]
    confirm_no_mandate_inference: Literal[True]
    confirm_no_party_inference: Literal[True]
    confirm_publication: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_profile_publication_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        return stripped


class PoliticianProfileSnapshotWithdrawalRequest(BaseModel):
    """Retirada integral ligada à prova exata da fotografia publicada."""

    model_config = ConfigDict(extra="forbid")

    expected_snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_withdrawal_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_effect_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_deputy_count: int = Field(ge=1, le=500)
    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    reason_category: ParliamentWithdrawalReason
    confirm_complete_snapshot: Literal[True]
    confirm_no_selective_removal: Literal[True]
    confirm_public_effect_reviewed: Literal[True]
    confirm_people_and_history_preserved: Literal[True]
    confirm_withdrawal: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_profile_withdrawal_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        return stripped


class AiDreProposalRequest(BaseModel):
    """Confirmações explícitas para uma geração privada baseada num snapshot DRE."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    confirm_private_only: Literal[True]
    confirm_archived_source_only: Literal[True]
    confirm_ai_not_source: Literal[True]


class AiDreRegenerationRequest(EditorialDecisionRequest):
    """Nova versão de IA ligada à versão e à prova que o revisor viu."""

    expected_current_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_private_only: Literal[True]
    confirm_archived_source_only: Literal[True]
    confirm_ai_not_source: Literal[True]
    confirm_new_immutable_version: Literal[True]


class AiEditorialPublicationRequest(EditorialDecisionRequest):
    """Publicação explícita da versão DRE de IA que o administrador confirmou."""

    public_rationale: str = Field(min_length=20, max_length=500)
    expected_public_id: str = Field(pattern=r"^dre-[0-9a-f]{64}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_normalised_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_editorial_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_source_reviewed: Literal[True]
    confirm_ai_label_reviewed: Literal[True]
    confirm_no_prediction_or_recommendation: Literal[True]
    confirm_publication: Literal[True]

    @field_validator("public_rationale")
    @classmethod
    def strip_ai_public_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("O resumo público deve ter pelo menos 20 caracteres úteis")
        return stripped


class AiEditorialWithdrawalRequest(EditorialDecisionRequest):
    """Retirada explícita ligada à projeção e aos eventos publicados exatos."""

    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    reason_category: ParliamentWithdrawalReason
    expected_public_id: str = Field(pattern=r"^dre-[0-9a-f]{64}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_normalised_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_editorial_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_review_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_audit_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_effect_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_no_selective_removal: Literal[True]
    confirm_public_effect_reviewed: Literal[True]
    confirm_withdrawal: Literal[True]

    @field_validator("public_rationale")
    @classmethod
    def strip_ai_withdrawal_public_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("O resumo público deve ter pelo menos 20 caracteres úteis")
        return stripped


class ParliamentEditorialPublicationRequest(EditorialDecisionRequest):
    """Confirmação explícita de uma publicação parlamentar já aprovada."""

    confirmed_scope: ParliamentEditorialScope
    expected_snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_editorial_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_source_reviewed: Literal[True]
    confirm_no_individual_inference: Literal[True]
    confirm_publication: Literal[True]


class ParliamentEditorialWithdrawalRequest(EditorialDecisionRequest):
    """Retirada explícita, não seletiva e ligada à prova publicada exata."""

    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    reason_category: ParliamentWithdrawalReason
    confirmed_scope: ParliamentEditorialScope
    expected_snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_editorial_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_review_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_audit_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_publication_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_public_effect_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_no_selective_removal: Literal[True]
    confirm_public_effect_reviewed: Literal[True]
    confirm_withdrawal: Literal[True]

    @field_validator("public_rationale")
    @classmethod
    def strip_public_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("O resumo público deve ter pelo menos 20 caracteres úteis")
        return stripped
