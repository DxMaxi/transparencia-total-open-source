"""Prova mínima IRN: hashes externos nunca dependem do HMAC de identidade."""

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.security import is_individual_organisation_registry_source_url
from app.models.base_organisation import safe_registry_record_id, safe_registry_text

PARSER_VERSION = "base-organisation-registry-v1"
POLICY_VERSION = "base-organisation-identity-v1"
PROPOSAL_SCHEMA = "base-organisation-identity-editorial-v1"
SUBJECT_TYPE = "BASE_ORGANISATION_IDENTITY_OBSERVATION"
ALLOWED_KINDS = {"PUBLIC_BODY", "COMPANY", "NON_PROFIT", "EUROPEAN_BODY", "OTHER"}


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def source_proof(row: Mapping[str, Any], registry_record_id: str) -> dict[str, object]:
    """Valida antes de devolver texto; dados da fonte alterados não chegam ao cliente."""

    if (
        row["source_publisher"] != "JUSTICE_REGISTRY"
        or row["source_kind"] != "ORGANISATION_REGISTRY"
        or row["source_official_identifier"] != registry_record_id
        or not is_individual_organisation_registry_source_url(str(row["source_url"]))
        or not isinstance(row["source_retrieved_at"], datetime)
        or not re.fullmatch(r"[0-9a-f]{64}", str(row["source_sha256"]))
    ):
        raise ValueError("A identidade exige uma fonte individual independente do registo IRN")
    safe_registry_record_id(registry_record_id)
    title = safe_registry_text(str(row["source_title"]), max_length=1000)
    mime = str(row["source_mime_type"])
    if mime not in {"text/html", "application/pdf", "application/xhtml+xml"}:
        raise ValueError("O tipo de documento de registo não está autorizado")
    return {
        "title": title,
        "publisher": "IRN",
        "official_identifier": registry_record_id,
        "url": str(row["source_url"]),
        "retrieved_at": iso(row["source_retrieved_at"]),
        "content_sha256": str(row["source_sha256"]),
        "mime_type": mime,
    }


def source_record(
    *,
    source_document_id: str,
    registry_record_id: str,
    legal_name: str,
    kind: str,
    source: Mapping[str, object],
) -> dict[str, object]:
    if kind not in ALLOWED_KINDS:
        raise ValueError("A observação não representa uma organização autorizada")
    return {
        "schema_version": "base-organisation-source-record-v1",
        "source_document_id": safe_registry_text(source_document_id, max_length=200),
        "registry_record_id": safe_registry_record_id(registry_record_id),
        "legal_name": safe_registry_text(legal_name),
        "kind": kind,
        "source": dict(source),
        "parser_version": PARSER_VERSION,
        "policy_version": POLICY_VERSION,
    }


def observation_sha256(source_record_sha256: str, protected_identifier_digest: str) -> str:
    """Prova interna; esta função nunca fornece dados a APIs, auditoria ou JSON editorial."""

    return sha256(
        {
            "schema_version": "base-organisation-private-observation-v1",
            "source_record_sha256": source_record_sha256,
            "protected_identifier_digest": protected_identifier_digest,
            "policy_version": POLICY_VERSION,
        }
    )


def proposal_confirmation_sha256(
    *,
    observation_id: str,
    source_document_id: str,
    source_content_sha256: str,
    source_record_sha256: str,
    archive_attestation_sha256: str | None,
) -> str:
    return sha256(
        {
            "schema_version": "base-organisation-private-proposal-confirmation-v1",
            "action": "SUBMIT_PRIVATE_IDENTITY_ONLY",
            "observation_id": observation_id,
            "source_document_id": source_document_id,
            "source_content_sha256": source_content_sha256,
            "source_record_sha256": source_record_sha256,
            "archive_attestation_sha256": archive_attestation_sha256,
            "policy_version": POLICY_VERSION,
        }
    )
