"""Porta privada entre situações oficiais e a revisão humana de mandatos."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.models.editorial import (
    EditorialCaseKind,
    PoliticianMandateEditorialProposalRequest,
    StaffSession,
)
from app.repositories.editorial import EditorialRepository, EditorialSourceError

_INGESTION_ALIAS = "parliament-mandate-ingestion"
_SUBJECT_TYPE = "PARLIAMENT_MANDATE_SITUATION"
_SCHEMA_VERSION = "politician-mandate-editorial-v1"
_SERVING_SITUATIONS = frozenset({"efetivo", "efetivodefinitivo", "efetivotemporario"})


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reference_sha256(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _normalise_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]", "", ascii_value.casefold())


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def _parse_date(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Uma data de situação deixou de ter o formato textual esperado")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Uma data de situação deixou de ser ISO-8601 válida") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _json_object(value: object) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise ValueError("A situação parlamentar deixou de ser um objeto")
    return dict(decoded)


def _case_reference(row: Mapping[str, Any]) -> dict[str, object] | None:
    if row["case_id"] is None:
        return None
    return {
        "id": str(row["case_id"]),
        "state": str(row["case_state"]),
        "revision": int(row["case_revision"]),
        "origin": str(row["case_origin"]),
    }


class PoliticianMandateEditorialRepository:
    """Reconstrói candidatos por intervalo e cria apenas processos privados ``PENDING``."""

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
        items, total = await self._load_candidates(
            legislature=legislature.strip() if legislature and legislature.strip() else None,
            query=query.strip() if query and query.strip() else None,
            observation_id=None,
            source_period_sha256=None,
            limit=limit,
            offset=offset,
        )
        if not items and offset:
            _first, total = await self._load_candidates(
                legislature=legislature.strip() if legislature and legislature.strip() else None,
                query=query.strip() if query and query.strip() else None,
                observation_id=None,
                source_period_sha256=None,
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
            "search_rule": (
                "A pesquisa limita intervalos já ligados a um DepId oficial; não associa "
                "pessoas por nome nem transforma a situação observada num mandato."
            ),
        }

    async def create_proposal(
        self,
        *,
        payload: PoliticianMandateEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        candidate = await self.get_exact_candidate(
            observation_id=payload.observation_id,
            source_period_sha256=payload.source_period_sha256,
        )
        if candidate is None:
            raise EditorialSourceError(
                "O intervalo oficial não existe ou deixou de corresponder à observação atestada"
            )
        if candidate["proposal_eligible"] is not True:
            reasons = candidate["blocked_reasons"]
            detail = (
                "; ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else ""
            )
            raise EditorialSourceError(
                "O intervalo não reúne prova suficiente para revisão de mandato"
                + (f": {detail}" if detail else "")
            )

        case, created = await self.editorial.create_ingestion_case(
            kind=EditorialCaseKind.POLITICIAN_PROFILE,
            subject_type=_SUBJECT_TYPE,
            subject_id=str(candidate["subject_id"]),
            source_document_id=str(candidate["source_document_id"]),
            normalized_data=self._normalized_proposal(candidate),
            origin_alias=_INGESTION_ALIAS,
            submission_rationale=(
                "Intervalo de situação parlamentar oficial enviado para revisão privada; "
                "o DepId, o período e o círculo foram confirmados por identificadores exatos, "
                "mas nenhuma semântica jurídica, filiação ou publicação foi inferida."
            ),
            actor=actor,
        )
        return {
            "created": created,
            "case": case,
            "state": "PRIVATE_PENDING_REVIEW",
            "publication_performed": False,
            "mandate_created": False,
            "public_review_created": False,
            "party_link_created": False,
        }

    async def get_exact_candidate(
        self,
        *,
        observation_id: str,
        source_period_sha256: str,
        connection: asyncpg.Connection | None = None,
    ) -> dict[str, object] | None:
        """Reconstrói um intervalo exato; o hash nunca é aceite como conteúdo do cliente."""

        candidates, _total = await self._load_candidates(
            legislature=None,
            query=None,
            observation_id=observation_id,
            source_period_sha256=source_period_sha256,
            limit=100,
            offset=0,
            connection=connection,
        )
        return candidates[0] if candidates else None

    async def _load_candidates(
        self,
        *,
        legislature: str | None,
        query: str | None,
        observation_id: str | None,
        source_period_sha256: str | None,
        limit: int,
        offset: int,
        connection: asyncpg.Connection | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        conditions = [
            "source.publisher = 'PARLIAMENT'",
            "source.url LIKE 'https://%'",
            "source.kind <> 'NEWS_ARTICLE'",
        ]
        arguments: list[object] = []
        if legislature:
            arguments.append(legislature)
            conditions.append(f"snapshot.legislature = ${len(arguments)}")
        if query:
            escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            arguments.extend([query, f"%{escaped}%"])
            exact_arg = len(arguments) - 1
            search_arg = len(arguments)
            conditions.append(
                "(observation.source_id = "
                f"${exact_arg} OR observation.parliamentary_name ILIKE ${search_arg} ESCAPE '!' "
                f"OR observation.full_name ILIKE ${search_arg} ESCAPE '!')"
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
            WITH materialised AS (
                SELECT candidate.snapshot_id,
                       COUNT(*)::int AS deputy_count,
                       COALESCE(SUM(jsonb_array_length(candidate.parliamentary_groups)), 0)::int
                           AS group_period_count,
                       COALESCE(SUM(jsonb_array_length(candidate.mandate_situations)), 0)::int
                           AS situation_period_count,
                       COALESCE(SUM(jsonb_array_length(candidate.offices)), 0)::int
                           AS office_period_count
                FROM parliament_deputy_observations AS candidate
                GROUP BY candidate.snapshot_id
            )
            SELECT observation.id AS observation_id,
                   observation.source_id,
                   observation.parliamentary_name,
                   observation.full_name,
                   observation.constituency_source_id,
                   observation.constituency_label,
                   situation.period,
                   situation.ordinality::int AS period_ordinal,
                   snapshot.id AS snapshot_id,
                   snapshot.source_document_id,
                   snapshot.legislature,
                   snapshot.parser_version,
                   snapshot.normalised_sha256,
                   snapshot.collected_at,
                   snapshot.deputy_count AS manifest_deputy_count,
                   snapshot.group_period_count AS manifest_group_period_count,
                   snapshot.situation_period_count AS manifest_situation_period_count,
                   snapshot.office_period_count AS manifest_office_period_count,
                   materialised.deputy_count,
                   materialised.group_period_count,
                   materialised.situation_period_count,
                   materialised.office_period_count,
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
                   person.id AS person_id,
                   membership.id AS membership_id,
                   person_review.publishable AS person_publishable,
                   person_review.reviewed_at AS person_reviewed_at,
                   mandate_case.id AS case_id,
                   mandate_case.current_state AS case_state,
                   mandate_case.revision AS case_revision,
                   mandate_case.origin AS case_origin,
                   (COUNT(*) OVER())::int AS total_count
            FROM parliament_deputy_observations AS observation
            JOIN parliament_deputy_snapshots AS snapshot
              ON snapshot.id = observation.snapshot_id
            JOIN materialised ON materialised.snapshot_id = snapshot.id
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
            CROSS JOIN LATERAL jsonb_array_elements(observation.mandate_situations)
                WITH ORDINALITY AS situation(period, ordinality)
            LEFT JOIN people AS person ON person.source_id = observation.source_id
            LEFT JOIN parliamentary_membership_snapshots AS membership
              ON membership.person_id = person.id
             AND membership.source_document_id = snapshot.source_document_id
             AND membership.legislature = snapshot.legislature
            LEFT JOIN LATERAL (
                SELECT review.publishable, review.reviewed_at
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'PERSON'
                  AND review.entity_id = person.id
                  AND review.source_document_id = snapshot.source_document_id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS person_review ON TRUE
            LEFT JOIN editorial_cases AS mandate_case
              ON mandate_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
             AND mandate_case.subject_type = '{_SUBJECT_TYPE}'
             AND mandate_case.subject_id = observation.id || ':' || situation.ordinality::text
             AND mandate_case.source_document_id = snapshot.source_document_id
            WHERE {" AND ".join(conditions)}
            ORDER BY snapshot.collected_at DESC,
                     LOWER(observation.parliamentary_name) COLLATE "C",
                     observation.source_id COLLATE "C",
                     situation.ordinality
            LIMIT ${limit_arg} OFFSET ${offset_arg}
            """,
            *arguments,
        )
        candidates = [self._candidate(row) for row in rows]
        if source_period_sha256 is not None:
            candidates = [
                item for item in candidates if item["source_period_sha256"] == source_period_sha256
            ]
        total = int(rows[0]["total_count"]) if rows else 0
        return candidates, (len(candidates) if source_period_sha256 is not None else total)

    @staticmethod
    def _candidate(row: Mapping[str, Any]) -> dict[str, object]:
        blocked: list[str] = []
        warnings = [
            "A situação é uma observação oficial e só pode ganhar significado de mandato "
            "depois de revisão humana específica.",
            "A ausência de uma data ou de um identificador significa dados indisponíveis.",
        ]
        try:
            period = _json_object(row["period"])
            if set(period) - {"description", "starts_at", "ends_at"}:
                raise ValueError("A situação contém campos fora do contrato V5.27")
            description = period.get("description")
            if not isinstance(description, str) or not description.strip():
                raise ValueError("A situação perdeu a designação oficial")
            starts_at = _parse_date(period.get("starts_at"))
            ends_at = _parse_date(period.get("ends_at"))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            description = "Dados indisponíveis"
            starts_at = ends_at = None
            blocked.append(f"Estrutura do intervalo inválida: {exc}")

        normalized_period = {
            "description": description.strip(),
            "starts_at": _iso(starts_at) if starts_at is not None else None,
            "ends_at": _iso(ends_at) if ends_at is not None else None,
        }
        source_period_sha256 = _sha256_json(normalized_period)
        expected_counts = {
            "deputies": int(row["manifest_deputy_count"]),
            "group_periods": int(row["manifest_group_period_count"]),
            "situation_periods": int(row["manifest_situation_period_count"]),
            "office_periods": int(row["manifest_office_period_count"]),
        }
        actual_counts = {
            "deputies": int(row["deputy_count"]),
            "group_periods": int(row["group_period_count"]),
            "situation_periods": int(row["situation_period_count"]),
            "office_periods": int(row["office_period_count"]),
        }
        if expected_counts != actual_counts:
            blocked.append("As contagens materializadas divergem do manifesto imutável.")
        if _normalise_key(str(description)) not in _SERVING_SITUATIONS:
            blocked.append("A designação não identifica um período de exercício elegível.")
        if starts_at is None:
            blocked.append("A data oficial de início está indisponível.")
        if starts_at is not None and ends_at is not None and ends_at < starts_at:
            blocked.append("A data final antecede a data inicial na fonte.")
        if row["constituency_source_id"] is None or row["constituency_label"] is None:
            blocked.append("O círculo não tem simultaneamente identificador e designação oficiais.")
        if row["person_id"] is None or row["membership_id"] is None:
            blocked.append("A identidade exata ainda não tem fotografia parlamentar publicada.")
        if row["person_reviewed_at"] is None or row["person_publishable"] is not True:
            blocked.append("A última revisão pública da identidade não está disponível.")

        subject_id = f"{row['observation_id']}:{int(row['period_ordinal'])}"
        if len(subject_id) > 200:
            blocked.append("A referência interna do intervalo excede o limite editorial.")
        return {
            "subject_id": subject_id,
            "source_period_ordinal": int(row["period_ordinal"]),
            "observation_id": str(row["observation_id"]),
            "source_document_id": str(row["source_document_id"]),
            "snapshot_id": str(row["snapshot_id"]),
            "official_deputy_id": str(row["source_id"]),
            "parliamentary_name": str(row["parliamentary_name"]),
            "full_name": row["full_name"],
            "legislature": str(row["legislature"]),
            "constituency": {
                "source_id": row["constituency_source_id"],
                "label": row["constituency_label"],
            },
            "source_period": normalized_period,
            "source_period_sha256": source_period_sha256,
            "snapshot": {
                "parser_version": str(row["parser_version"]),
                "normalised_sha256": str(row["normalised_sha256"]),
                "collected_at": _iso(row["collected_at"]),
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
            "manifest_counts": expected_counts,
            "materialised_counts": actual_counts,
            "identity_publication_ready": (
                row["person_id"] is not None
                and row["membership_id"] is not None
                and row["person_reviewed_at"] is not None
                and row["person_publishable"] is True
            ),
            "existing_case": _case_reference(row),
            "blocked_reasons": blocked,
            "warnings": warnings,
            "proposal_eligible": not blocked,
            "public_projection_allowed": False,
            "party_inference_allowed": False,
        }

    @staticmethod
    def _normalized_proposal(candidate: dict[str, object]) -> dict[str, Any]:
        constituency = candidate["constituency"]
        source = candidate["source"]
        archive = candidate["archive"]
        snapshot = candidate["snapshot"]
        assert isinstance(constituency, dict)
        assert isinstance(source, dict)
        assert isinstance(archive, dict)
        assert isinstance(snapshot, dict)
        return {
            "schema_version": _SCHEMA_VERSION,
            "mandate_candidate": {
                "office_title_candidate": "Deputado à Assembleia da República",
                "legislature": candidate["legislature"],
                "source_situation": candidate["source_period"],
                "source_period_sha256": candidate["source_period_sha256"],
                "meaning": "SOURCE_PERIOD_REQUIRING_HUMAN_MANDATE_REVIEW",
                "constituency": {
                    "official_id_reference_sha256": _reference_sha256(constituency["source_id"]),
                    "label": constituency["label"],
                },
                "party": {
                    "state": "DATA_UNAVAILABLE_FOR_THIS_GATE",
                    "inference_allowed": False,
                },
            },
            "identity_proof": {
                "official_deputy_id_reference_sha256": _reference_sha256(
                    candidate["official_deputy_id"]
                ),
                "observation_reference_sha256": _reference_sha256(candidate["observation_id"]),
                "snapshot_reference_sha256": _reference_sha256(candidate["snapshot_id"]),
                "parliamentary_name": candidate["parliamentary_name"],
                "identity_publication_ready": candidate["identity_publication_ready"],
            },
            "source_proof": {
                "source_document_reference_sha256": _reference_sha256(
                    candidate["source_document_id"]
                ),
                "url": source["url"],
                "retrieved_at": source["retrieved_at"],
                "content_sha256": source["content_sha256"],
                "archive_attestation_sha256": archive["attestation_sha256"],
                "archive_byte_size": archive["byte_size"],
                "snapshot_normalised_sha256": snapshot["normalised_sha256"],
                "parser_version": snapshot["parser_version"],
                "collected_at": snapshot["collected_at"],
            },
            "manifest_counts": candidate["manifest_counts"],
            "materialised_counts": candidate["materialised_counts"],
            "limitations": candidate["warnings"],
            "identity_rule": "EXACT_AR_DEP_ID_ONLY",
            "period_semantics": "HUMAN_REVIEW_REQUIRED",
            "public_projection_allowed": False,
            "party_inference_allowed": False,
            "publication": {
                "state": "PRIVATE_PENDING_REVIEW",
                "automatic_publication": False,
                "human_review_required": True,
                "mandate_creation_performed": False,
                "public_review_created": False,
                "publication_event_created": False,
            },
        }
