"""Contratos privados para metadados públicos do registo de interesses EPT."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models.editorial import validate_normalized_data


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
