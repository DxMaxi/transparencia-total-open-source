"""Porta privada entre autorias oficiais de iniciativas e revisão humana."""

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.models.editorial import (
    EditorialCaseKind,
    PoliticianInitiativeAuthorshipEditorialProposalRequest,
    StaffSession,
)
from app.models.parliamentary_initiative_authorship import (
    PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION,
)
from app.repositories.editorial import EditorialRepository, EditorialSourceError

_INGESTION_ALIAS = "parliament-initiative-authorship-ingestion"
_SUBJECT_TYPE = "PARLIAMENT_INITIATIVE_AUTHORSHIP"
_SCHEMA_VERSION = "politician-initiative-authorship-editorial-v1"


def _reference_sha256(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def _case_reference(row: Mapping[str, Any]) -> dict[str, object] | None:
    if row["case_id"] is None:
        return None
    return {
        "id": str(row["case_id"]),
        "state": str(row["case_state"]),
        "revision": int(row["case_revision"]),
        "origin": str(row["case_origin"]),
    }


class PoliticianInitiativeAuthorshipEditorialRepository:
    """Cria propostas por relação literal, nunca por semelhança de nomes."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    async def list_candidates(
        self,
        *,
        legislature: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        exact_legislature = legislature.strip() if legislature and legislature.strip() else None
        exact_query = query.strip() if query and query.strip() else None
        items, total = await self._load_candidates(
            legislature=exact_legislature,
            query=exact_query,
            observation_id=None,
            limit=limit,
            offset=offset,
            connection=None,
        )
        if not items and offset:
            _first, total = await self._load_candidates(
                legislature=exact_legislature,
                query=exact_query,
                observation_id=None,
                limit=1,
                offset=0,
                connection=None,
            )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + len(items) < total else None,
            "publication_performed": False,
            "search_rule": (
                "A pesquisa filtra relações já separadas por IniId e idCadastro oficiais; "
                "não associa identidades, partidos ou iniciativas por nome semelhante."
            ),
        }

    async def create_proposal(
        self,
        *,
        payload: PoliticianInitiativeAuthorshipEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        candidates, _total = await self._load_candidates(
            legislature=None,
            query=None,
            observation_id=payload.observation_id,
            limit=1,
            offset=0,
            connection=None,
        )
        if not candidates:
            raise EditorialSourceError(
                "A autoria não existe ou não possui arquivo oficial atestado"
            )
        candidate = candidates[0]
        if candidate["source_record_sha256"] != payload.source_record_sha256:
            raise EditorialSourceError(
                "A autoria observada mudou; atualize a prova antes de criar a proposta"
            )
        if candidate["proposal_eligible"] is not True:
            reasons = candidate["blocked_reasons"]
            detail = (
                "; ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else ""
            )
            raise EditorialSourceError(
                "A autoria não reúne prova suficiente para revisão"
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
                "Autoria individual declarada pela Assembleia enviada para revisão privada; "
                "IniId e idCadastro foram preservados exatamente, sem correspondência por "
                "nome ou partido e sem criar qualquer relação pública."
            ),
            actor=actor,
        )
        return {
            "created": created,
            "case": case,
            "state": "PRIVATE_PENDING_REVIEW",
            "publication_performed": False,
            "initiative_authorship_created": False,
            "people_created": 0,
            "party_links_created": 0,
            "public_reviews_created": 0,
            "name_matching_allowed": False,
        }

    async def _load_candidates(
        self,
        *,
        legislature: str | None,
        query: str | None,
        observation_id: str | None,
        limit: int,
        offset: int,
        connection: asyncpg.Connection | None,
    ) -> tuple[list[dict[str, object]], int]:
        conditions = [
            "source.publisher = 'PARLIAMENT'",
            "source.url LIKE 'https://%'",
            "snapshot.parser_version = $1",
            "observation.relation = 'AUTHOR'",
        ]
        arguments: list[object] = [PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION]
        if legislature:
            arguments.append(legislature)
            conditions.append(f"snapshot.legislature = ${len(arguments)}")
        if query:
            escaped_query = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            arguments.append(f"%{escaped_query}%")
            parameter = f"${len(arguments)}"
            conditions.append(
                "(observation.initiative_source_id ILIKE "
                f"{parameter} ESCAPE '!' OR observation.official_deputy_id ILIKE "
                f"{parameter} ESCAPE '!' OR observation.parliamentary_name ILIKE "
                f"{parameter} ESCAPE '!' OR COALESCE(initiative.number, '') ILIKE "
                f"{parameter} ESCAPE '!' OR COALESCE(initiative.title, '') ILIKE "
                f"{parameter} ESCAPE '!')"
            )
        if observation_id:
            arguments.append(observation_id)
            conditions.append(f"observation.id = ${len(arguments)}")
        arguments.extend([limit, offset])
        limit_arg = len(arguments) - 1
        offset_arg = len(arguments)

        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        rows = await database.fetch(
            f"""
            SELECT observation.id AS observation_id,
                   observation.snapshot_id,
                   observation.initiative_source_id,
                   observation.official_deputy_id,
                   observation.parliamentary_name,
                   observation.parliamentary_group_label,
                   observation.relation,
                   observation.source_record_sha256,
                   snapshot.source_document_id,
                   snapshot.legislature,
                   snapshot.parser_version,
                   snapshot.normalised_sha256,
                   snapshot.collected_at,
                   snapshot.initiative_count,
                   snapshot.authorship_count,
                   snapshot.deputy_count,
                   source.title AS source_title,
                   source.official_identifier,
                   source.url AS source_url,
                   source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256,
                   source.mime_type AS source_mime_type,
                   archive.storage_backend,
                   archive.byte_size,
                   archive.archived_at,
                   archive.attestation_sha256,
                   materialised.initiative_count AS actual_initiative_count,
                   materialised.authorship_count AS actual_authorship_count,
                   materialised.deputy_count AS actual_deputy_count,
                   initiative.match_count AS initiative_match_count,
                   initiative.id AS initiative_id,
                   initiative.number AS initiative_number,
                   initiative.type AS initiative_type,
                   initiative.title AS initiative_title,
                   initiative.status AS initiative_status,
                   initiative.official_url AS initiative_official_url,
                   identity.person_id,
                   identity.full_name AS identity_full_name,
                   identity.publishable AS identity_publishable,
                   authorship_case.id AS case_id,
                   authorship_case.current_state AS case_state,
                   authorship_case.revision AS case_revision,
                   authorship_case.origin AS case_origin,
                   (COUNT(*) OVER())::int AS total_count
            FROM parliament_initiative_author_observations AS observation
            JOIN parliament_initiative_author_snapshots AS snapshot
              ON snapshot.id = observation.snapshot_id
            JOIN source_documents AS source ON source.id = snapshot.source_document_id
            JOIN LATERAL (
                SELECT attestation.storage_backend, attestation.byte_size,
                       attestation.archived_at, attestation.attestation_sha256
                FROM source_archive_attestations AS attestation
                WHERE attestation.source_document_id = source.id
                  AND attestation.content_sha256 = source.content_sha256
                  AND attestation.retrieval_url = source.url
                  AND attestation.retrieved_at = source.retrieved_at
                ORDER BY attestation.archived_at ASC, attestation.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            JOIN LATERAL (
                SELECT COUNT(DISTINCT candidate.initiative_source_id)::int
                           AS initiative_count,
                       COUNT(*)::int AS authorship_count,
                       COUNT(DISTINCT candidate.official_deputy_id)::int AS deputy_count
                FROM parliament_initiative_author_observations AS candidate
                WHERE candidate.snapshot_id = snapshot.id
            ) AS materialised ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS match_count,
                       MIN(item.id) AS id,
                       MIN(item.number) AS number,
                       MIN(item.type) AS type,
                       MIN(item.title) AS title,
                       MIN(item.status) AS status,
                       MIN(item.official_url) AS official_url
                FROM parliamentary_initiatives AS item
                WHERE item.source_document_id = snapshot.source_document_id
                  AND item.legislature = snapshot.legislature
                  AND item.source_id = observation.initiative_source_id
            ) AS initiative ON TRUE
            LEFT JOIN LATERAL (
                SELECT person.id AS person_id, person.full_name,
                       latest_review.publishable
                FROM people AS person
                LEFT JOIN LATERAL (
                    SELECT review.publishable
                    FROM data_publication_reviews AS review
                    WHERE review.entity_type = 'PERSON'
                      AND review.entity_id = person.id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) AS latest_review ON TRUE
                WHERE person.source_id = observation.official_deputy_id
                LIMIT 1
            ) AS identity ON TRUE
            LEFT JOIN editorial_cases AS authorship_case
              ON authorship_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
             AND authorship_case.subject_type = '{_SUBJECT_TYPE}'
             AND authorship_case.subject_id = observation.id
             AND authorship_case.source_document_id = snapshot.source_document_id
            WHERE {" AND ".join(conditions)}
            ORDER BY snapshot.collected_at DESC,
                     observation.initiative_source_id COLLATE "C",
                     observation.official_deputy_id COLLATE "C"
            LIMIT ${limit_arg} OFFSET ${offset_arg}
            """,
            *arguments,
        )
        items = [self._candidate(row) for row in rows]
        total = int(rows[0]["total_count"]) if rows else 0
        return items, total

    @staticmethod
    def _candidate(row: Mapping[str, Any]) -> dict[str, object]:
        expected_counts = {
            "initiatives": int(row["initiative_count"]),
            "authorships": int(row["authorship_count"]),
            "deputies": int(row["deputy_count"]),
        }
        actual_counts = {
            "initiatives": int(row["actual_initiative_count"]),
            "authorships": int(row["actual_authorship_count"]),
            "deputies": int(row["actual_deputy_count"]),
        }
        observation_payload = {
            "initiative_source_id": str(row["initiative_source_id"]),
            "official_deputy_id": str(row["official_deputy_id"]),
            "parliamentary_name": str(row["parliamentary_name"]),
            "parliamentary_group_label": row["parliamentary_group_label"],
            "relation": str(row["relation"]),
        }
        computed_record_sha256 = hashlib.sha256(
            _canonical_json(observation_payload).encode("utf-8")
        ).hexdigest()
        source_record_sha256 = str(row["source_record_sha256"])
        initiative_match_count = int(row["initiative_match_count"])
        blocked: list[str] = []
        if expected_counts != actual_counts:
            blocked.append("As contagens materializadas divergem do manifesto imutável.")
        if computed_record_sha256 != source_record_sha256:
            blocked.append("A relação materializada diverge do respetivo SHA-256.")
        if initiative_match_count != 1:
            blocked.append(
                "O IniId não corresponde exatamente a uma única iniciativa do mesmo arquivo."
            )

        person_id = row["person_id"]
        identity_exact = person_id is not None
        identity_reviewed = identity_exact and row["identity_publishable"] is True
        publication_blockers: list[str] = []
        if not identity_exact:
            publication_blockers.append(
                "O idCadastro ainda não tem identidade pública com o mesmo identificador exato."
            )
        elif not identity_reviewed:
            publication_blockers.append(
                "A identidade exata ainda não tem revisão pública positiva."
            )
        publication_blockers.append(
            "A publicação de autorias individuais pertence a uma etapa posterior da V5."
        )
        warnings = [
            "O nome e a sigla são texto preservado da fonte e nunca servem para associar pessoa "
            "ou partido.",
            "A autoria desta iniciativa não permite inferir voto, concordância futura, posição "
            "coletiva do partido ou mérito político.",
        ]
        return {
            "observation_id": str(row["observation_id"]),
            "snapshot_id": str(row["snapshot_id"]),
            "source_document_id": str(row["source_document_id"]),
            "legislature": str(row["legislature"]),
            "initiative_source_id": str(row["initiative_source_id"]),
            "official_deputy_id": str(row["official_deputy_id"]),
            "parliamentary_name": str(row["parliamentary_name"]),
            "parliamentary_group_label": row["parliamentary_group_label"],
            "relation": str(row["relation"]),
            "source_record_sha256": source_record_sha256,
            "snapshot": {
                "parser_version": str(row["parser_version"]),
                "normalised_sha256": str(row["normalised_sha256"]),
                "collected_at": _iso(row["collected_at"]),
                "manifest_counts": expected_counts,
                "materialised_counts": actual_counts,
            },
            "initiative": {
                "exact_match_count": initiative_match_count,
                "id": str(row["initiative_id"]) if row["initiative_id"] is not None else None,
                "number": row["initiative_number"],
                "type": row["initiative_type"],
                "title": row["initiative_title"],
                "status": row["initiative_status"],
                "official_url": row["initiative_official_url"],
            },
            "identity_reconciliation": {
                "exact_identity": identity_exact,
                "reviewed_identity": identity_reviewed,
                "full_name": row["identity_full_name"] if identity_exact else None,
                "rule": "EXACT_AR_IDCADASTRO_ONLY",
            },
            "source": {
                "title": str(row["source_title"]),
                "official_identifier": row["official_identifier"],
                "url": str(row["source_url"]),
                "retrieved_at": _iso(row["source_retrieved_at"]),
                "content_sha256": str(row["source_sha256"]),
                "mime_type": row["source_mime_type"],
            },
            "archive": {
                "storage_backend": str(row["storage_backend"]),
                "byte_size": int(row["byte_size"]),
                "archived_at": _iso(row["archived_at"]),
                "attestation_sha256": str(row["attestation_sha256"]),
            },
            "existing_case": _case_reference(row),
            "blocked_reasons": blocked,
            "warnings": warnings,
            "proposal_eligible": not blocked,
            "publication_blockers": publication_blockers,
            "publication_ready": False,
            "public_projection_allowed": False,
            "name_matching_allowed": False,
            "party_matching_allowed": False,
            "collective_position_inference_allowed": False,
        }

    @staticmethod
    def _normalized_proposal(candidate: dict[str, object]) -> dict[str, Any]:
        source = candidate["source"]
        archive = candidate["archive"]
        initiative = candidate["initiative"]
        snapshot = candidate["snapshot"]
        assert isinstance(source, dict)
        assert isinstance(archive, dict)
        assert isinstance(initiative, dict)
        assert isinstance(snapshot, dict)
        return {
            "schema_version": _SCHEMA_VERSION,
            "authorship": {
                "observation_reference_sha256": _reference_sha256(candidate["observation_id"]),
                "initiative_source_id_reference_sha256": _reference_sha256(
                    candidate["initiative_source_id"]
                ),
                "official_deputy_id_reference_sha256": _reference_sha256(
                    candidate["official_deputy_id"]
                ),
                "parliamentary_name": candidate["parliamentary_name"],
                "parliamentary_group_label": candidate["parliamentary_group_label"],
                "relation": candidate["relation"],
                "source_record_sha256": candidate["source_record_sha256"],
            },
            "initiative": {
                "number": initiative["number"],
                "type": initiative["type"],
                "title": initiative["title"],
                "status": initiative["status"],
                "official_url": initiative["official_url"],
                "exact_match_count": initiative["exact_match_count"],
            },
            "identity_reconciliation": candidate["identity_reconciliation"],
            "source_proof": {
                "source_document_reference_sha256": _reference_sha256(
                    candidate["source_document_id"]
                ),
                "url": source["url"],
                "retrieved_at": source["retrieved_at"],
                "content_sha256": source["content_sha256"],
                "archive_attestation_sha256": archive["attestation_sha256"],
                "archive_byte_size": archive["byte_size"],
                "normalised_sha256": snapshot["normalised_sha256"],
                "parser_version": snapshot["parser_version"],
                "collected_at": snapshot["collected_at"],
            },
            "limitations": candidate["warnings"],
            "publication_blockers": candidate["publication_blockers"],
            "identity_rule": "EXACT_AR_IDCADASTRO_ONLY",
            "initiative_rule": "EXACT_AR_INIID_ONLY",
            "relation_rule": "SOURCE_DECLARED_AUTHOR_ONLY",
            "name_matching_allowed": False,
            "party_matching_allowed": False,
            "collective_position_inference_allowed": False,
            "publication": {
                "state": "PRIVATE_PENDING_REVIEW",
                "automatic_publication": False,
                "human_review_required": True,
                "initiative_authorship_created": False,
                "people_created": 0,
                "party_links_created": 0,
                "public_reviews_created": 0,
                "publication_event_created": False,
            },
        }
