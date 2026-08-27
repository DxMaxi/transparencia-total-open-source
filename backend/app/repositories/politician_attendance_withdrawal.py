"""Retirada transacional e imutável de uma reunião integral de presenças."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialState,
    PoliticianAttendanceWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.politician_attendance_editorial import (
    PoliticianAttendanceEditorialRepository,
    _reference_sha256,
)
from app.repositories.politician_attendance_publication import (
    _PROPOSAL_SCHEMA_VERSION,
    _SUBJECT_TYPE,
    PoliticianAttendancePublicationRepository,
    _attendance_mapping_sha256,
    _attendance_publication_proof_sha256,
    _canonical_json,
    _integer,
    _json_object,
    _meeting_datetime,
    _new_id,
    _optional_count,
    _publication_event_sha256,
    _sha256_json,
    _status_projection,
)

_WITHDRAWAL_SCHEMA_VERSION = "politician-attendance-withdrawal-v1"
_ALLOWED_STATUSES = frozenset({"PRESENT", "JUSTIFIED_ABSENCE", "UNJUSTIFIED_ABSENCE"})


def _json_object_or_none(value: object) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return dict(value) if isinstance(value, dict) else None


def _digest(value: object) -> str | None:
    text = str(value) if value is not None else ""
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else None


def _publication_effect(record_count: int) -> dict[str, int]:
    return {
        "sessions_to_create": 1,
        "attendance_records_to_create": record_count,
        "attendance_reviews_to_append": 1,
        "attendance_audits_to_append": 1,
        "editorial_decisions_to_append": 1,
        "publication_events_to_append": 1,
        "people_to_create": 0,
        "mandates_to_create": 0,
        "party_links_to_create": 0,
    }


class PoliticianAttendanceWithdrawalRepository:
    """Oculta uma reunião inteira e preserva todas as linhas e provas originais."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.candidates = PoliticianAttendanceEditorialRepository(pool)
        self.publisher = PoliticianAttendancePublicationRepository(pool)

    async def inspect(self, *, case_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            preview, _context = await self._inspect_context(
                connection,
                case_id=case_id,
                lock=False,
            )
            return preview

    async def _case(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> Mapping[str, Any]:
        if lock:
            locked = await connection.fetchval(
                "SELECT id FROM editorial_cases WHERE id = $1 FOR UPDATE",
                case_id,
            )
            if locked is None:
                raise EditorialNotFoundError("Processo editorial de presenças não encontrado")

        row = await connection.fetchrow(
            f"""
            SELECT editorial_case.id,
                   editorial_case.subject_id,
                   editorial_case.source_document_id,
                   editorial_case.origin::text AS origin,
                   editorial_case.current_state::text AS current_state,
                   editorial_case.revision,
                   editorial_case.current_version_id,
                   version.normalized_json,
                   version.normalized_sha256,
                   latest_decision.action::text AS latest_decision_action,
                   latest_decision.resulting_state::text AS latest_decision_state,
                   latest_decision.case_revision AS latest_decision_case_revision,
                   latest_decision.version_id AS latest_decision_version_id,
                   latest_decision.source_confirmed AS latest_source_confirmed,
                   source.publisher::text AS source_publisher,
                   source.kind::text AS source_kind,
                   source.url AS source_url,
                   source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256,
                   archive.id AS archive_id,
                   archive.attestation_sha256 AS archive_attestation_sha256,
                   publication.id AS publication_event_id,
                   publication.version_id AS publication_event_version_id,
                   publication.target_type AS publication_event_target_type,
                   publication.target_id AS publication_event_target_id,
                   publication.rationale AS publication_event_rationale,
                   publication.actor_id AS publication_event_actor_id,
                   publication.actor_alias AS publication_event_actor_alias,
                   publication.event_sha256 AS publication_event_sha256,
                   publication.created_at AS publication_event_created_at,
                   withdrawal.id AS withdrawal_event_id,
                   session.id AS session_id,
                   session.source_id AS session_source_id,
                   session.legislature AS session_legislature,
                   session.session_number,
                   session.title AS session_title,
                   session.starts_at AS session_starts_at,
                   session.snapshot_id AS activity_snapshot_id,
                   session.attendance_snapshot_id,
                   session.source_document_id AS session_source_document_id,
                   public_review.id AS public_review_id,
                   public_review.publishable AS public_publishable,
                   public_review.reviewed_at AS public_reviewed_at,
                   publication_audit.id AS publication_audit_event_id,
                   publication_audit.before_json AS publication_audit_before_json,
                   publication_audit.after_json AS publication_audit_after_json,
                   publication_audit.created_at AS publication_audit_created_at
            FROM editorial_cases AS editorial_case
            JOIN editorial_versions AS version
              ON version.id = editorial_case.current_version_id
             AND version.case_id = editorial_case.id
            JOIN source_documents AS source
              ON source.id = editorial_case.source_document_id
            LEFT JOIN LATERAL (
                SELECT decision.action,
                       decision.resulting_state,
                       decision.case_revision,
                       decision.version_id,
                       decision.source_confirmed
                FROM editorial_decisions AS decision
                WHERE decision.case_id = editorial_case.id
                ORDER BY decision.case_revision DESC, decision.id DESC
                LIMIT 1
            ) AS latest_decision ON TRUE
            LEFT JOIN LATERAL (
                SELECT attestation.id, attestation.attestation_sha256
                FROM source_archive_attestations AS attestation
                WHERE attestation.source_document_id = source.id
                  AND attestation.content_sha256 = source.content_sha256
                  AND attestation.retrieval_url = source.url
                  AND attestation.retrieved_at = source.retrieved_at
                ORDER BY attestation.archived_at ASC, attestation.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id,
                       event.version_id,
                       event.target_type,
                       event.target_id,
                       event.rationale,
                       event.actor_id,
                       event.actor_alias,
                       event.event_sha256,
                       event.created_at
                FROM editorial_publication_events AS event
                WHERE event.case_id = editorial_case.id
                  AND event.version_id = editorial_case.current_version_id
                  AND event.action = 'PUBLISH'::"EditorialPublicationAction"
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS publication ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id
                FROM editorial_publication_events AS event
                WHERE event.case_id = editorial_case.id
                  AND event.version_id = editorial_case.current_version_id
                  AND event.action = 'WITHDRAW'::"EditorialPublicationAction"
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS withdrawal ON TRUE
            LEFT JOIN parliamentary_sessions AS session
              ON session.attendance_snapshot_id = editorial_case.subject_id
             AND session.source_document_id = editorial_case.source_document_id
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable, review.reviewed_at
                FROM data_publication_reviews AS review
                WHERE review.entity_type = '{_SUBJECT_TYPE}'
                  AND review.entity_id = editorial_case.subject_id
                  AND review.source_document_id = editorial_case.source_document_id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS public_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT audit.id, audit.before_json, audit.after_json, audit.created_at
                FROM audit_events AS audit
                WHERE audit.entity_type = '{_SUBJECT_TYPE}'
                  AND audit.entity_id = editorial_case.subject_id
                  AND audit.action = 'PUBLISHED'
                ORDER BY audit.created_at DESC, audit.id DESC
                LIMIT 1
            ) AS publication_audit ON TRUE
            WHERE editorial_case.id = $1
              AND editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
              AND editorial_case.subject_type = '{_SUBJECT_TYPE}'
            """,
            case_id,
        )
        if row is None:
            raise EditorialNotFoundError("Processo editorial de presenças não encontrado")

        if lock and row["session_id"] is not None:
            await connection.fetchval(
                "SELECT id FROM parliamentary_sessions WHERE id = $1 FOR UPDATE",
                str(row["session_id"]),
            )
            await connection.fetch(
                """
                SELECT id
                FROM attendance_records
                WHERE session_id = $1
                ORDER BY id COLLATE "C"
                FOR UPDATE
                """,
                str(row["session_id"]),
            )
        return cast(Mapping[str, Any], row)

    @staticmethod
    async def _records(
        connection: asyncpg.Connection,
        *,
        session_id: str,
    ) -> list[dict[str, object]]:
        rows = await connection.fetch(
            """
            SELECT id, mandate_id, session_id, present, absence_reason,
                   is_excused, source_document_id, source_observation_id,
                   source_record_sha256
            FROM attendance_records
            WHERE session_id = $1
            ORDER BY source_observation_id COLLATE "C", id COLLATE "C"
            """,
            session_id,
        )
        return [dict(row) for row in rows]

    @staticmethod
    def _mapping_blockers(rows: list[dict[str, object]]) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []

        def block(code: str, detail: str) -> None:
            if not any(item["code"] == code for item in blockers):
                blockers.append({"code": code, "detail": detail})

        for row in rows:
            if str(row["status"]) not in _ALLOWED_STATUSES:
                block("UNKNOWN_STATUS_PRESENT", "Existe um estado não publicável na reunião.")
            if row["person_id"] is None:
                block("EXACT_IDENTITY_MISSING", "Existe um BID sem identidade pública exata.")
                continue
            if str(row["person_role"] or "") != "DEPUTY" or row["person_active"] is not True:
                block("PERSON_NOT_ACTIVE_DEPUTY", "Uma identidade deixou de ser deputada ativa.")
            if not (row["identity_publishable"] is True and row["identity_proof_valid"] is True):
                block(
                    "IDENTITY_REVIEW_INVALID",
                    "Uma identidade deixou de ter revisão positiva e arquivo oficial válido.",
                )
            if _optional_count(row["mandate_count"]) != 1:
                block(
                    "EXACT_MANDATE_MISSING",
                    "Cada BID exige exatamente um mandato a cobrir a data da reunião.",
                )
            if _optional_count(row["reviewed_mandate_count"]) != 1 or row["mandate_id"] is None:
                block(
                    "MANDATE_REVIEW_INVALID",
                    "Um mandato deixou de ter revisão positiva e arquivo oficial válido.",
                )
        return blockers

    @staticmethod
    def _record_blockers(
        *,
        mappings: list[dict[str, object]],
        records: list[dict[str, object]],
        session_id: str,
        source_document_id: str,
    ) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []

        def block(code: str, detail: str) -> None:
            if not any(item["code"] == code for item in blockers):
                blockers.append({"code": code, "detail": detail})

        by_observation = {
            str(record["source_observation_id"]): record
            for record in records
            if record["source_observation_id"] is not None
        }
        if len(records) != len(mappings) or len(by_observation) != len(mappings):
            block(
                "PUBLIC_RECORD_SET_CHANGED",
                "As linhas públicas deixaram de corresponder à reunião integral.",
            )
        for mapping in mappings:
            observation_id = str(mapping["observation_id"])
            record = by_observation.get(observation_id)
            if record is None:
                block("PUBLIC_RECORD_MISSING", "Uma observação deixou de ter a linha publicada.")
                continue
            present, is_excused = _status_projection(mapping["status"])
            expected_reason = mapping["absence_reason"] if not present else None
            checks = (
                (str(record["id"]), str(mapping["existing_record_id"])),
                (str(record["mandate_id"]), str(mapping["mandate_id"])),
                (str(record["session_id"]), session_id),
                (record["present"], present),
                (record["absence_reason"], expected_reason),
                (record["is_excused"], is_excused),
                (str(record["source_document_id"]), source_document_id),
                (str(record["source_observation_id"]), observation_id),
                (str(record["source_record_sha256"]), str(mapping["source_record_sha256"])),
            )
            if any(received != expected for received, expected in checks):
                block(
                    "PUBLIC_RECORD_PROOF_MISMATCH",
                    "Uma linha publicada diverge da observação, mandato ou estado oficial.",
                )
        return blockers

    async def _inspect_context(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, object]]:
        case = await self._case(connection, case_id=case_id, lock=lock)
        snapshot_id = str(case["subject_id"])
        candidate = await self.candidates.get_exact_candidate(
            snapshot_id=snapshot_id,
            connection=connection,
        )
        if candidate is None:
            raise EditorialSourceError(
                "A reunião publicada deixou de corresponder à fonte oficial atestada"
            )
        normalized = _json_object(case["normalized_json"])
        proposal_observations = await self.candidates.load_proposal_observations(
            snapshot_id,
            connection=connection,
        )
        meeting_date = _meeting_datetime(candidate["meeting_date"])
        mappings = await self.publisher._load_mappings(
            snapshot_id=snapshot_id,
            legislature=str(candidate["legislature"]),
            meeting_date=meeting_date,
            connection=connection,
        )
        session_id = str(case["session_id"] or "")
        records = await self._records(connection, session_id=session_id) if session_id else []
        source = candidate["source"]
        manifest_counts = candidate["manifest_counts"]
        assert isinstance(source, dict)
        assert isinstance(manifest_counts, dict)
        record_count = _integer(candidate["record_count"], label="A contagem da reunião")

        blockers: list[dict[str, str]] = []

        def block(code: str, detail: str) -> None:
            blockers.append({"code": code, "detail": detail})

        if str(case["current_state"]) != EditorialState.PUBLISHED.value:
            block("CASE_NOT_PUBLISHED", "O processo tem de estar atualmente publicado.")
        if str(case["origin"]) != "INGESTION":
            block(
                "INVALID_CASE_ORIGIN",
                "A retirada exige um processo criado a partir da ingestão oficial.",
            )
        if not (
            str(case["latest_decision_action"] or "") == EditorialAction.PUBLISH.value
            and str(case["latest_decision_state"] or "") == EditorialState.PUBLISHED.value
            and int(case["latest_decision_case_revision"] or -1) == int(case["revision"])
            and str(case["latest_decision_version_id"] or "") == str(case["current_version_id"])
            and case["latest_source_confirmed"] is True
        ):
            block("LATEST_PUBLICATION_INVALID", "A decisão atual não prova esta publicação.")
        if normalized.get("schema_version") != _PROPOSAL_SCHEMA_VERSION:
            block("PROPOSAL_SCHEMA_INVALID", "A versão publicada usa outro contrato editorial.")
        expected_normalized = self.candidates._normalized_proposal(
            candidate,
            proposal_observations,
        )
        if normalized != expected_normalized:
            block(
                "PUBLISHED_VERSION_DRIFT",
                "A versão publicada diverge da prova oficial reconstruída no servidor.",
            )
        for detail in cast(list[object], candidate["blocked_reasons"]):
            block("SOURCE_CANDIDATE_BLOCKED", str(detail))
        for detail in cast(list[object], candidate["publication_blockers"]):
            block("SOURCE_PUBLICATION_BLOCKED", str(detail))
        if len(proposal_observations) != record_count or len(mappings) != record_count:
            block(
                "MEETING_NOT_COMPLETE",
                "As observações deixaram de corresponder à reunião integral.",
            )
        blockers.extend(self._mapping_blockers(mappings))
        blockers.extend(
            self._record_blockers(
                mappings=mappings,
                records=records,
                session_id=session_id,
                source_document_id=str(candidate["source_document_id"]),
            )
        )

        if case["withdrawal_event_id"] is not None:
            block("WITHDRAWAL_ALREADY_RECORDED", "A reunião já possui uma retirada imutável.")
        if not session_id:
            block("SESSION_MISSING", "A publicação original já não encontra a sessão.")
        session_checks = (
            (str(case["session_source_id"] or ""), str(candidate["official_meeting_id"])),
            (str(case["session_legislature"] or ""), str(candidate["legislature"])),
            (case["session_number"], candidate["session_number"]),
            (str(case["session_title"] or ""), f"Reunião plenária — {candidate['meeting_type']}"),
            (case["session_starts_at"], meeting_date),
            (case["activity_snapshot_id"], None),
            (str(case["attendance_snapshot_id"] or ""), snapshot_id),
            (
                str(case["session_source_document_id"] or ""),
                str(candidate["source_document_id"]),
            ),
        )
        if any(received != expected for received, expected in session_checks):
            block("SESSION_PROOF_MISMATCH", "A sessão publicada deixou de corresponder à reunião.")
        if str(case["source_document_id"]) != str(candidate["source_document_id"]):
            block("SOURCE_DOCUMENT_CHANGED", "O documento oficial do processo deixou de coincidir.")
        if case["archive_id"] is None:
            block("ARCHIVE_MISSING", "A atestação exata do arquivo deixou de estar disponível.")
        if (
            str(case["source_publisher"] or "") != "PARLIAMENT"
            or str(case["source_kind"] or "") != "ATTENDANCE"
        ):
            block(
                "SOURCE_NOT_OFFICIAL", "A origem deixou de ser uma fonte parlamentar de presenças."
            )
        if case["public_review_id"] is None or case["public_publishable"] is not True:
            block("PUBLIC_REVIEW_INACTIVE", "A revisão integral da reunião já não está ativa.")

        publication_event_sha256 = _digest(case["publication_event_sha256"])
        publication_created_at = case["publication_event_created_at"]
        if case["publication_event_id"] is None or not isinstance(publication_created_at, datetime):
            block("PUBLICATION_EVENT_MISSING", "O evento imutável de publicação está incompleto.")
        else:
            rebuilt_event = _publication_event_sha256(
                event_id=str(case["publication_event_id"]),
                case_id=case_id,
                version_id=str(case["publication_event_version_id"]),
                action="PUBLISH",
                target_id=str(case["publication_event_target_id"]),
                rationale=str(case["publication_event_rationale"]),
                actor_id=str(case["publication_event_actor_id"]),
                actor_alias=str(case["publication_event_actor_alias"]),
                created_at=publication_created_at,
            )
            if publication_event_sha256 != rebuilt_event:
                block(
                    "PUBLICATION_EVENT_HASH_MISMATCH",
                    "O evento de publicação deixou de corresponder ao seu SHA-256.",
                )
        if (
            str(case["publication_event_version_id"] or "") != str(case["current_version_id"])
            or str(case["publication_event_target_type"] or "") != _SUBJECT_TYPE
            or str(case["publication_event_target_id"] or "") != snapshot_id
        ):
            block(
                "PUBLICATION_EVENT_LINK_CHANGED",
                "O evento já não aponta para esta versão e reunião.",
            )

        mapping_sha256 = (
            _attendance_mapping_sha256(mappings)
            if not self._mapping_blockers(mappings) and len(mappings) == record_count
            else None
        )
        publication_proof_sha256 = (
            _attendance_publication_proof_sha256(
                case_id=case_id,
                version_id=case["current_version_id"],
                version_sha256=case["normalized_sha256"],
                source_sha256=source["content_sha256"],
                snapshot_id=snapshot_id,
                snapshot_sha256=candidate["normalised_sha256"],
                mapping_sha256=mapping_sha256,
                legislature=candidate["legislature"],
                meeting_date=candidate["meeting_date"],
                counts=manifest_counts,
                public_effect=_publication_effect(record_count),
            )
            if mapping_sha256 is not None
            else None
        )
        audit_before = _json_object_or_none(case["publication_audit_before_json"])
        audit_after = _json_object_or_none(case["publication_audit_after_json"])
        if (
            case["publication_audit_event_id"] is None
            or audit_before is None
            or audit_after is None
        ):
            block("PUBLICATION_AUDIT_MISSING", "A auditoria da publicação está incompleta.")
        elif publication_proof_sha256 is not None:
            audit_checks = (
                (audit_before.get("publishable"), False),
                (audit_before.get("case_reference_sha256"), _reference_sha256(case_id)),
                (audit_before.get("version_sha256"), str(case["normalized_sha256"])),
                (audit_after.get("publishable"), True),
                (audit_after.get("source_sha256"), source["content_sha256"]),
                (audit_after.get("snapshot_sha256"), candidate["normalised_sha256"]),
                (audit_after.get("mapping_sha256"), mapping_sha256),
                (audit_after.get("publication_proof_sha256"), publication_proof_sha256),
                (audit_after.get("session_reference_sha256"), _reference_sha256(session_id)),
                (audit_after.get("attendance_records_created"), record_count),
                (audit_after.get("people_created"), 0),
                (audit_after.get("mandates_created"), 0),
                (audit_after.get("selective_processing"), False),
            )
            if any(received != expected for received, expected in audit_checks):
                block(
                    "PUBLICATION_AUDIT_PROOF_MISMATCH",
                    "A prova original já não corresponde à reunião e às linhas atuais.",
                )
        if (
            case["publication_audit_created_at"] is not None
            and case["public_reviewed_at"] != case["publication_audit_created_at"]
        ):
            block("PUBLICATION_REVIEW_MISMATCH", "A revisão ativa não é a revisão publicada.")

        public_effect = await self._public_effect(
            connection,
            snapshot_id=snapshot_id,
            legislature=str(candidate["legislature"]),
            record_count=record_count,
        )
        withdrawal_payload = {
            "schema_version": _WITHDRAWAL_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case_id),
            "version_reference_sha256": _reference_sha256(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "snapshot_reference_sha256": _reference_sha256(snapshot_id),
            "snapshot_sha256": str(candidate["normalised_sha256"]),
            "source_sha256": str(source["content_sha256"]),
            "mapping_sha256": mapping_sha256,
            "publication_proof_sha256": publication_proof_sha256,
            "public_review_reference_sha256": _reference_sha256(case["public_review_id"]),
            "publication_audit_reference_sha256": _reference_sha256(
                case["publication_audit_event_id"]
            ),
            "publication_event_reference_sha256": _reference_sha256(case["publication_event_id"]),
            "publication_event_sha256": publication_event_sha256,
            "session_reference_sha256": _reference_sha256(session_id),
            "record_count": record_count,
            "public_effect": public_effect,
            "whole_meeting_only": True,
            "session_and_records_preserved": True,
            "people_and_mandates_unchanged": True,
            "absence_is_noncompliance": False,
            "automatic_withdrawal": False,
        }
        eligible = (
            not blockers and mapping_sha256 is not None and publication_proof_sha256 is not None
        )
        preview: dict[str, object] = {
            "case_id": case_id,
            "case_state": str(case["current_state"]),
            "case_revision": int(case["revision"]),
            "version_id": str(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "snapshot_id": snapshot_id,
            "snapshot_sha256": str(candidate["normalised_sha256"]),
            "mapping_sha256": mapping_sha256,
            "source": source,
            "publication_proof_sha256": publication_proof_sha256,
            "withdrawal_proof_sha256": _sha256_json(withdrawal_payload) if eligible else None,
            "public_review_id": str(case["public_review_id"] or ""),
            "publication_audit_event_id": str(case["publication_audit_event_id"] or ""),
            "publication_event_id": str(case["publication_event_id"] or ""),
            "publication_event_sha256": publication_event_sha256 or "0" * 64,
            "record_count": record_count,
            "public_effect": public_effect,
            "public_effect_sha256": _sha256_json(public_effect),
            "eligible": eligible,
            "blockers": blockers,
            "automatic_withdrawal": False,
            "selective_withdrawal_allowed": False,
            "sessions_to_delete": 0,
            "attendance_records_to_delete": 0,
            "people_to_delete": 0,
            "mandates_to_delete": 0,
            "absence_is_noncompliance": False,
            "withdrawal_rule": (
                "A revisão negativa, auditoria, decisão e evento são acrescentados numa "
                "transação ADMIN com MFA. A sessão, todas as presenças e a publicação "
                "original permanecem imutáveis."
            ),
        }
        return preview, {
            "case": dict(case),
            "candidate": candidate,
            "mappings": mappings,
            "records": records,
        }

    @staticmethod
    async def _public_effect(
        connection: asyncpg.Connection,
        *,
        snapshot_id: str,
        legislature: str,
        record_count: int,
    ) -> dict[str, object]:
        remaining = await connection.fetchval(
            f"""
            SELECT COUNT(*)::int
            FROM parliamentary_sessions AS session
            JOIN parliament_attendance_snapshots AS snapshot
              ON snapshot.id = session.attendance_snapshot_id
             AND snapshot.source_document_id = session.source_document_id
            JOIN source_documents AS source ON source.id = session.source_document_id
            JOIN LATERAL (
                SELECT review.publishable
                FROM data_publication_reviews AS review
                WHERE review.entity_type = '{_SUBJECT_TYPE}'
                  AND review.entity_id = snapshot.id
                  AND review.source_document_id = source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS latest_review ON latest_review.publishable = TRUE
            WHERE snapshot.legislature = $1
              AND snapshot.id <> $2
              AND source.publisher = 'PARLIAMENT'
              AND source.kind = 'ATTENDANCE'
              AND EXISTS (
                  SELECT 1
                  FROM source_archive_attestations AS archive
                  WHERE archive.source_document_id = source.id
                    AND archive.content_sha256 = source.content_sha256
                    AND archive.retrieval_url = source.url
                    AND archive.retrieved_at = source.retrieved_at
              )
            """,
            legislature,
            snapshot_id,
        )
        return {
            "kind": "PARLIAMENT_ATTENDANCE_MEETING_HIDDEN_HISTORY_PRESERVED",
            "snapshot_reference_sha256": _reference_sha256(snapshot_id),
            "exact_meeting_public_after_withdrawal": False,
            "remaining_public_attendance_meetings_in_legislature": int(remaining or 0),
            "session_preserved": True,
            "attendance_records_preserved": record_count,
            "people_and_mandates_unchanged": True,
            "selective_withdrawal": False,
            "message": (
                "A reunião integral deixa a consulta ativa; sessão, todas as linhas, fonte, "
                "versão, publicação e decisões anteriores permanecem preservadas."
            ),
        }

    @staticmethod
    def _confirm_payload(
        *,
        case_id: str,
        preview: dict[str, object],
        payload: PoliticianAttendanceWithdrawalRequest,
    ) -> None:
        if case_id != payload.expected_case_id or str(preview["case_id"]) != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        source = cast(dict[str, object], preview["source"])
        confirmations = (
            (payload.expected_revision, preview["case_revision"], "revisão"),
            (payload.expected_version_id, preview["version_id"], "versão"),
            (payload.expected_version_sha256, preview["version_sha256"], "SHA-256 da versão"),
            (payload.expected_snapshot_id, preview["snapshot_id"], "reunião"),
            (payload.expected_source_sha256, source["content_sha256"], "SHA-256 da fonte"),
            (payload.expected_snapshot_sha256, preview["snapshot_sha256"], "fotografia"),
            (payload.expected_mapping_sha256, preview["mapping_sha256"], "mapa exato"),
            (
                payload.expected_publication_proof_sha256,
                preview["publication_proof_sha256"],
                "prova de publicação",
            ),
            (
                payload.expected_withdrawal_proof_sha256,
                preview["withdrawal_proof_sha256"],
                "prova de retirada",
            ),
            (payload.expected_public_review_id, preview["public_review_id"], "revisão pública"),
            (
                payload.expected_publication_audit_event_id,
                preview["publication_audit_event_id"],
                "auditoria de publicação",
            ),
            (
                payload.expected_publication_event_id,
                preview["publication_event_id"],
                "evento de publicação",
            ),
            (
                payload.expected_publication_event_sha256,
                preview["publication_event_sha256"],
                "SHA-256 do evento de publicação",
            ),
            (
                payload.expected_public_effect_sha256,
                preview["public_effect_sha256"],
                "efeito público",
            ),
            (payload.expected_record_count, preview["record_count"], "contagem integral"),
        )
        for received, expected, label in confirmations:
            if received != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    async def withdraw(
        self,
        *,
        case_id: str,
        payload: PoliticianAttendanceWithdrawalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError("Esta retirada exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError("A retirada exige autenticação multifator")
        if case_id != payload.expected_case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"politician-attendance-publication:{case_id}",
                )
                preview, context = await self._inspect_context(
                    connection,
                    case_id=case_id,
                    lock=True,
                )
                self._confirm_payload(case_id=case_id, preview=preview, payload=payload)
                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    details = "; ".join(str(item["detail"]) for item in blockers)
                    if str(preview["case_state"]) != EditorialState.PUBLISHED.value:
                        raise EditorialConflictError(details)
                    raise EditorialSourceError(details)

                case = context["case"]
                candidate = context["candidate"]
                records = context["records"]
                assert isinstance(case, dict)
                assert isinstance(candidate, dict)
                assert isinstance(records, list)
                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")

                review_id = _new_id("publication_review")
                await connection.execute(
                    f"""
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, '{_SUBJECT_TYPE}', $2,
                            'Retirada documentada de uma reunião integral de presenças',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'Sessão e linhas permanecem; só a revisão mais recente muda.',
                            'A decisão não seleciona pessoas, não altera mandatos e não '
                            'transforma faltas em incumprimento.',
                            FALSE, $3, $4, $5)
                    """,
                    review_id,
                    str(preview["snapshot_id"]),
                    str(case["source_document_id"]),
                    actor.public_alias,
                    created_at,
                )

                internal_rationale = f"[{payload.reason_category.value}] {payload.rationale}"
                audit_id = _new_id("audit")
                await connection.execute(
                    f"""
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, '{_SUBJECT_TYPE}', $2, 'WITHDRAWN', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    audit_id,
                    str(preview["snapshot_id"]),
                    actor.public_alias,
                    _canonical_json(
                        {
                            "publishable": True,
                            "public_review_reference_sha256": _reference_sha256(
                                preview["public_review_id"]
                            ),
                            "publication_audit_reference_sha256": _reference_sha256(
                                preview["publication_audit_event_id"]
                            ),
                            "publication_event_reference_sha256": _reference_sha256(
                                preview["publication_event_id"]
                            ),
                            "publication_proof_sha256": preview["publication_proof_sha256"],
                        }
                    ),
                    _canonical_json(
                        {
                            "publishable": False,
                            "source_sha256": payload.expected_source_sha256,
                            "snapshot_sha256": payload.expected_snapshot_sha256,
                            "mapping_sha256": payload.expected_mapping_sha256,
                            "withdrawal_proof_sha256": payload.expected_withdrawal_proof_sha256,
                            "public_effect": preview["public_effect"],
                            "public_effect_sha256": payload.expected_public_effect_sha256,
                            "withdrawal_reason_category": payload.reason_category.value,
                            "session_deleted": False,
                            "attendance_records_deleted": 0,
                            "people_changed": False,
                            "mandates_changed": False,
                            "selective_withdrawal": False,
                            "absence_is_noncompliance": False,
                        }
                    ),
                    payload.public_rationale,
                    created_at,
                )

                version_id = str(case["current_version_id"])
                next_revision = int(case["revision"]) + 1
                decision_id = _new_id("editorial_decision")
                decision_sha256 = self.editorial._decision_sha256(
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.WITHDRAW,
                    previous_state=EditorialState.PUBLISHED,
                    resulting_state=EditorialState.WITHDRAWN,
                    case_revision=next_revision,
                    rationale=internal_rationale,
                    source_confirmed=False,
                    actor=actor,
                    created_at=created_at,
                )
                await self.editorial._insert_decision(
                    connection,
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.WITHDRAW,
                    previous_state=EditorialState.PUBLISHED,
                    resulting_state=EditorialState.WITHDRAWN,
                    case_revision=next_revision,
                    rationale=internal_rationale,
                    source_confirmed=False,
                    actor=actor,
                    decision_sha256=decision_sha256,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    UPDATE editorial_cases
                    SET current_state = 'WITHDRAWN', revision = $2, updated_at = $3
                    WHERE id = $1
                    """,
                    case_id,
                    next_revision,
                    created_at,
                )

                event_id = _new_id("editorial_publication")
                event_sha256 = _publication_event_sha256(
                    event_id=event_id,
                    case_id=case_id,
                    version_id=version_id,
                    action="WITHDRAW",
                    target_id=str(preview["snapshot_id"]),
                    rationale=internal_rationale,
                    actor_id=actor.staff_id,
                    actor_alias=actor.public_alias,
                    created_at=created_at,
                )
                await connection.execute(
                    f"""
                    INSERT INTO editorial_publication_events
                        (id, case_id, version_id, action, target_type, target_id,
                         rationale, actor_id, actor_alias, event_sha256, created_at)
                    VALUES ($1, $2, $3, 'WITHDRAW'::"EditorialPublicationAction",
                            '{_SUBJECT_TYPE}', $4, $5, $6, $7, $8, $9)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    str(preview["snapshot_id"]),
                    internal_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )

                final = await connection.fetchrow(
                    f"""
                    SELECT EXISTS (
                               SELECT 1
                               FROM parliamentary_sessions
                               WHERE id = $1 AND attendance_snapshot_id = $2
                           ) AS session_preserved,
                           (
                               SELECT COUNT(*)::int
                               FROM attendance_records
                               WHERE session_id = $1
                           ) AS records_preserved,
                           EXISTS (
                               SELECT 1
                               FROM parliamentary_sessions AS session
                               JOIN LATERAL (
                                   SELECT review.publishable
                                   FROM data_publication_reviews AS review
                                   WHERE review.entity_type = '{_SUBJECT_TYPE}'
                                     AND review.entity_id = $2
                                     AND review.source_document_id = $3
                                   ORDER BY review.reviewed_at DESC, review.id DESC
                                   LIMIT 1
                               ) AS latest_review ON latest_review.publishable = TRUE
                               WHERE session.id = $1
                           ) AS still_public,
                           EXISTS (
                               SELECT 1 FROM editorial_publication_events
                               WHERE id = $4 AND action = 'PUBLISH'
                           ) AS publication_event_preserved,
                           EXISTS (
                               SELECT 1 FROM audit_events
                               WHERE id = $5 AND action = 'PUBLISHED'
                           ) AS publication_audit_preserved
                    """,
                    str(case["session_id"]),
                    str(preview["snapshot_id"]),
                    str(case["source_document_id"]),
                    str(preview["publication_event_id"]),
                    str(preview["publication_audit_event_id"]),
                )
                if final is None or final["session_preserved"] is not True:
                    raise EditorialSourceError("A sessão deixou de existir; tudo foi revertido")
                if int(final["records_preserved"] or 0) != len(records):
                    raise EditorialSourceError("As presenças deixaram de estar completas")
                if final["still_public"] is True:
                    raise EditorialSourceError("A reunião ainda seria pública; tudo foi revertido")
                if not (
                    final["publication_event_preserved"] is True
                    and final["publication_audit_preserved"] is True
                ):
                    raise EditorialSourceError("A prova original deixou de estar preservada")
                confirmed_effect = await self._public_effect(
                    connection,
                    snapshot_id=str(preview["snapshot_id"]),
                    legislature=str(candidate["legislature"]),
                    record_count=len(records),
                )
                if confirmed_effect != preview["public_effect"]:
                    raise EditorialConflictError("O efeito público mudou durante a retirada")
        except asyncpg.IntegrityConstraintViolationError as exc:
            raise EditorialConflictError(
                "O processo ou a prova mudou; nenhuma retirada foi registada"
            ) from exc

        return {
            "created": True,
            "case_id": case_id,
            "version_id": payload.expected_version_id,
            "state": EditorialState.WITHDRAWN.value,
            "revision": next_revision,
            "snapshot_id": payload.expected_snapshot_id,
            "reason_category": payload.reason_category.value,
            "attendance_review_id": review_id,
            "audit_event_id": audit_id,
            "editorial_decision_id": decision_id,
            "withdrawal_event_id": event_id,
            "decision_sha256": decision_sha256,
            "event_sha256": event_sha256,
            "withdrawal_proof_sha256": payload.expected_withdrawal_proof_sha256,
            "public_effect": preview["public_effect"],
            "public_effect_sha256": payload.expected_public_effect_sha256,
            "sessions_deleted": 0,
            "attendance_records_deleted": 0,
            "people_deleted": 0,
            "mandates_deleted": 0,
            "automatic_withdrawal": False,
            "selective_withdrawal_allowed": False,
            "absence_is_noncompliance": False,
            "withdrawal_rule": (
                "A revisão negativa, auditoria, decisão e evento foram acrescentados numa "
                "transação ADMIN com MFA; a reunião e toda a prova original permanecem."
            ),
        }
