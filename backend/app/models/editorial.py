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
