"""Persistência privada e restrita de observações do registo de interesses EPT."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import asyncpg

from app.core.config import Settings
from app.core.security import (
    hmac_private_reference_identifier,
    is_individual_ept_source_url,
)
from app.models.ept_declaration import EptPublicInterestObservationInput

_SCHEMA_VERSION = "ept-public-interest-observation-v1"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def _db_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.replace(tzinfo=None)


class EptDeclarationStagingRepository:
    """Guarda apenas metadados permitidos; não cria pessoa, revisão ou publicação."""

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self.pool = pool
        self.settings = settings

    async def stage_observation(
        self,
        *,
        payload: EptPublicInterestObservationInput,
        actor_alias: str,
    ) -> dict[str, object]:
        pepper = self.settings.protected_identifier_pepper
        if pepper is None:
            raise ValueError(
                "PROTECTED_IDENTIFIER_PEPPER não configurado; o identificador EPT não "
                "pode ser persistido"
            )
        subject_identifier = payload.official_subject_identifier.get_secret_value().strip()
        subject_digest = hmac_private_reference_identifier(
            subject_identifier,
            pepper.get_secret_value(),
        )

        async with self.pool.acquire() as connection, connection.transaction():
            source = await connection.fetchrow(
                """
                SELECT source.id, source.publisher::text AS publisher,
                       source.kind::text AS kind, source.title,
                       source.official_identifier, source.url,
                       source.retrieved_at, source.content_sha256,
                       archive.id AS archive_id,
                       archive.attestation_sha256
                FROM source_documents AS source
                LEFT JOIN LATERAL (
                    SELECT candidate.id, candidate.attestation_sha256
                    FROM source_archive_attestations AS candidate
                    WHERE candidate.source_document_id = source.id
                      AND candidate.content_sha256 = source.content_sha256
                      AND candidate.retrieval_url = source.url
                      AND candidate.retrieved_at = source.retrieved_at
                    ORDER BY candidate.archived_at ASC, candidate.id ASC
                    LIMIT 1
                ) AS archive ON TRUE
                WHERE source.id = $1
                """,
                payload.source_document_id,
            )
            if source is None:
                raise ValueError("Documento oficial individual não encontrado")
            source_url = str(source["url"])
            if (
                source["publisher"] != "TRANSPARENCY_ENTITY"
                or source["kind"] != "DECLARATION"
                or source["official_identifier"] != payload.official_declaration_id
                or not is_individual_ept_source_url(source_url)
            ):
                raise ValueError(
                    "A observação exige uma prova EPT individual, direta e identificada; "
                    "o portal geral não é uma declaração"
                )
            if source["archive_id"] is None:
                raise ValueError("O documento individual não possui arquivo privado atestado")

            normalized = {
                "schema_version": _SCHEMA_VERSION,
                "official_declaration_id": payload.official_declaration_id,
                "official_subject_digest": subject_digest,
                "public_subject_name": payload.public_subject_name,
                "declaration_type": "INTEREST_REGISTER",
                "declared_at": _iso(payload.declared_at),
                "period_label": payload.period_label,
                "public_access_scope": "PUBLIC_INTEREST_REGISTER",
                "legal_review_status": "REQUIRES_INDEPENDENT_LEGAL_REVIEW",
                "identity_link_status": "UNLINKED_PRIVATE",
                "source_document_id": str(source["id"]),
                "source_content_sha256": str(source["content_sha256"]),
            }
            source_record_sha256 = hashlib.sha256(
                _canonical_json(normalized).encode("utf-8")
            ).hexdigest()
            observation_id = f"ept_interest_{source_record_sha256}"
            inserted = await connection.fetchval(
                """
                INSERT INTO ept_public_interest_observations
                    (id, official_declaration_id, official_subject_digest,
                     public_subject_name, declaration_type, declared_at,
                     period_label, public_access_scope, legal_review_status,
                     identity_link_status, source_document_id,
                     source_record_sha256, observed_at, created_at)
                VALUES ($1, $2, $3, $4, 'INTEREST_REGISTER', $5, $6,
                        'PUBLIC_INTEREST_REGISTER',
                        'REQUIRES_INDEPENDENT_LEGAL_REVIEW', 'UNLINKED_PRIVATE',
                        $7, $8, $9, NOW())
                ON CONFLICT (source_document_id, official_declaration_id) DO NOTHING
                RETURNING TRUE
                """,
                observation_id,
                payload.official_declaration_id,
                subject_digest,
                payload.public_subject_name,
                _db_timestamp(payload.declared_at),
                payload.period_label,
                str(source["id"]),
                source_record_sha256,
                source["retrieved_at"],
            )
            created = bool(inserted)
            if not created:
                existing = await connection.fetchrow(
                    """
                    SELECT id, source_record_sha256
                    FROM ept_public_interest_observations
                    WHERE source_document_id = $1
                      AND official_declaration_id = $2
                    """,
                    str(source["id"]),
                    payload.official_declaration_id,
                )
                if (
                    existing is None
                    or str(existing["source_record_sha256"]) != source_record_sha256
                ):
                    raise ValueError(
                        "Já existe uma observação diferente para a mesma declaração e versão"
                    )
                observation_id = str(existing["id"])
            else:
                audit_after: dict[str, Any] = {
                    "observation_id": observation_id,
                    "source_document_id": str(source["id"]),
                    "source_content_sha256": str(source["content_sha256"]),
                    "source_record_sha256": source_record_sha256,
                    "official_declaration_id": payload.official_declaration_id,
                    "official_subject_digest": subject_digest,
                    "public_access_scope": "PUBLIC_INTEREST_REGISTER",
                    "legal_review_status": "REQUIRES_INDEPENDENT_LEGAL_REVIEW",
                    "identity_link_status": "UNLINKED_PRIVATE",
                    "publication_performed": False,
                }
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, 'EPT_PUBLIC_INTEREST_OBSERVATION', $2,
                            'STAGED_PRIVATE', $3, NULL, $4::jsonb, $5, NOW())
                    """,
                    f"audit_{uuid4().hex}",
                    observation_id,
                    actor_alias,
                    _canonical_json(audit_after),
                    (
                        "Metadados públicos mínimos preservados para revisão privada; "
                        "sem conteúdo patrimonial, ligação de identidade ou publicação."
                    ),
                )

        return {
            "created": created,
            "observation_id": observation_id,
            "source_record_sha256": source_record_sha256,
            "state": "PRIVATE_UNLINKED_REQUIRES_LEGAL_REVIEW",
            "publication_performed": False,
            "person_link_created": False,
            "public_review_created": False,
            "protected_identifier_persisted_in_clear": False,
        }
