"""Adaptador privado entre observações oficiais de deputados e revisão editorial."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.models.editorial import (
    EditorialCaseKind,
    PoliticianProfileEditorialProposalRequest,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialRepository,
    EditorialSourceError,
)

_INGESTION_ALIAS = "parliament-deputy-ingestion"
_SUBJECT_TYPE = "PARLIAMENT_DEPUTY_OBSERVATION"
_SCHEMA_VERSION = "politician-profile-editorial-v1"


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


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


def _json_array(value: object) -> list[dict[str, Any]]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, list) or any(not isinstance(item, dict) for item in decoded):
        raise ValueError("O período parlamentar privado deixou de ser uma lista de objetos")
    return [dict(item) for item in decoded]


def _parse_period_date(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Uma data observada deixou de ter o formato textual esperado")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Uma data observada deixou de ser ISO-8601 válida") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _periods(
    value: object,
    *,
    label_key: str,
    identifier_key: str | None,
) -> tuple[list[dict[str, Any]], int, int]:
    periods = _json_array(value)
    normalised: list[dict[str, Any]] = []
    inverted = 0
    missing_identifiers = 0
    allowed = {label_key, "starts_at", "ends_at"}
    if identifier_key is not None:
        allowed.add(identifier_key)

    for item in periods:
        if set(item) - allowed:
            raise ValueError("Um período contém campos que não pertencem ao contrato V5.27")
        label = item.get(label_key)
        if not isinstance(label, str) or not label.strip():
            raise ValueError("Um período perdeu o respetivo rótulo oficial")
        starts_at = _parse_period_date(item.get("starts_at"))
        ends_at = _parse_period_date(item.get("ends_at"))
        if starts_at is not None and ends_at is not None and ends_at < starts_at:
            inverted += 1

        entry: dict[str, Any] = {
            label_key: label.strip(),
            "starts_at": _iso(starts_at) if starts_at is not None else None,
            "ends_at": _iso(ends_at) if ends_at is not None else None,
        }
        if identifier_key is not None:
            source_id = item.get(identifier_key)
            if source_id is None:
                missing_identifiers += 1
                entry[identifier_key] = None
            elif not isinstance(source_id, str) or not source_id.strip():
                raise ValueError("Um identificador oficial de período é inválido")
            else:
                entry[identifier_key] = source_id.strip()
        normalised.append(entry)
    return normalised, inverted, missing_identifiers


def _case_reference(row: Mapping[str, Any]) -> dict[str, object] | None:
    if row["case_id"] is None:
        return None
    return {
        "id": str(row["case_id"]),
        "state": str(row["case_state"]),
        "revision": int(row["case_revision"]),
        "origin": str(row["case_origin"]),
    }


class PoliticianProfileEditorialRepository:
    """Reprova a fonte e cria somente casos ``PENDING`` de perfis políticos."""

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
        normalised_legislature = legislature.strip() if legislature else None
        normalised_query = query.strip() if query else None
        normalised_legislature = normalised_legislature or None
        normalised_query = normalised_query or None
        items, total = await self._load_candidates(
            legislature=normalised_legislature,
            query=normalised_query,
            observation_id=None,
            limit=limit,
            offset=offset,
        )
        if not items and offset:
            _first_page, total = await self._load_candidates(
                legislature=normalised_legislature,
                query=normalised_query,
                observation_id=None,
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
                "A pesquisa filtra observações já separadas por DepId; não liga pessoas por nome."
            ),
        }

    async def snapshot_candidates(self, *, snapshot_id: str) -> list[dict[str, object]]:
        """Reconstrói uma fotografia inteira para uma inspeção privada de publicação."""

        items, total = await self._load_candidates(
            legislature=None,
            query=None,
            observation_id=None,
            limit=500,
            offset=0,
            snapshot_id=snapshot_id,
        )
        if total > 500 or len(items) != total:
            raise EditorialSourceError(
                "A fotografia de deputados excede o limite seguro ou não foi lida por inteiro"
            )
        return items

    async def create_proposal(
        self,
        *,
        payload: PoliticianProfileEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        candidates, _total = await self._load_candidates(
            legislature=None,
            query=None,
            observation_id=payload.observation_id,
            limit=1,
            offset=0,
        )
        if not candidates:
            raise EditorialSourceError(
                "A observação de deputado não existe ou perdeu a prova oficial atestada"
            )
        candidate = candidates[0]
        if candidate["proposal_eligible"] is not True:
            raise EditorialSourceError(
                "A observação diverge do manifesto privado e não pode entrar na fila editorial"
            )

        case, created = await self.editorial.create_ingestion_case(
            kind=EditorialCaseKind.POLITICIAN_PROFILE,
            subject_type=_SUBJECT_TYPE,
            subject_id=payload.observation_id,
            source_document_id=str(candidate["source_document_id"]),
            normalized_data=self._normalized_proposal(candidate),
            origin_alias=_INGESTION_ALIAS,
            submission_rationale=(
                "Observação parlamentar oficial enviada para revisão privada por DepId exato; "
                "não cria pessoa, mandato, filiação, publicação ou inferência individual."
            ),
            actor=actor,
        )
        return {
            "created": created,
            "case": case,
            "state": "PRIVATE_PENDING_REVIEW",
            "publication_performed": False,
            "person_created": False,
            "mandate_created": False,
        }

    async def _load_candidates(
        self,
        *,
        legislature: str | None,
        query: str | None,
        observation_id: str | None,
        limit: int,
        offset: int,
        snapshot_id: str | None = None,
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
        if snapshot_id:
            arguments.append(snapshot_id)
            conditions.append(f"snapshot.id = ${len(arguments)}")
        arguments.extend([limit, offset])
        limit_arg = len(arguments) - 1
        offset_arg = len(arguments)

        rows = await self.pool.fetch(
            f"""
            WITH materialised AS (
                SELECT
                    candidate.snapshot_id,
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
            SELECT
                observation.id AS observation_id,
                observation.source_id,
                observation.candidate_source_id,
                observation.parliamentary_name,
                observation.full_name,
                observation.constituency_source_id,
                observation.constituency_label,
                observation.parliamentary_groups,
                observation.mandate_situations,
                observation.offices,
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
                editorial_case.id AS case_id,
                editorial_case.current_state AS case_state,
                editorial_case.revision AS case_revision,
                editorial_case.origin AS case_origin,
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
            LEFT JOIN editorial_cases AS editorial_case
              ON editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
             AND editorial_case.subject_type = '{_SUBJECT_TYPE}'
             AND editorial_case.subject_id = observation.id
             AND editorial_case.source_document_id = snapshot.source_document_id
            WHERE {" AND ".join(conditions)}
            ORDER BY snapshot.collected_at DESC,
                     LOWER(observation.parliamentary_name) COLLATE "C",
                     observation.source_id COLLATE "C",
                     observation.id
            LIMIT ${limit_arg} OFFSET ${offset_arg}
            """,
            *arguments,
        )
        if not rows:
            return [], 0
        return [self._candidate(row) for row in rows], int(rows[0]["total_count"])

    @staticmethod
    def _candidate(row: Mapping[str, Any]) -> dict[str, object]:
        warnings: list[str] = []
        structure_valid = True
        try:
            groups, inverted_groups, groups_without_ids = _periods(
                row["parliamentary_groups"],
                label_key="short_name",
                identifier_key="source_id",
            )
            situations, inverted_situations, _ = _periods(
                row["mandate_situations"],
                label_key="description",
                identifier_key=None,
            )
            offices, inverted_offices, offices_without_ids = _periods(
                row["offices"],
                label_key="title",
                identifier_key="source_id",
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            groups, situations, offices = [], [], []
            inverted_groups = inverted_situations = inverted_offices = 0
            groups_without_ids = offices_without_ids = 0
            structure_valid = False
            warnings.append(f"Estrutura privada inválida: {exc}")

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
        manifest_matches = expected_counts == actual_counts
        if not manifest_matches:
            warnings.append(
                "As contagens materializadas divergem do manifesto; a proposta está bloqueada."
            )

        inverted_count = inverted_groups + inverted_situations + inverted_offices
        if inverted_count:
            warnings.append(
                f"{inverted_count} intervalo(s) têm fim anterior ao início tal como na fonte; "
                "não podem originar mandatos."
            )
        if row["candidate_source_id"] is None:
            warnings.append("Identificador oficial de candidatura: dados indisponíveis.")
        if row["constituency_source_id"] is None:
            warnings.append("Identificador oficial de círculo: dados indisponíveis.")
        if groups_without_ids:
            warnings.append(
                f"{groups_without_ids} período(s) de grupo não têm identificador oficial."
            )
        if offices_without_ids:
            warnings.append(
                f"{offices_without_ids} cargo(s) parlamentar(es) não têm identificador oficial."
            )
        if not situations:
            warnings.append("Situações parlamentares: dados indisponíveis.")
        warnings.append(
            "Uma observação parlamentar não prova o início, fim ou continuidade de um mandato."
        )

        observation_payload = {
            "source_id": str(row["source_id"]),
            "candidate_source_id": row["candidate_source_id"],
            "parliamentary_name": str(row["parliamentary_name"]),
            "full_name": row["full_name"],
            "constituency_source_id": row["constituency_source_id"],
            "constituency_label": row["constituency_label"],
            "parliamentary_groups": groups,
            "mandate_situations": situations,
            "offices": offices,
        }

        return {
            "observation_id": str(row["observation_id"]),
            "source_document_id": str(row["source_document_id"]),
            "snapshot_id": str(row["snapshot_id"]),
            "official_deputy_id": str(row["source_id"]),
            "official_candidate_id": row["candidate_source_id"],
            "parliamentary_name": str(row["parliamentary_name"]),
            "full_name": row["full_name"],
            "legislature": str(row["legislature"]),
            "constituency": {
                "source_id": row["constituency_source_id"],
                "label": row["constituency_label"],
            },
            "parliamentary_groups": groups,
            "mandate_situations": situations,
            "offices": offices,
            "observation_sha256": _sha256_json(observation_payload),
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
            "manifest_matches": manifest_matches,
            "structure_valid": structure_valid,
            "warnings": warnings,
            "editorial_case": _case_reference(row),
            "proposal_eligible": manifest_matches and structure_valid,
            "mandate_inference_allowed": False,
            "publication_state": "PRIVATE_ONLY",
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

        def reference(value: object) -> str | None:
            return _reference_sha256(value) if value is not None else None

        def protected_periods(
            values: object,
            *,
            label_key: str,
        ) -> list[dict[str, object]]:
            assert isinstance(values, list)
            result: list[dict[str, object]] = []
            for item in values:
                assert isinstance(item, dict)
                result.append(
                    {
                        label_key: item[label_key],
                        "official_id_reference_sha256": reference(item.get("source_id")),
                        "starts_at": item["starts_at"],
                        "ends_at": item["ends_at"],
                    }
                )
            return result

        situations = candidate["mandate_situations"]
        assert isinstance(situations, list)
        return {
            "schema_version": _SCHEMA_VERSION,
            "identity_observation": {
                "official_deputy_id_reference_sha256": _reference_sha256(
                    candidate["official_deputy_id"]
                ),
                "official_candidate_id_reference_sha256": reference(
                    candidate["official_candidate_id"]
                ),
                "parliamentary_name": candidate["parliamentary_name"],
                "full_name": candidate["full_name"],
                "legislature": candidate["legislature"],
                "constituency": {
                    "official_id_reference_sha256": reference(constituency.get("source_id")),
                    "label": constituency.get("label"),
                },
                "parliamentary_groups": protected_periods(
                    candidate["parliamentary_groups"],
                    label_key="short_name",
                ),
                "mandate_situations": [
                    {
                        "description": item["description"],
                        "starts_at": item["starts_at"],
                        "ends_at": item["ends_at"],
                        "meaning": "SOURCE_OBSERVATION_ONLY",
                    }
                    for item in situations
                ],
                "offices": protected_periods(candidate["offices"], label_key="title"),
            },
            "observation_proof": {
                "observation_reference_sha256": _reference_sha256(candidate["observation_id"]),
                "observation_sha256": candidate["observation_sha256"],
                "snapshot_reference_sha256": _reference_sha256(candidate["snapshot_id"]),
                "snapshot_normalised_sha256": snapshot["normalised_sha256"],
                "parser_version": snapshot["parser_version"],
                "collected_at": snapshot["collected_at"],
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
            },
            "manifest_counts": candidate["manifest_counts"],
            "materialised_counts": candidate["materialised_counts"],
            "limitations": candidate["warnings"],
            "identity_rule": "EXACT_AR_DEP_ID_ONLY",
            "mandate_inference_allowed": False,
            "publication": {
                "state": "PRIVATE_PENDING_REVIEW",
                "automatic_publication": False,
                "human_review_required": True,
                "person_creation_performed": False,
                "mandate_creation_performed": False,
                "membership_creation_performed": False,
            },
        }
