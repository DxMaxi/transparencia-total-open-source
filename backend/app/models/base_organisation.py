"""Entradas fechadas para identidade organizacional independente, apenas privada."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models.editorial import ParliamentWithdrawalReason

OrganisationIdentityKind = Literal["PUBLIC_BODY", "COMPANY", "NON_PROFIT", "EUROPEAN_BODY", "OTHER"]
_FISCAL_SEQUENCE = re.compile(r"\d(?:[\W_]*\d){8}")
_DIGEST = re.compile(r"[0-9a-fA-F]{64}")
_RECORD = re.compile(r"^[A-Za-z][A-Za-z0-9._:/-]{2,199}$")


def safe_registry_text(value: str, *, max_length: int = 300) -> str:
    """Recusa identificadores fiscais, inclusive embebidos, separados ou Unicode."""

    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        not 1 <= len(normalized) <= max_length
        or _FISCAL_SEQUENCE.search(normalized)
        or _DIGEST.search(re.sub(r"[\W_]+", "", normalized))
        or any(unicodedata.category(char).startswith("C") for char in normalized)
    ):
        raise ValueError("O texto de registo não respeita o âmbito mínimo e privado")
    return normalized


def safe_registry_record_id(value: str) -> str:
    normalized = safe_registry_text(value, max_length=200)
    if not _RECORD.fullmatch(normalized):
        raise ValueError("É necessária uma referência oficial de ato, não fiscal")
    return normalized


def canonical_fiscal_identifier(value: SecretStr) -> str:
    """Aceita nove algarismos, com espaços ou hífen; nunca ignora letras."""

    normalized = unicodedata.normalize("NFKC", value.get_secret_value()).strip()
    if not re.fullmatch(r"\d(?:[ -]*\d){8}", normalized):
        raise ValueError("O identificador fiscal protegido tem um formato inválido")
    return "".join(str(unicodedata.decimal(char)) for char in normalized if char.isdecimal())


class BaseOrganisationIdentityObservationInput(BaseModel):
    """Exclusivo do processo CLI; não é um contrato HTTP ou um payload editorial."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)

    source_document_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    registry_record_id: str = Field(min_length=3, max_length=200)
    legal_name: str = Field(min_length=1, max_length=300)
    kind: OrganisationIdentityKind
    fiscal_identifier: SecretStr = Field(exclude=True, repr=False)
    confirm_independent_official_source: Literal[True]
    confirm_identifier_hmac_only: Literal[True]
    confirm_private_identity_only: Literal[True]
    confirm_no_publication: Literal[True]

    @field_validator("source_document_id", "legal_name")
    @classmethod
    def validate_safe_text(cls, value: str) -> str:
        return safe_registry_text(value)

    @field_validator("registry_record_id")
    @classmethod
    def validate_record_reference(cls, value: str) -> str:
        return safe_registry_record_id(value)

    @field_validator("fiscal_identifier")
    @classmethod
    def validate_private_identifier(cls, value: SecretStr) -> SecretStr:
        return SecretStr(canonical_fiscal_identifier(value))


class BaseOrganisationIdentityEditorialProposalRequest(BaseModel):
    """O navegador seleciona prova exata; nunca envia nomes ou identificadores fiscais."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    observation_id: str = Field(pattern=r"^base_org_identity_[0-9a-f]{32}$")
    source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_confirmation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_independent_official_source: Literal[True]
    confirm_private_identity_only: Literal[True]
    confirm_no_publication: Literal[True]


class OrganisationProofRequest(BaseModel):
    """Referências fechadas; o servidor reconstrói todos os campos da proposta."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_case_id: str = Field(pattern=r"^editorial_case_[0-9a-f]{32}$")
    expected_version_id: str = Field(pattern=r"^editorial_version_[0-9a-f]{32}$")
    expected_revision: int = Field(ge=0)
    expected_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_identity_remains_private: Literal[True]
    confirm_zero_graph: Literal[True]


class OrganisationPublicationProposalRequest(OrganisationProofRequest):
    confirm_separate_review: Literal[True]
    confirm_no_publication: Literal[True]


class OrganisationPublicationRequest(OrganisationProofRequest):
    rationale: str = Field(min_length=20, max_length=2000)
    public_rationale: str = Field(min_length=20, max_length=1000)
    confirm_official_source: Literal[True]
    confirm_public_interest_and_minimisation: Literal[True]
    confirm_publication: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        normalized = safe_registry_text(value, max_length=2000)
        if len(normalized) < 20:
            raise ValueError("A fundamentação exige pelo menos vinte caracteres úteis")
        return normalized


class OrganisationWithdrawalRequest(OrganisationProofRequest):
    reason: ParliamentWithdrawalReason
    rationale: str = Field(min_length=20, max_length=2000)
    public_rationale: str = Field(min_length=20, max_length=1000)
    confirm_preserve_history_and_replies: Literal[True]
    confirm_withdrawal: Literal[True]

    @field_validator("rationale", "public_rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        normalized = safe_registry_text(value, max_length=2000)
        if len(normalized) < 20:
            raise ValueError("A fundamentação exige pelo menos vinte caracteres úteis")
        return normalized
