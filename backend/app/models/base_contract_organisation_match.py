"""Contrato fechado para criar candidatos privados de correspondência BASE."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.base_organisation import safe_registry_text
from app.models.editorial import validate_normalized_data


class BaseContractOrganisationMatchCandidateRequest(BaseModel):
    """Confirma uma igualdade exata sem expor ou reenviar o HMAC protegido."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_public_contract_id: str = Field(pattern=r"^base_contract_[0-9a-f]{64}$")
    expected_contract_publication_snapshot_id: str = Field(
        pattern=r"^base_contract_publication_[0-9a-f]{32}$"
    )
    expected_contract_party_snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    expected_organisation_id: str = Field(pattern=r"^base_public_org_[0-9a-f]{32}$")
    expected_organisation_publication_snapshot_id: str = Field(
        pattern=r"^base_org_publication_[0-9a-f]{32}$"
    )
    expected_candidate_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=20, max_length=1000)
    confirm_exact_protected_identifier: Literal[True]
    confirm_two_active_publications: Literal[True]
    confirm_independent_official_sources: Literal[True]
    confirm_private_pending_review_only: Literal[True]
    confirm_no_name_or_fuzzy_matching: Literal[True]
    confirm_no_public_party_match_or_relationship: Literal[True]

    @field_validator("rationale")
    @classmethod
    def strip_and_protect_rationale(cls, value: str) -> str:
        stripped = safe_registry_text(value, max_length=1000)
        if len(stripped) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres úteis")
        validate_normalized_data({"rationale": stripped})
        return stripped
