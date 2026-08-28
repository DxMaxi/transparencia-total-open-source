"""Porta privada entre observações EPT e o circuito editorial humano."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.core.security import is_individual_ept_source_url
from app.models.editorial import EditorialCaseKind, StaffSession
from app.models.ept_declaration import EptPublicInterestEditorialProposalRequest
from app.repositories.editorial import EditorialRepository, EditorialSourceError

_INGESTION_ALIAS = "ept-public-interest-ingestion"
_SUBJECT_TYPE = "EPT_PUBLIC_INTEREST_OBSERVATION"
_SCHEMA_VERSION = "ept-public-interest-observation-v1"
_PROPOSAL_SCHEMA_VERSION = "ept-public-interest-editorial-v1"


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


def _reference_sha256(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _case_reference(row: Mapping[str, Any]) -> dict[str, object] | None:
    if row["case_id"] is None:
        return None
    return {
        "id": str(row["case_id"]),
        "state": str(row["case_state"]),
        "revision": int(row["case_revision"]),
        "origin": str(row["case_origin"]),
    }


class EptDeclarationEditorialRepository:
    """Cria propostas privadas; nunca associa por nome nem publica declarações."""

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
        items, total = await self._load_candidates(
            query=query.strip() if query and query.strip() else None,
            observation_id=None,
            source_record_sha256=None,
            limit=limit,
            offset=offset,
        )
        if not items and offset:
            _first, total = await self._load_candidates(
                query=query.strip() if query and query.strip() else None,
                observation_id=None,
                source_record_sha256=None,
                limit=1,
                offset=0,
            )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + len(items) < total else None,
            "publication_performed": False,
            "identity_link_performed": False,
            "search_rule": (
                "A pesquisa filtra observações privadas já identificadas pela EPT. O nome "
                "serve apenas para encontrar a linha e nunca para associar uma pessoa."
            ),
            "legal_scope": (
                "Apenas metadados do registo público de interesses entram neste circuito; "
                "rendimentos, património e conteúdos de consulta condicionada ficam excluídos."
            ),
        }

    async def create_proposal(
        self,
        *,
        payload: EptPublicInterestEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        candidate = await self.get_exact_candidate(
            observation_id=payload.observation_id,
            source_record_sha256=payload.source_record_sha256,
        )
        if candidate is None:
            raise EditorialSourceError(
                "A observação EPT não existe ou a respetiva prova deixou de coincidir"
            )
        if candidate["proposal_eligible"] is not True:
            reasons = candidate["blocked_reasons"]
            detail = (
                "; ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else ""
            )
            raise EditorialSourceError(
                "A observação EPT não reúne prova suficiente para revisão privada"
                + (f": {detail}" if detail else "")
            )

        case, created = await self.editorial.create_ingestion_case(
            kind=EditorialCaseKind.POLITICIAN_PROFILE,
            subject_type=_SUBJECT_TYPE,
            subject_id=payload.observation_id,
            source_document_id=str(candidate["source_document_id"]),
            normalized_data=self._normalized_proposal(candidate),
            origin_alias=_INGESTION_ALIAS,
            submission_rationale=(
                "Metadados mínimos de um registo público de interesses EPT enviados para "
                "revisão privada. Não foram recolhidos rendimentos ou património, não foi "
                "ligada qualquer pessoa por nome e a revisão jurídica continua pendente."
            ),
            actor=actor,
        )
        return {
            "created": created,
            "case": case,
            "state": "PRIVATE_PENDING_REVIEW",
            "publication_performed": False,
            "declaration_created": False,
            "person_link_created": False,
            "public_review_created": False,
            "independent_legal_review_completed": False,
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
        observation_id: str | None,
        source_record_sha256: str | None,
        limit: int,
        offset: int,
        connection: asyncpg.Connection | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        conditions = [
            "source.publisher = 'TRANSPARENCY_ENTITY'",
            "source.kind = 'DECLARATION'",
            "source.url LIKE 'https://%'",
        ]
        arguments: list[object] = []
        if query:
            escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            arguments.extend([query, f"%{escaped}%"])
            exact_arg = len(arguments) - 1
            search_arg = len(arguments)
            conditions.append(
                "(observation.official_declaration_id = "
                f"${exact_arg} OR observation.public_subject_name ILIKE "
                f"${search_arg} ESCAPE '!')"
            )
        if observation_id:
            arguments.append(observation_id)
            conditions.append(f"observation.id = ${len(arguments)}")
        if source_record_sha256:
            arguments.append(source_record_sha256)
            conditions.append(f"observation.source_record_sha256 = ${len(arguments)}")
        arguments.extend([limit, offset])
        limit_arg = len(arguments) - 1
        offset_arg = len(arguments)

        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        rows = await database.fetch(
            f"""
            SELECT observation.id AS observation_id,
                   observation.official_declaration_id,
                   observation.official_subject_digest,
                   observation.public_subject_name,
                   observation.declaration_type,
                   observation.declared_at,
                   observation.period_label,
                   observation.public_access_scope,
                   observation.legal_review_status,
                   observation.identity_link_status,
                   observation.source_document_id,
                   observation.source_record_sha256,
                   observation.observed_at,
                   source.title AS source_title,
                   source.official_identifier AS source_official_identifier,
                   source.url AS source_url,
                   source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256,
                   source.mime_type AS source_mime_type,
                   archive.storage_backend,
                   archive.byte_size,
                   archive.archived_at,
                   archive.attestation_sha256,
                   editorial_case.id AS case_id,
                   editorial_case.current_state AS case_state,
                   editorial_case.revision AS case_revision,
                   editorial_case.origin AS case_origin,
                   (COUNT(*) OVER())::int AS total_count
            FROM ept_public_interest_observations AS observation
            JOIN source_documents AS source
              ON source.id = observation.source_document_id
            LEFT JOIN LATERAL (
                SELECT candidate.storage_backend, candidate.byte_size,
                       candidate.archived_at, candidate.attestation_sha256
                FROM source_archive_attestations AS candidate
                WHERE candidate.source_document_id = source.id
                  AND candidate.content_sha256 = source.content_sha256
                  AND candidate.retrieval_url = source.url
                  AND candidate.retrieved_at = source.retrieved_at
                ORDER BY candidate.archived_at ASC, candidate.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            LEFT JOIN editorial_cases AS editorial_case
              ON editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
             AND editorial_case.subject_type = '{_SUBJECT_TYPE}'
             AND editorial_case.subject_id = observation.id
             AND editorial_case.source_document_id = source.id
            WHERE {" AND ".join(conditions)}
            ORDER BY observation.observed_at DESC,
                     LOWER(observation.public_subject_name) COLLATE "C",
                     observation.official_declaration_id COLLATE "C"
            LIMIT ${limit_arg} OFFSET ${offset_arg}
            """,
            *arguments,
        )
        candidates = [self._candidate(row) for row in rows]
        total = int(rows[0]["total_count"]) if rows else 0
        return candidates, total

    @staticmethod
    def _candidate(row: Mapping[str, Any]) -> dict[str, object]:
        blocked: list[str] = []
        source_url = str(row["source_url"])
        source_record = {
            "schema_version": _SCHEMA_VERSION,
            "official_declaration_id": str(row["official_declaration_id"]),
            "official_subject_digest": str(row["official_subject_digest"]),
            "public_subject_name": str(row["public_subject_name"]),
            "declaration_type": str(row["declaration_type"]),
            "declared_at": _iso(row["declared_at"]),
            "period_label": row["period_label"],
            "public_access_scope": str(row["public_access_scope"]),
            "legal_review_status": str(row["legal_review_status"]),
            "identity_link_status": str(row["identity_link_status"]),
            "source_document_id": str(row["source_document_id"]),
            "source_content_sha256": str(row["source_sha256"]),
        }
        computed_record_sha256 = hashlib.sha256(
            _canonical_json(source_record).encode("utf-8")
        ).hexdigest()
        if row["declaration_type"] != "INTEREST_REGISTER":
            blocked.append("O registo não está limitado ao domínio público de interesses.")
        if row["public_access_scope"] != "PUBLIC_INTEREST_REGISTER":
            blocked.append("O âmbito público permitido deixou de coincidir com o contrato.")
        if row["legal_review_status"] != "REQUIRES_INDEPENDENT_LEGAL_REVIEW":
            blocked.append("O estado jurídico privado é desconhecido ou foi alterado.")
        if row["identity_link_status"] != "UNLINKED_PRIVATE":
            blocked.append("A observação já contém uma associação de identidade não esperada.")
        if row["source_official_identifier"] != row["official_declaration_id"]:
            blocked.append("O identificador do documento não coincide com o registo observado.")
        if not is_individual_ept_source_url(source_url):
            blocked.append(
                "A ligação não é uma prova individual num domínio oficial autorizado da EPT."
            )
        if row["storage_backend"] is None:
            blocked.append("O original individual não possui arquivo privado atestado.")
        if str(row["source_record_sha256"]) != computed_record_sha256:
            blocked.append("O hash da observação normalizada deixou de coincidir.")

        return {
            "observation_id": str(row["observation_id"]),
            "source_document_id": str(row["source_document_id"]),
            "official_declaration_id": str(row["official_declaration_id"]),
            "official_subject_reference_sha256": _reference_sha256(row["official_subject_digest"]),
            "public_subject_name": str(row["public_subject_name"]),
            "declaration_type": str(row["declaration_type"]),
            "declared_at": _iso(row["declared_at"]),
            "period_label": row["period_label"],
            "observed_at": _iso(row["observed_at"]),
            "source_record_sha256": str(row["source_record_sha256"]),
            "source": {
                "title": str(row["source_title"]),
                "official_identifier": row["source_official_identifier"],
                "url": source_url,
                "retrieved_at": _iso(row["source_retrieved_at"]),
                "content_sha256": str(row["source_sha256"]),
                "mime_type": row["source_mime_type"],
            },
            "archive": (
                {
                    "storage_backend": str(row["storage_backend"]),
                    "byte_size": int(row["byte_size"]),
                    "archived_at": _iso(row["archived_at"]),
                    "attestation_sha256": str(row["attestation_sha256"]),
                }
                if row["storage_backend"] is not None
                else None
            ),
            "legal_review_status": str(row["legal_review_status"]),
            "identity_link_status": str(row["identity_link_status"]),
            "existing_case": _case_reference(row),
            "proposal_eligible": not blocked,
            "blocked_reasons": blocked,
            "public_projection_allowed": False,
            "person_link_allowed": False,
            "name_matching_allowed": False,
            "income_or_asset_content_present": False,
        }

    @staticmethod
    def _normalized_proposal(candidate: Mapping[str, Any]) -> dict[str, object]:
        source = candidate["source"]
        archive = candidate["archive"]
        assert isinstance(source, Mapping)
        assert isinstance(archive, Mapping)
        return {
            "schema_version": _PROPOSAL_SCHEMA_VERSION,
            "candidate": {
                "official_declaration_id": candidate["official_declaration_id"],
                "official_subject_reference_sha256": candidate["official_subject_reference_sha256"],
                "public_subject_name": candidate["public_subject_name"],
                "declaration_type": "INTEREST_REGISTER",
                "declared_at": candidate["declared_at"],
                "period_label": candidate["period_label"],
                "observed_at": candidate["observed_at"],
                "source_record_sha256": candidate["source_record_sha256"],
            },
            "source_proof": {
                "document_reference_sha256": _reference_sha256(candidate["source_document_id"]),
                "publisher": "TRANSPARENCY_ENTITY",
                "official_identifier": source["official_identifier"],
                "url": source["url"],
                "retrieved_at": source["retrieved_at"],
                "content_sha256": source["content_sha256"],
                "archive_attestation_sha256": archive["attestation_sha256"],
            },
            "legal_scope": {
                "scope": "PUBLIC_INTEREST_REGISTER_ONLY",
                "income_or_asset_content_included": False,
                "independent_legal_review": "REQUIRED_BEFORE_ANY_PUBLICATION",
                "legal_control_is_not_automated": True,
            },
            "identity": {
                "status": "UNLINKED_PRIVATE",
                "name_matching_allowed": False,
                "fuzzy_matching_allowed": False,
                "exact_official_evidence_required": True,
            },
            "publication": {
                "public_projection_allowed": False,
                "person_link_created": False,
                "asset_declaration_created": False,
                "data_publication_review_created": False,
                "publication_event_created": False,
            },
        }
