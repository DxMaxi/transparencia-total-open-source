"""Porta privada entre reuniões oficiais de presenças e revisão humana."""

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.models.editorial import (
    EditorialCaseKind,
    PoliticianAttendanceEditorialProposalRequest,
    StaffSession,
)
from app.repositories.editorial import EditorialRepository, EditorialSourceError
from app.services.parliament_attendance import PARLIAMENT_ATTENDANCE_PARSER_VERSION

_INGESTION_ALIAS = "parliament-attendance-ingestion"
_SUBJECT_TYPE = "PARLIAMENT_ATTENDANCE_SNAPSHOT"
_SCHEMA_VERSION = "politician-attendance-editorial-v1"


def _reference_sha256(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


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


class PoliticianAttendanceEditorialRepository:
    """Cria um único caso privado por reunião integral, sem seleção individual."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    async def list_candidates(
        self,
        *,
        legislature: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        items, total = await self._load_candidates(
            legislature=legislature.strip() if legislature and legislature.strip() else None,
            snapshot_id=None,
            limit=limit,
            offset=offset,
        )
        if not items and offset:
            _first, total = await self._load_candidates(
                legislature=legislature.strip() if legislature and legislature.strip() else None,
                snapshot_id=None,
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
            "selection_rule": (
                "A reunião é revista como fotografia integral; nenhum deputado pode ser "
                "omitido ou promovido isoladamente e nenhuma associação é feita por nome."
            ),
        }

    async def create_proposal(
        self,
        *,
        payload: PoliticianAttendanceEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        candidates, _total = await self._load_candidates(
            legislature=None,
            snapshot_id=payload.snapshot_id,
            limit=1,
            offset=0,
        )
        if not candidates:
            raise EditorialSourceError(
                "A reunião de presenças não existe ou não possui arquivo oficial atestado"
            )
        candidate = candidates[0]
        if candidate["proposal_eligible"] is not True:
            reasons = candidate["blocked_reasons"]
            detail = (
                "; ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else ""
            )
            raise EditorialSourceError(
                "A reunião não reúne prova suficiente para revisão integral"
                + (f": {detail}" if detail else "")
            )

        observations = await self._load_observations(payload.snapshot_id)
        record_count = candidate["record_count"]
        if not isinstance(record_count, int):
            raise EditorialSourceError("O manifesto da reunião não contém uma contagem válida")
        if len(observations) != record_count:
            raise EditorialSourceError("A reunião deixou de corresponder ao manifesto imutável")
        case, created = await self.editorial.create_ingestion_case(
            kind=EditorialCaseKind.POLITICIAN_PROFILE,
            subject_type=_SUBJECT_TYPE,
            subject_id=payload.snapshot_id,
            source_document_id=str(candidate["source_document_id"]),
            normalized_data=self._normalized_proposal(candidate, observations),
            origin_alias=_INGESTION_ALIAS,
            submission_rationale=(
                "Reunião plenária oficial completa enviada para revisão privada; os registos "
                "foram preservados por BID exato, sem correspondência por nome, sem interpretar "
                "falta como incumprimento e sem criar presença pública."
            ),
            actor=actor,
        )
        return {
            "created": created,
            "case": case,
            "state": "PRIVATE_PENDING_REVIEW",
            "publication_performed": False,
            "session_created": False,
            "attendance_records_created": 0,
            "public_reviews_created": 0,
            "selective_processing_allowed": False,
        }

    async def _load_candidates(
        self,
        *,
        legislature: str | None,
        snapshot_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, object]], int]:
        conditions = [
            "source.publisher = 'PARLIAMENT'",
            "source.kind = 'ATTENDANCE'",
            "source.url LIKE 'https://%'",
            "snapshot.parser_version = $1",
        ]
        arguments: list[object] = [PARLIAMENT_ATTENDANCE_PARSER_VERSION]
        if legislature:
            arguments.append(legislature)
            conditions.append(f"snapshot.legislature = ${len(arguments)}")
        if snapshot_id:
            arguments.append(snapshot_id)
            conditions.append(f"snapshot.id = ${len(arguments)}")
        arguments.extend([limit, offset])
        limit_arg = len(arguments) - 1
        offset_arg = len(arguments)

        rows = await self.pool.fetch(
            f"""
            SELECT snapshot.id,
                   snapshot.source_document_id,
                   snapshot.legislature,
                   snapshot.official_meeting_id,
                   snapshot.meeting_date,
                   snapshot.meeting_type,
                   snapshot.session_number,
                   snapshot.parser_version,
                   snapshot.normalised_sha256,
                   snapshot.collected_at,
                   snapshot.record_count,
                   snapshot.present_count,
                   snapshot.justified_absence_count,
                   snapshot.unjustified_absence_count,
                   snapshot.unknown_count,
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
                   materialised.record_count AS actual_record_count,
                   materialised.present_count AS actual_present_count,
                   materialised.justified_absence_count AS actual_justified_absence_count,
                   materialised.unjustified_absence_count
                       AS actual_unjustified_absence_count,
                   materialised.unknown_count AS actual_unknown_count,
                   reconciliation.identity_count,
                   reconciliation.reviewed_identity_count,
                   reconciliation.exact_mandate_count,
                   reconciliation.reviewed_mandate_count,
                   attendance_case.id AS case_id,
                   attendance_case.current_state AS case_state,
                   attendance_case.revision AS case_revision,
                   attendance_case.origin AS case_origin,
                   (COUNT(*) OVER())::int AS total_count
            FROM parliament_attendance_snapshots AS snapshot
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
                SELECT COUNT(*)::int AS record_count,
                       COUNT(*) FILTER (WHERE status = 'PRESENT')::int AS present_count,
                       COUNT(*) FILTER (
                           WHERE status = 'JUSTIFIED_ABSENCE'
                       )::int AS justified_absence_count,
                       COUNT(*) FILTER (
                           WHERE status = 'UNJUSTIFIED_ABSENCE'
                       )::int AS unjustified_absence_count,
                       COUNT(*) FILTER (WHERE status = 'UNKNOWN')::int AS unknown_count
                FROM parliament_attendance_observations AS observation
                WHERE observation.snapshot_id = snapshot.id
            ) AS materialised ON TRUE
            JOIN LATERAL (
                SELECT COUNT(*) FILTER (
                           WHERE exact_person.person_id IS NOT NULL
                       )::int AS identity_count,
                       COUNT(*) FILTER (
                           WHERE exact_person.identity_publishable IS TRUE
                       )::int AS reviewed_identity_count,
                       COUNT(*) FILTER (
                           WHERE exact_person.covering_mandate_count = 1
                       )::int AS exact_mandate_count,
                       COUNT(*) FILTER (
                           WHERE exact_person.reviewed_covering_mandate_count = 1
                       )::int AS reviewed_mandate_count
                FROM parliament_attendance_observations AS observation
                LEFT JOIN LATERAL (
                    SELECT person.id AS person_id,
                           identity_review.publishable AS identity_publishable,
                           (
                               SELECT COUNT(*)
                               FROM mandates AS mandate
                               WHERE mandate.person_id = person.id
                                 AND mandate.legislature = snapshot.legislature
                                 AND mandate.started_at::date <= snapshot.meeting_date
                                 AND (
                                     mandate.ended_at IS NULL
                                     OR mandate.ended_at::date >= snapshot.meeting_date
                                 )
                           )::int AS covering_mandate_count,
                           (
                               SELECT COUNT(*)
                               FROM mandates AS mandate
                               JOIN LATERAL (
                                   SELECT review.publishable
                                   FROM data_publication_reviews AS review
                                   WHERE review.entity_type = 'MANDATE'
                                     AND review.entity_id = mandate.id
                                     AND review.source_document_id = mandate.source_document_id
                                   ORDER BY review.reviewed_at DESC, review.id DESC
                                   LIMIT 1
                               ) AS mandate_review ON mandate_review.publishable = TRUE
                               WHERE mandate.person_id = person.id
                                 AND mandate.legislature = snapshot.legislature
                                 AND mandate.started_at::date <= snapshot.meeting_date
                                 AND (
                                     mandate.ended_at IS NULL
                                     OR mandate.ended_at::date >= snapshot.meeting_date
                                 )
                           )::int AS reviewed_covering_mandate_count
                    FROM people AS person
                    LEFT JOIN LATERAL (
                        SELECT review.publishable
                        FROM data_publication_reviews AS review
                        WHERE review.entity_type = 'PERSON'
                          AND review.entity_id = person.id
                        ORDER BY review.reviewed_at DESC, review.id DESC
                        LIMIT 1
                    ) AS identity_review ON TRUE
                    WHERE person.source_id = observation.official_deputy_id
                    LIMIT 1
                ) AS exact_person ON TRUE
                WHERE observation.snapshot_id = snapshot.id
            ) AS reconciliation ON TRUE
            LEFT JOIN editorial_cases AS attendance_case
              ON attendance_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
             AND attendance_case.subject_type = '{_SUBJECT_TYPE}'
             AND attendance_case.subject_id = snapshot.id
             AND attendance_case.source_document_id = snapshot.source_document_id
            WHERE {" AND ".join(conditions)}
            ORDER BY snapshot.meeting_date DESC, snapshot.official_meeting_id DESC
            LIMIT ${limit_arg} OFFSET ${offset_arg}
            """,
            *arguments,
        )
        items = [self._candidate(row) for row in rows]
        total = int(rows[0]["total_count"]) if rows else 0
        return items, total

    async def _load_observations(self, snapshot_id: str) -> list[dict[str, object]]:
        rows = await self.pool.fetch(
            """
            SELECT official_deputy_id, parliamentary_name,
                   parliamentary_group_label, status, source_status_label,
                   source_status_code, absence_reason, source_record_sha256
            FROM parliament_attendance_observations
            WHERE snapshot_id = $1
            ORDER BY LOWER(parliamentary_name) COLLATE "C",
                     official_deputy_id COLLATE "C"
            """,
            snapshot_id,
        )
        return [
            {
                "official_deputy_id_reference_sha256": _reference_sha256(row["official_deputy_id"]),
                "parliamentary_name": str(row["parliamentary_name"]),
                "parliamentary_group_label": row["parliamentary_group_label"],
                "status": str(row["status"]),
                "source_status_label": str(row["source_status_label"]),
                "source_status_code": row["source_status_code"],
                "absence_reason": row["absence_reason"],
                "source_record_sha256": str(row["source_record_sha256"]),
            }
            for row in rows
        ]

    @staticmethod
    def _candidate(row: Mapping[str, Any]) -> dict[str, object]:
        expected_counts = {
            "records": int(row["record_count"]),
            "present": int(row["present_count"]),
            "justified_absence": int(row["justified_absence_count"]),
            "unjustified_absence": int(row["unjustified_absence_count"]),
            "unknown": int(row["unknown_count"]),
        }
        actual_counts = {
            "records": int(row["actual_record_count"]),
            "present": int(row["actual_present_count"]),
            "justified_absence": int(row["actual_justified_absence_count"]),
            "unjustified_absence": int(row["actual_unjustified_absence_count"]),
            "unknown": int(row["actual_unknown_count"]),
        }
        blocked: list[str] = []
        warnings = [
            "Uma falta é apenas o estado publicado pela fonte nesta reunião; não constitui "
            "automaticamente incumprimento, culpa ou ausência noutro trabalho parlamentar.",
            "A fotografia só poderá ser publicada integralmente e por BID exato.",
        ]
        if expected_counts != actual_counts:
            blocked.append("As contagens materializadas divergem do manifesto imutável.")

        record_count = expected_counts["records"]
        identity_count = int(row["identity_count"])
        reviewed_identity_count = int(row["reviewed_identity_count"])
        exact_mandate_count = int(row["exact_mandate_count"])
        reviewed_mandate_count = int(row["reviewed_mandate_count"])
        publication_blockers: list[str] = []
        if expected_counts["unknown"]:
            publication_blockers.append(
                "Existem estados UNKNOWN que exigem correção da fonte ou do parser."
            )
        if identity_count != record_count:
            publication_blockers.append(
                f"{record_count - identity_count} BID não têm identidade pública exata."
            )
        if reviewed_identity_count != record_count:
            publication_blockers.append(
                f"{record_count - reviewed_identity_count} identidades não têm revisão "
                "pública positiva."
            )
        if exact_mandate_count != record_count:
            publication_blockers.append(
                f"{record_count - exact_mandate_count} registos não têm exatamente um mandato "
                "oficial a cobrir a data."
            )
        if reviewed_mandate_count != record_count:
            publication_blockers.append(
                f"{record_count - reviewed_mandate_count} registos não têm mandato revisto "
                "positivamente para a data."
            )
        return {
            "snapshot_id": str(row["id"]),
            "source_document_id": str(row["source_document_id"]),
            "legislature": str(row["legislature"]),
            "official_meeting_id": str(row["official_meeting_id"]),
            "meeting_date": row["meeting_date"].isoformat(),
            "meeting_type": str(row["meeting_type"]),
            "session_number": row["session_number"],
            "parser_version": str(row["parser_version"]),
            "normalised_sha256": str(row["normalised_sha256"]),
            "collected_at": _iso(row["collected_at"]),
            "record_count": record_count,
            "manifest_counts": expected_counts,
            "materialised_counts": actual_counts,
            "identity_reconciliation": {
                "exact_identities": identity_count,
                "reviewed_identities": reviewed_identity_count,
                "exact_covering_mandates": exact_mandate_count,
                "reviewed_covering_mandates": reviewed_mandate_count,
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
            "publication_ready": not blocked and not publication_blockers,
            "public_projection_allowed": False,
            "selective_processing_allowed": False,
            "name_matching_allowed": False,
        }

    @staticmethod
    def _normalized_proposal(
        candidate: dict[str, object],
        observations: list[dict[str, object]],
    ) -> dict[str, Any]:
        source = candidate["source"]
        archive = candidate["archive"]
        assert isinstance(source, dict)
        assert isinstance(archive, dict)
        return {
            "schema_version": _SCHEMA_VERSION,
            "meeting": {
                "legislature": candidate["legislature"],
                "official_meeting_id_reference_sha256": _reference_sha256(
                    candidate["official_meeting_id"]
                ),
                "date": candidate["meeting_date"],
                "type": candidate["meeting_type"],
                "session_number": candidate["session_number"],
            },
            "manifest_counts": candidate["manifest_counts"],
            "materialised_counts": candidate["materialised_counts"],
            "identity_reconciliation": candidate["identity_reconciliation"],
            "records": observations,
            "source_proof": {
                "source_document_reference_sha256": _reference_sha256(
                    candidate["source_document_id"]
                ),
                "url": source["url"],
                "retrieved_at": source["retrieved_at"],
                "content_sha256": source["content_sha256"],
                "archive_attestation_sha256": archive["attestation_sha256"],
                "archive_byte_size": archive["byte_size"],
                "normalised_sha256": candidate["normalised_sha256"],
                "parser_version": candidate["parser_version"],
                "collected_at": candidate["collected_at"],
            },
            "limitations": candidate["warnings"],
            "publication_blockers": candidate["publication_blockers"],
            "identity_rule": "EXACT_AR_BID_ONLY",
            "absence_rule": "SOURCE_STATUS_IS_NOT_AUTOMATIC_NONCOMPLIANCE",
            "selection_rule": "WHOLE_MEETING_ONLY",
            "public_projection_allowed": False,
            "selective_processing_allowed": False,
            "name_matching_allowed": False,
            "publication": {
                "state": "PRIVATE_PENDING_REVIEW",
                "automatic_publication": False,
                "human_review_required": True,
                "session_creation_performed": False,
                "attendance_records_created": 0,
                "public_reviews_created": 0,
                "publication_event_created": False,
            },
        }
