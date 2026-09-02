"""Revisão privada da identidade de organizações baseada em prova IRN independente."""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import asyncpg

from app.models.base_organisation import (
    BaseOrganisationIdentityEditorialProposalRequest,
    safe_registry_text,
)
from app.models.editorial import EditorialCaseKind, StaffSession
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialRepository,
    EditorialSourceError,
)
from app.services.base_organisation_identity import (
    PARSER_VERSION,
    POLICY_VERSION,
    PROPOSAL_SCHEMA,
    SUBJECT_TYPE,
    canonical_json,
    iso,
    observation_sha256,
    proposal_confirmation_sha256,
    sha256,
    source_proof,
    source_record,
)

_REVIEW_CONSTRAINTS: dict[str, object] = {
    "private_only": True,
    "identity_scope": "ORGANISATION_IDENTITY_ONLY",
    "identity_link_status": "UNLINKED_PRIVATE",
    "protected_identifier_observed": True,
    "protected_identifier_exposed": False,
    "name_or_fuzzy_matching_allowed": False,
    "approval_is_not_publication": True,
    "organisation_created": False,
    "interest_entity_created": False,
    "match_review_created": False,
    "relationship_created": False,
    "publication_performed": False,
}


def _validate_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Contrato fechado: nenhum campo HMAC ou observação interna entra no JSON."""

    if set(value) != {"schema_version", "candidate", "source", "archive", "review_constraints"}:
        raise ValueError("A proposta de identidade contém campos não autorizados")
    if value["schema_version"] != PROPOSAL_SCHEMA:
        raise ValueError("A versão de proposta de identidade é inválida")
    candidate = value["candidate"]
    source = value["source"]
    archive = value["archive"]
    if (
        not isinstance(candidate, dict)
        or set(candidate)
        != {"registry_record_id", "legal_name", "kind", "observed_at", "source_record_sha256"}
        or not isinstance(source, dict)
        or set(source)
        != {
            "title",
            "publisher",
            "official_identifier",
            "url",
            "retrieved_at",
            "content_sha256",
            "mime_type",
        }
        or not isinstance(archive, dict)
        or set(archive) != {"storage_backend", "byte_size", "archived_at", "attestation_sha256"}
        or value["review_constraints"] != _REVIEW_CONSTRAINTS
    ):
        raise ValueError("A proposta não respeita a projeção privada mínima")
    # Só texto oficialmente autorizado; campos técnicos têm validação específica.
    safe_registry_text(str(candidate["legal_name"]))
    safe_registry_text(str(source["title"]), max_length=1000)
    safe_registry_text(str(archive["storage_backend"]), max_length=64)
    for value_hash in (
        candidate["source_record_sha256"],
        source["content_sha256"],
        archive["attestation_sha256"],
    ):
        if not isinstance(value_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", value_hash):
            raise ValueError("A prova privada exige hashes SHA-256 válidos")
    if (
        not isinstance(archive["byte_size"], int)
        or isinstance(archive["byte_size"], bool)
        or archive["byte_size"] < 1
    ):
        raise ValueError("O arquivo privado está vazio")
    rebuilt_source = source_proof(
        {
            "source_publisher": "JUSTICE_REGISTRY" if source["publisher"] == "IRN" else "",
            "source_kind": "ORGANISATION_REGISTRY",
            "source_official_identifier": source["official_identifier"],
            "source_url": source["url"],
            "source_retrieved_at": datetime.fromisoformat(str(source["retrieved_at"])),
            "source_sha256": source["content_sha256"],
            "source_title": source["title"],
            "source_mime_type": source["mime_type"],
        },
        str(candidate["registry_record_id"]),
    )
    source_record(
        source_document_id="server_reconstructed",
        registry_record_id=str(candidate["registry_record_id"]),
        legal_name=str(candidate["legal_name"]),
        kind=str(candidate["kind"]),
        source=rebuilt_source,
    )
    for timestamp in (candidate["observed_at"], archive["archived_at"]):
        if datetime.fromisoformat(str(timestamp)).tzinfo is None:
            raise ValueError("A prova privada exige datas com fuso horário")
    canonical_json(value)
    return value


class BaseOrganisationEditorialRepository:
    """Propostas PENDING; não cria organizações públicas, partes ou relações."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    async def list_candidates(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        if not 1 <= limit <= 50 or not 0 <= offset <= 10_000:
            raise EditorialSourceError("Paginação privada inválida")
        query = query.strip() if query else None
        if query:
            try:
                query = safe_registry_text(query, max_length=100)
                compact = re.sub(r"[\W_]+", "", query)
                if sum(char.isdecimal() for char in query) >= 9 or re.search(
                    r"[a-fA-F0-9]{32,}", compact
                ):
                    raise ValueError("A pesquisa não aceita identificadores protegidos")
            except ValueError:
                raise EditorialSourceError(
                    "Pesquise apenas pela referência do ato ou pela designação literal"
                ) from None
            if len(query) < 2:
                raise EditorialSourceError("A pesquisa exige pelo menos dois caracteres")
        items, total = (
            await self._load_candidates(query=query, limit=limit, offset=offset)
            if query
            else ([], 0)
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "filter_required": not bool(query),
            "publication_performed": False,
            "organisation_created": False,
            "relationship_created": False,
            "protected_identifier_exposed": False,
            "search_rule": (
                "A designação literal serve apenas para localizar prova privada; "
                "não identifica nem associa organizações por nome."
            ),
            "coverage_rule": (
                "Cada observação prova apenas a identidade descrita no ato oficial "
                "independente; não prova contratos, titulares, relações ou conflitos."
            ),
        }

    async def create_proposal(
        self,
        *,
        payload: BaseOrganisationIdentityEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        try:
            safe_registry_text(actor.public_alias, max_length=80)
        except ValueError:
            raise EditorialConflictError(
                "O pseudónimo editorial não respeita a privacidade"
            ) from None
        # READ COMMITTED depois do advisory lock permite ver um envio concorrente já concluído.
        # A fonte fica bloqueada e as observações/atestados são append-only.
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base-organisation-editorial:{payload.observation_id}",
                )
                await connection.fetchrow(
                    """
                    SELECT observation.id
                    FROM base_organisation_identity_observations AS observation
                    JOIN source_documents AS source ON source.id = observation.source_document_id
                    WHERE observation.id = $1
                    FOR SHARE OF observation, source
                    """,
                    payload.observation_id,
                )
                candidate = await self.get_exact_candidate(
                    observation_id=payload.observation_id,
                    source_record_sha256=payload.source_record_sha256,
                    connection=connection,
                )
                if candidate is None or not hmac.compare_digest(
                    str(candidate["proposal_confirmation_sha256"]),
                    payload.proposal_confirmation_sha256,
                ):
                    raise EditorialConflictError(
                        "A prova selecionada mudou; atualize a consulta privada antes de enviar"
                    )
                if candidate["proposal_eligible"] is not True:
                    raise EditorialSourceError(
                        "A observação não reúne prova suficiente para revisão privada"
                    )
                case, created = await self.editorial.create_ingestion_case(
                    kind=EditorialCaseKind.ORGANISATION_IDENTITY,
                    subject_type=SUBJECT_TYPE,
                    subject_id=payload.observation_id,
                    source_document_id=str(candidate["source_document_id"]),
                    normalized_data=self._normalized_proposal(candidate),
                    origin_alias="base-organisation-identity-ingestion",
                    submission_rationale=(
                        "Identidade descrita numa prova oficial independente enviada "
                        "para revisão privada. Sem correspondência por nome, criação de "
                        "organização pública, relação, contrato ou publicação."
                    ),
                    actor=actor,
                    connection=connection,
                    normalized_data_validator=_validate_projection,
                )
                # Deteta alterações feitas por triggers inesperados antes de confirmar tudo.
                final = await self.get_exact_candidate(
                    observation_id=payload.observation_id,
                    source_record_sha256=payload.source_record_sha256,
                    connection=connection,
                )
                if (
                    final is None
                    or final["proposal_eligible"] is not True
                    or final["proposal_confirmation_sha256"]
                    != candidate["proposal_confirmation_sha256"]
                ):
                    raise EditorialConflictError("A prova privada mudou durante a submissão")
        except asyncpg.PostgresError:
            raise EditorialConflictError(
                "A submissão privada foi recusada sem concluir alterações"
            ) from None
        return {
            "created": created,
            "case": case,
            "state": case["current_state"],
            "publication_performed": False,
            "organisation_created": False,
            "interest_entity_created": False,
            "match_review_created": False,
            "relationship_created": False,
        }

    async def get_exact_candidate(
        self,
        *,
        observation_id: str,
        source_record_sha256: str,
        connection: asyncpg.Connection | None = None,
    ) -> dict[str, object] | None:
        items, _total = await self._load_candidates(
            query=None,
            observation_id=observation_id,
            source_record_sha256=source_record_sha256,
            limit=1,
            offset=0,
            connection=connection,
        )
        return items[0] if items else None

    async def _load_candidates(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
        observation_id: str | None = None,
        source_record_sha256: str | None = None,
        connection: asyncpg.Connection | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        conditions: list[str] = []
        arguments: list[object] = []
        if query:
            escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            arguments.extend([query, f"%{escaped}%"])
            conditions.append(
                "(observation.registry_record_id = $1 "
                "OR observation.legal_name ILIKE $2 ESCAPE '!')"
            )
        if observation_id:
            arguments.append(observation_id)
            conditions.append(f"observation.id = ${len(arguments)}")
        if source_record_sha256:
            arguments.append(source_record_sha256)
            conditions.append(f"observation.source_record_sha256 = ${len(arguments)}")
        where = " AND ".join(conditions) or "FALSE"
        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        total = int(
            await database.fetchval(
                f"SELECT COUNT(*)::int FROM base_organisation_identity_observations "
                f"AS observation WHERE {where}",
                *arguments,
            )
        )
        arguments.extend([limit, offset])
        rows = await database.fetch(
            f"""
            SELECT observation.id AS observation_id, observation.registry_record_id,
                   observation.legal_name, observation.kind::text AS organisation_kind,
                   observation.identifier_scheme, observation.protected_identifier_digest,
                   observation.identity_scope, observation.link_status,
                   observation.publication_eligible, observation.source_document_id,
                   observation.source_record_sha256, observation.observation_sha256,
                   observation.observed_at, observation.parser_version, observation.policy_version,
                   source.publisher::text AS source_publisher,
                   source.kind::text AS source_kind, source.title AS source_title,
                   source.official_identifier AS source_official_identifier,
                   source.url AS source_url, source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256, source.mime_type AS source_mime_type,
                   archive.storage_backend, archive.byte_size, archive.archived_at,
                   archive.attestation_sha256,
                   editorial_case.id AS case_id, editorial_case.current_state::text AS case_state,
                   editorial_case.revision AS case_revision,
                   editorial_case.origin::text AS case_origin
            FROM base_organisation_identity_observations AS observation
            JOIN source_documents AS source ON source.id = observation.source_document_id
            LEFT JOIN LATERAL (
                SELECT candidate.storage_backend, candidate.byte_size,
                       candidate.archived_at, candidate.attestation_sha256
                FROM source_archive_attestations AS candidate
                WHERE candidate.source_document_id = source.id
                  AND candidate.content_sha256 = source.content_sha256
                  AND candidate.retrieval_url = source.url
                  AND candidate.retrieved_at = source.retrieved_at
                ORDER BY candidate.archived_at, candidate.id
                LIMIT 1
            ) AS archive ON TRUE
            LEFT JOIN editorial_cases AS editorial_case
              ON editorial_case.kind = 'ORGANISATION_IDENTITY'::"EditorialCaseKind"
             AND editorial_case.subject_type = '{SUBJECT_TYPE}'
             AND editorial_case.subject_id = observation.id
             AND editorial_case.source_document_id = source.id
            WHERE {where}
            ORDER BY observation.observed_at DESC, observation.id COLLATE "C"
            LIMIT ${len(arguments) - 1} OFFSET ${len(arguments)}
            """,
            *arguments,
        )
        return [self._candidate(row) for row in rows], total

    @staticmethod
    def _candidate(row: Mapping[str, Any]) -> dict[str, object]:
        try:
            source = source_proof(row, str(row["registry_record_id"]))
            record = source_record(
                source_document_id=str(row["source_document_id"]),
                registry_record_id=str(row["registry_record_id"]),
                legal_name=str(row["legal_name"]),
                kind=str(row["organisation_kind"]),
                source=source,
            )
            source_hash = sha256(record)
            if (
                not re.fullmatch(r"base_org_identity_[0-9a-f]{32}", str(row["observation_id"]))
                or not re.fullmatch(r"[0-9a-f]{64}", str(row["source_record_sha256"]))
                or not re.fullmatch(r"[0-9a-f]{64}", str(row["protected_identifier_digest"]))
                or not isinstance(row["observed_at"], datetime)
            ):
                raise ValueError("Observação inválida")
            archive: dict[str, object] | None = None
            if row["storage_backend"] is not None:
                backend = safe_registry_text(str(row["storage_backend"]), max_length=64)
                if (
                    not re.fullmatch(r"[0-9a-f]{64}", str(row["attestation_sha256"]))
                    or int(row["byte_size"]) < 1
                    or not isinstance(row["archived_at"], datetime)
                ):
                    raise ValueError("Atestado inválido")
                archive = {
                    "storage_backend": backend,
                    "byte_size": int(row["byte_size"]),
                    "archived_at": iso(row["archived_at"]),
                    "attestation_sha256": str(row["attestation_sha256"]),
                }
        except (ValueError, TypeError, KeyError):
            raise EditorialSourceError(
                "A prova contém metadados fora do âmbito privado; a consulta foi bloqueada"
            ) from None
        blocked: list[str] = []
        if (
            row["identifier_scheme"] != "PORTUGUESE_FISCAL_IDENTIFIER"
            or row["identity_scope"] != "ORGANISATION_IDENTITY_ONLY"
            or row["link_status"] != "UNLINKED_PRIVATE"
            or row["publication_eligible"] is not False
            or row["parser_version"] != PARSER_VERSION
            or row["policy_version"] != POLICY_VERSION
        ):
            blocked.append("O âmbito da observação não coincide com a política privada.")
        if (
            source_hash != row["source_record_sha256"]
            or observation_sha256(source_hash, str(row["protected_identifier_digest"]))
            != row["observation_sha256"]
            or iso(row["observed_at"]) != source["retrieved_at"]
        ):
            blocked.append("A prova preservada deixou de coincidir com a fonte.")
        if archive is None:
            blocked.append("O original individual não possui arquivo privado atestado.")
        return {
            "observation_id": str(row["observation_id"]),
            "source_document_id": str(row["source_document_id"]),
            "registry_record_id": record["registry_record_id"],
            "legal_name": record["legal_name"],
            "kind": record["kind"],
            "observed_at": iso(row["observed_at"]),
            "source_record_sha256": str(row["source_record_sha256"]),
            "proposal_confirmation_sha256": proposal_confirmation_sha256(
                observation_id=str(row["observation_id"]),
                source_document_id=str(row["source_document_id"]),
                source_content_sha256=str(row["source_sha256"]),
                source_record_sha256=str(row["source_record_sha256"]),
                archive_attestation_sha256=(
                    str(archive["attestation_sha256"]) if archive else None
                ),
            ),
            "protected_identifier_observed": True,
            "protected_identifier_exposed": False,
            "source": source,
            "archive": archive,
            "existing_case": (
                {
                    "id": str(row["case_id"]),
                    "state": str(row["case_state"]),
                    "revision": int(row["case_revision"]),
                    "origin": str(row["case_origin"]),
                }
                if row["case_id"] is not None
                else None
            ),
            "proposal_eligible": not blocked,
            "blocked_reasons": blocked,
            "publication_performed": False,
            "organisation_created": False,
            "relationship_created": False,
        }

    @staticmethod
    def _normalized_proposal(candidate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": PROPOSAL_SCHEMA,
            "candidate": {
                key: candidate[key]
                for key in (
                    "registry_record_id",
                    "legal_name",
                    "kind",
                    "observed_at",
                    "source_record_sha256",
                )
            },
            "source": dict(candidate["source"]),
            "archive": dict(candidate["archive"]),
            "review_constraints": dict(_REVIEW_CONSTRAINTS),
        }
