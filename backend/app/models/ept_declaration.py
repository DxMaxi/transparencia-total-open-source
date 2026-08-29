"""Contratos privados para metadados públicos do registo de interesses EPT."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.models.editorial import ParliamentWithdrawalReason, validate_normalized_data


class EptPublicInterestObservationInput(BaseModel):
    """Entrada mínima; o identificador do titular é convertido logo para HMAC."""

    model_config = ConfigDict(extra="forbid")

    source_document_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    official_declaration_id: str = Field(min_length=1, max_length=200)
    official_subject_identifier: SecretStr
    public_subject_name: str = Field(min_length=1, max_length=300)
    declared_at: datetime | None = None
    period_label: str | None = Field(default=None, min_length=1, max_length=200)
    confirm_public_interest_register_only: Literal[True]
    confirm_no_income_or_asset_content: Literal[True]
    confirm_no_protected_identifiers_persisted: Literal[True]
    confirm_private_only: Literal[True]

    @field_validator("official_declaration_id", "public_subject_name", "period_label")
    @classmethod
    def strip_public_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("O campo não pode conter apenas espaços")
        return stripped

    @field_validator("official_subject_identifier")
    @classmethod
    def validate_subject_identifier(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("O identificador oficial do titular não pode estar vazio")
        if len(value.get_secret_value().strip()) > 200:
            raise ValueError("O identificador oficial do titular excede 200 caracteres")
        return value

    @field_validator("public_subject_name")
    @classmethod
    def reject_protected_data_in_name(cls, value: str) -> str:
        validate_normalized_data({"public_subject_name": value})
        return value


class EptPublicInterestEditorialProposalRequest(BaseModel):
    """Seleciona uma observação exata para revisão privada, sem ligar a pessoa."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_private_only: Literal[True]
    confirm_public_interest_register_only: Literal[True]
    confirm_no_income_or_asset_content: Literal[True]
    confirm_no_name_matching: Literal[True]
    confirm_identity_unlinked: Literal[True]
    confirm_independent_legal_review_required: Literal[True]


class EptLegalAssessmentOutcome(StrEnum):
    """Conclusão humana documentada; nunca é inferida pelo sistema."""

    PERMITS_PUBLIC_INTEREST_METADATA_ONLY = "PERMITS_PUBLIC_INTEREST_METADATA_ONLY"
    DOES_NOT_PERMIT_PUBLICATION = "DOES_NOT_PERMIT_PUBLICATION"
    REQUIRES_CHANGES = "REQUIRES_CHANGES"


class EptLegalAssessmentRecordRequest(BaseModel):
    """Regista a prova de uma avaliação jurídica independente já realizada."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_revision: int = Field(ge=1)
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_observation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: EptLegalAssessmentOutcome
    assessment_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_document_storage_backend: Literal[
        "BACKBLAZE_B2_ENCRYPTED", "OTHER_ENCRYPTED_PRIVATE"
    ]
    assessment_document_storage_key: SecretStr
    assessment_document_byte_size: int = Field(ge=1, le=50_000_000)
    assessment_document_mime_type: Literal["application/pdf", "application/octet-stream"]
    assessor_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualification_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    conflict_check_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessed_at: datetime
    valid_until: datetime | None = None
    recording_rationale: str = Field(min_length=20, max_length=1000)
    confirm_external_human_assessment: Literal[True]
    confirm_independent_assessor: Literal[True]
    confirm_qualification_and_conflicts_checked: Literal[True]
    confirm_public_interest_metadata_only: Literal[True]
    confirm_document_encrypted_and_private: Literal[True]
    confirm_system_did_not_issue_legal_opinion: Literal[True]

    @field_validator("assessment_document_storage_key", mode="after")
    @classmethod
    def validate_private_storage_key(cls, value: SecretStr) -> SecretStr:
        storage_key = value.get_secret_value().strip()
        if not 1 <= len(storage_key) <= 500:
            raise ValueError("A referência privada do arquivo é inválida")
        return SecretStr(storage_key)

    @field_validator("recording_rationale")
    @classmethod
    def strip_recording_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        validate_normalized_data({"recording_rationale": stripped})
        return stripped

    @model_validator(mode="after")
    def validate_assessment_period(self) -> "EptLegalAssessmentRecordRequest":
        if self.valid_until is not None and self.valid_until <= self.assessed_at:
            raise ValueError("A validade da avaliação tem de terminar depois da sua data")
        return self


class EptExactIdentityLinkRequest(BaseModel):
    """Liga uma pessoa apenas pelo identificador oficial exato convertido para HMAC."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_revision: int = Field(ge=1)
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_observation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    official_subject_identifier: SecretStr
    person_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_person_source_id: str = Field(min_length=1, max_length=200)
    identity_evidence_document_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_identity_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recording_rationale: str = Field(min_length=20, max_length=1000)
    confirm_exact_official_identifier: Literal[True]
    confirm_second_official_source_reviewed: Literal[True]
    confirm_no_name_or_fuzzy_matching: Literal[True]
    confirm_identifier_will_only_persist_as_hmac: Literal[True]
    confirm_same_person: Literal[True]

    @field_validator("official_subject_identifier")
    @classmethod
    def validate_subject_identifier(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip()
        if not 1 <= len(raw) <= 200:
            raise ValueError("O identificador oficial do titular é inválido")
        return SecretStr(raw)

    @field_validator("expected_person_source_id")
    @classmethod
    def strip_person_source_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("O campo não pode conter apenas espaços")
        validate_normalized_data({"value": stripped})
        return stripped

    @field_validator("recording_rationale")
    @classmethod
    def strip_identity_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        validate_normalized_data({"recording_rationale": stripped})
        return stripped


class EptPublicInterestPublicationRequest(BaseModel):
    """Confirma a publicação dos metadados mínimos reconstruídos no servidor."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_revision: int = Field(ge=1)
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_observation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_declaration_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_person_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_identity_link_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_identity_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_legal_assessment_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_legal_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_legal_assessment_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=20, max_length=1850)
    public_rationale: str = Field(min_length=20, max_length=500)
    confirm_source_and_archive_reviewed: Literal[True]
    confirm_exact_identity_link_reviewed: Literal[True]
    confirm_independent_legal_assessment_reviewed: Literal[True]
    confirm_public_interest_metadata_only: Literal[True]
    confirm_no_income_asset_or_protected_identifier: Literal[True]
    confirm_append_only_publication: Literal[True]
    confirm_publication: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_publication_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        validate_normalized_data({"rationale": stripped})
        return stripped


class EptPublicInterestWithdrawalRequest(BaseModel):
    """Retira a projeção ativa e conserva toda a prova e decisões anteriores."""

    model_config = ConfigDict(extra="forbid")

    expected_case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_revision: int = Field(ge=1)
    expected_version_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_declaration_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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
    confirm_public_effect_reviewed: Literal[True]
    confirm_declaration_and_history_preserved: Literal[True]
    confirm_identity_and_legal_records_preserved: Literal[True]
    confirm_withdrawal: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def strip_withdrawal_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        validate_normalized_data({"rationale": stripped})
        return stripped
