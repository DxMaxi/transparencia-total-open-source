"""Observações de identidade independentes; persistência privada sem projeção pública."""

from __future__ import annotations

from uuid import uuid4

import asyncpg

from app.core.config import Settings
from app.core.security import hmac_protected_identifier
from app.models.base_organisation import (
    BaseOrganisationIdentityObservationInput,
    canonical_fiscal_identifier,
    safe_registry_text,
)
from app.services.base_organisation_identity import (
    PARSER_VERSION,
    POLICY_VERSION,
    SUBJECT_TYPE,
    canonical_json,
    observation_sha256,
    sha256,
    source_proof,
    source_record,
)


class BaseOrganisationStagingRepository:
    """Exige pepper duradouro e ambiente staging/test antes de consultar a base."""

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self.pool = pool
        self.settings = settings

    async def stage_observation(
        self,
        *,
        payload: BaseOrganisationIdentityObservationInput,
        actor_alias: str,
    ) -> dict[str, object]:
        if self.settings.environment not in {"staging", "test"}:
            raise ValueError("A identidade organizacional só pode ser recolhida em staging")
        pepper = self.settings.protected_identifier_pepper
        if pepper is None:
            raise ValueError(
                "PROTECTED_IDENTIFIER_PEPPER não configurado; a base não será consultada"
            )
        alias = safe_registry_text(actor_alias, max_length=80)
        if len(alias) < 3:
            raise ValueError("É necessário um pseudónimo interno de operador")
        protected_digest = hmac_protected_identifier(
            canonical_fiscal_identifier(payload.fiscal_identifier), pepper.get_secret_value()
        )
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base-organisation-stage:{payload.source_document_id}:"
                    f"{payload.registry_record_id}",
                )
                source = await connection.fetchrow(
                    """
                    SELECT source.id AS source_document_id,
                           source.publisher::text AS source_publisher,
                           source.kind::text AS source_kind,
                           source.title AS source_title,
                           source.official_identifier AS source_official_identifier,
                           source.url AS source_url,
                           source.retrieved_at AS source_retrieved_at,
                           source.content_sha256 AS source_sha256,
                           source.mime_type AS source_mime_type,
                           archive.attestation_sha256
                    FROM source_documents AS source
                    LEFT JOIN LATERAL (
                        SELECT candidate.attestation_sha256
                        FROM source_archive_attestations AS candidate
                        WHERE candidate.source_document_id = source.id
                          AND candidate.content_sha256 = source.content_sha256
                          AND candidate.retrieval_url = source.url
                          AND candidate.retrieved_at = source.retrieved_at
                        ORDER BY candidate.archived_at, candidate.id
                        LIMIT 1
                    ) AS archive ON TRUE
                    WHERE source.id = $1
                    FOR SHARE OF source
                    """,
                    payload.source_document_id,
                )
                if source is None:
                    raise ValueError("Documento individual de registo não encontrado")
                proof = source_proof(source, payload.registry_record_id)
                if source["attestation_sha256"] is None:
                    raise ValueError("O documento não possui arquivo privado atestado")
                record_hash = sha256(
                    source_record(
                        source_document_id=payload.source_document_id,
                        registry_record_id=payload.registry_record_id,
                        legal_name=payload.legal_name,
                        kind=payload.kind,
                        source=proof,
                    )
                )
                internal_hash = observation_sha256(record_hash, protected_digest)
                observation_id = f"base_org_identity_{uuid4().hex}"
                inserted = await connection.fetchval(
                    """
                    INSERT INTO base_organisation_identity_observations
                        (id, registry_record_id, legal_name, kind, identifier_scheme,
                         protected_identifier_digest, identity_scope, link_status,
                         publication_eligible, source_document_id, source_record_sha256,
                         observation_sha256, observed_at, parser_version, policy_version,
                         created_by_alias, created_at)
                    VALUES ($1, $2, $3, $4::"InterestEntityKind",
                            'PORTUGUESE_FISCAL_IDENTIFIER', $5,
                            'ORGANISATION_IDENTITY_ONLY', 'UNLINKED_PRIVATE',
                            FALSE, $6, $7, $8, $9, $10, $11, $12, NOW())
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    observation_id,
                    payload.registry_record_id,
                    payload.legal_name,
                    payload.kind,
                    protected_digest,
                    payload.source_document_id,
                    record_hash,
                    internal_hash,
                    source["source_retrieved_at"],
                    PARSER_VERSION,
                    POLICY_VERSION,
                    alias,
                )
                created = inserted is not None
                if not created:
                    existing = await connection.fetchrow(
                        """
                        SELECT id, source_record_sha256, observation_sha256
                        FROM base_organisation_identity_observations
                        WHERE source_document_id = $1 AND registry_record_id = $2
                        """,
                        payload.source_document_id,
                        payload.registry_record_id,
                    )
                    if (
                        existing is None
                        or existing["source_record_sha256"] != record_hash
                        or existing["observation_sha256"] != internal_hash
                    ):
                        raise ValueError(
                            "Já existe prova diferente para esta fonte; "
                            "a correção exige uma nova observação e fonte"
                        )
                    observation_id = str(existing["id"])
                else:
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, $2, $3, 'STAGED_PRIVATE', $4, NULL, $5::jsonb, $6, NOW())
                        """,
                        f"audit_{uuid4().hex}",
                        SUBJECT_TYPE,
                        observation_id,
                        alias,
                        canonical_json(
                            {
                                "observation_id": observation_id,
                                "source_document_id": payload.source_document_id,
                                "source_content_sha256": source["source_sha256"],
                                "source_record_sha256": record_hash,
                                "scope": "ORGANISATION_IDENTITY_ONLY",
                                "identity_link_status": "UNLINKED_PRIVATE",
                                "protected_identifier_exposed": False,
                                "publication_performed": False,
                            }
                        ),
                        (
                            "Prova oficial independente preservada apenas para revisão privada. "
                            "Sem criação de organização pública, ligação, correspondência, "
                            "revisão pública ou publicação."
                        ),
                    )
        except asyncpg.PostgresError:
            # PostgreSQL pode incluir valores em DETAIL. Nunca propagar esses detalhes.
            raise ValueError(
                "A persistência privada foi recusada; nenhuma operação foi concluída"
            ) from None
        return {
            "created": created,
            "observation_id": observation_id,
            "source_record_sha256": record_hash,
            "state": "PRIVATE_UNLINKED",
            "publication_performed": False,
            "organisation_created": False,
            "relationship_created": False,
            "protected_identifier_exposed": False,
        }
