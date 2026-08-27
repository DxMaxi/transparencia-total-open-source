"""Publicação transacional de uma reunião integral de presenças parlamentares."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialState,
    PoliticianAttendancePublicationRequest,
    StaffRole,
    StaffSession,
    validate_normalized_data,
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

_SUBJECT_TYPE = "PARLIAMENT_ATTENDANCE_SNAPSHOT"
_PROPOSAL_SCHEMA_VERSION = "politician-attendance-editorial-v1"
_PUBLICATION_SCHEMA_VERSION = "politician-attendance-publication-v1"
_ALLOWED_STATUSES = frozenset({"PRESENT", "JUSTIFIED_ABSENCE", "UNJUSTIFIED_ABSENCE"})


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


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


def _iso_timestamp(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_object(value: object) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise EditorialSourceError("A versão editorial deixou de ser um objeto JSON")
    result = dict(decoded)
    try:
        validate_normalized_data(result)
    except ValueError as exc:
        raise EditorialSourceError(
            f"A versão editorial deixou de cumprir o contrato: {exc}"
        ) from exc
    return result


def _meeting_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise EditorialSourceError("A data oficial da reunião deixou de ser textual")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise EditorialSourceError("A data oficial da reunião deixou de ser válida") from exc
    return parsed


def _integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EditorialSourceError(f"{label} deixou de ser um número inteiro")
    return value


def _optional_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _status_projection(status: object) -> tuple[bool, bool | None]:
    value = str(status)
    if value == "PRESENT":
        return True, None
    if value == "JUSTIFIED_ABSENCE":
        return False, True
    if value == "UNJUSTIFIED_ABSENCE":
        return False, False
    raise EditorialSourceError("A reunião contém um estado não publicável; nada pode ser projetado")


def _publication_event_sha256(
    *,
    event_id: str,
    case_id: str,
    version_id: str,
    action: str,
    target_id: str,
    rationale: str,
    actor_id: str,
    actor_alias: str,
    created_at: datetime,
) -> str:
    return _sha256_json(
        {
            "id": event_id,
            "case_id": case_id,
            "version_id": version_id,
            "action": action,
            "target_type": _SUBJECT_TYPE,
            "target_id": target_id,
            "rationale": rationale,
            "actor_id": actor_id,
            "actor_alias": actor_alias,
            "created_at": _iso_timestamp(created_at),
        }
    )


def _attendance_mapping_sha256(rows: list[dict[str, object]]) -> str:
    mappings: list[dict[str, object]] = []
    for row in rows:
        present, is_excused = _status_projection(row["status"])
        mappings.append(
            {
                "source_observation_reference_sha256": _reference_sha256(row["observation_id"]),
                "official_deputy_id_reference_sha256": _reference_sha256(row["official_deputy_id"]),
                "person_reference_sha256": _reference_sha256(row["person_id"]),
                "mandate_reference_sha256": _reference_sha256(row["mandate_id"]),
                "source_record_sha256": str(row["source_record_sha256"]),
                "status": str(row["status"]),
                "present": present,
                "is_excused": is_excused,
                "absence_reason": row["absence_reason"],
            }
        )
    return _sha256_json(
        sorted(
            mappings,
            key=lambda item: str(item["source_observation_reference_sha256"]),
        )
    )


def _attendance_publication_proof_sha256(
    *,
    case_id: str,
    version_id: object,
    version_sha256: object,
    source_sha256: object,
    snapshot_id: object,
    snapshot_sha256: object,
    mapping_sha256: str,
    legislature: object,
    meeting_date: object,
    counts: object,
    public_effect: dict[str, int],
) -> str:
    """Reconstrói a prova sem confiar em identificadores recebidos do cliente."""

    return _sha256_json(
        {
            "schema_version": _PUBLICATION_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case_id),
            "version_reference_sha256": _reference_sha256(version_id),
            "version_sha256": str(version_sha256),
            "source_sha256": str(source_sha256),
            "snapshot_reference_sha256": _reference_sha256(snapshot_id),
            "snapshot_sha256": str(snapshot_sha256),
            "mapping_sha256": mapping_sha256,
            "legislature": legislature,
            "meeting_date": meeting_date,
            "counts": counts,
            "public_effect": public_effect,
            "identity_rule": "EXACT_AR_BID_ONLY",
            "selection_rule": "WHOLE_MEETING_ONLY",
            "absence_rule": "SOURCE_STATUS_IS_NOT_AUTOMATIC_NONCOMPLIANCE",
            "name_matching_allowed": False,
            "automatic_publication": False,
        }
    )


class PoliticianAttendancePublicationRepository:
    """Publica uma reunião inteira ou reverte tudo, sem seleção individual."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.candidates = PoliticianAttendanceEditorialRepository(pool)

    async def inspect(self, *, case_id: str) -> dict[str, object]:
        preview, _context = await self._inspect_context(
            case_id=case_id,
            connection=None,
            lock=False,
        )
        return preview

    async def _load_case(
        self,
        *,
        case_id: str,
        connection: asyncpg.Connection | None,
    ) -> Mapping[str, Any]:
        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        row = await database.fetchrow(
            f"""
            SELECT editorial_case.id,
                   editorial_case.subject_id,
                   editorial_case.source_document_id,
                   editorial_case.current_state::text AS current_state,
                   editorial_case.revision,
                   editorial_case.current_version_id,
                   version.normalized_json AS normalized_data,
                   version.normalized_sha256,
                   latest_decision.action::text AS latest_decision_action,
                   latest_decision.resulting_state::text AS latest_decision_state,
                   latest_decision.case_revision AS latest_decision_case_revision,
                   latest_decision.version_id AS latest_decision_version_id,
                   latest_decision.source_confirmed AS latest_source_confirmed
            FROM editorial_cases AS editorial_case
            JOIN editorial_versions AS version
              ON version.id = editorial_case.current_version_id
             AND version.case_id = editorial_case.id
            LEFT JOIN LATERAL (
                SELECT decision.action, decision.resulting_state,
                       decision.case_revision, decision.version_id,
                       decision.source_confirmed
                FROM editorial_decisions AS decision
                WHERE decision.case_id = editorial_case.id
                ORDER BY decision.case_revision DESC, decision.id DESC
                LIMIT 1
            ) AS latest_decision ON TRUE
            WHERE editorial_case.id = $1
              AND editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
              AND editorial_case.subject_type = '{_SUBJECT_TYPE}'
            """,
            case_id,
        )
        if row is None:
            raise EditorialNotFoundError("Processo editorial de presenças não encontrado")
        return cast(Mapping[str, Any], row)

    async def _load_mappings(
        self,
        *,
        snapshot_id: str,
        legislature: str,
        meeting_date: datetime,
        connection: asyncpg.Connection | None,
    ) -> list[dict[str, object]]:
        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        rows = await database.fetch(
            """
            SELECT observation.id AS observation_id,
                   observation.official_deputy_id,
                   observation.status,
                   observation.absence_reason,
                   observation.source_record_sha256,
                   person.id AS person_id,
                   person.role::text AS person_role,
                   person.active AS person_active,
                   identity_review.publishable AS identity_publishable,
                   identity_review.proof_valid AS identity_proof_valid,
                   mandate_match.mandate_count,
                   mandate_match.reviewed_mandate_count,
                   mandate_match.mandate_id,
                   existing_record.id AS existing_record_id
            FROM parliament_attendance_observations AS observation
            LEFT JOIN people AS person
              ON person.source_id = observation.official_deputy_id
            LEFT JOIN LATERAL (
                SELECT review.publishable,
                       (
                           source.publisher = 'PARLIAMENT'
                           AND source.kind <> 'NEWS_ARTICLE'
                           AND EXISTS (
                               SELECT 1
                               FROM source_archive_attestations AS attestation
                               WHERE attestation.source_document_id = source.id
                                 AND attestation.content_sha256 = source.content_sha256
                                 AND attestation.retrieval_url = source.url
                                 AND attestation.retrieved_at = source.retrieved_at
                           )
                       ) AS proof_valid
                FROM data_publication_reviews AS review
                LEFT JOIN source_documents AS source
                  ON source.id = review.source_document_id
                WHERE review.entity_type = 'PERSON'
                  AND review.entity_id = person.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS identity_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS mandate_count,
                       COUNT(*) FILTER (
                           WHERE latest_review.publishable = TRUE
                             AND mandate_source.publisher = 'PARLIAMENT'
                             AND mandate_source.kind <> 'NEWS_ARTICLE'
                             AND EXISTS (
                                 SELECT 1
                                 FROM source_archive_attestations AS attestation
                                 WHERE attestation.source_document_id = mandate_source.id
                                   AND attestation.content_sha256 =
                                       mandate_source.content_sha256
                                   AND attestation.retrieval_url = mandate_source.url
                                   AND attestation.retrieved_at =
                                       mandate_source.retrieved_at
                             )
                       )::int AS reviewed_mandate_count,
                       MIN(mandate.id) FILTER (
                           WHERE latest_review.publishable = TRUE
                             AND mandate_source.publisher = 'PARLIAMENT'
                             AND mandate_source.kind <> 'NEWS_ARTICLE'
                             AND EXISTS (
                                 SELECT 1
                                 FROM source_archive_attestations AS attestation
                                 WHERE attestation.source_document_id = mandate_source.id
                                   AND attestation.content_sha256 =
                                       mandate_source.content_sha256
                                   AND attestation.retrieval_url = mandate_source.url
                                   AND attestation.retrieved_at =
                                       mandate_source.retrieved_at
                             )
                       ) AS mandate_id
                FROM mandates AS mandate
                JOIN source_documents AS mandate_source
                  ON mandate_source.id = mandate.source_document_id
                LEFT JOIN LATERAL (
                    SELECT review.publishable
                    FROM data_publication_reviews AS review
                    WHERE review.entity_type = 'MANDATE'
                      AND review.entity_id = mandate.id
                      AND review.source_document_id = mandate.source_document_id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) AS latest_review ON TRUE
                WHERE mandate.person_id = person.id
                  AND mandate.legislature = $2
                  AND mandate.started_at::date <= $3::date
                  AND (
                      mandate.ended_at IS NULL
                      OR mandate.ended_at::date >= $3::date
                  )
            ) AS mandate_match ON TRUE
            LEFT JOIN attendance_records AS existing_record
              ON existing_record.source_observation_id = observation.id
            WHERE observation.snapshot_id = $1
            ORDER BY observation.id COLLATE "C"
            """,
            snapshot_id,
            legislature,
            meeting_date,
        )
        return [dict(row) for row in rows]

    @staticmethod
    def _mapping_blockers(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        blockers: list[dict[str, object]] = []

        def block(code: str, detail: str) -> None:
            if not any(item["code"] == code for item in blockers):
                blockers.append({"code": code, "detail": detail})

        for row in rows:
            if str(row["status"]) not in _ALLOWED_STATUSES:
                block(
                    "UNKNOWN_STATUS_PRESENT",
                    "Existe pelo menos um estado não publicável na reunião integral.",
                )
            if row["person_id"] is None:
                block(
                    "EXACT_IDENTITY_MISSING",
                    "Existe pelo menos um BID sem identidade pública exata.",
                )
                continue
            if str(row["person_role"] or "") != "DEPUTY" or row["person_active"] is not True:
                block(
                    "PERSON_NOT_ACTIVE_DEPUTY",
                    "Existe uma identidade que não é uma pessoa deputada ativa.",
                )
            if not (row["identity_publishable"] is True and row["identity_proof_valid"] is True):
                block(
                    "IDENTITY_REVIEW_INVALID",
                    "Existe uma identidade sem revisão positiva e arquivo oficial válido.",
                )
            if _optional_count(row["mandate_count"]) != 1:
                block(
                    "EXACT_MANDATE_MISSING",
                    "Cada BID exige exatamente um mandato a cobrir a data da reunião.",
                )
            if _optional_count(row["reviewed_mandate_count"]) != 1 or row["mandate_id"] is None:
                block(
                    "MANDATE_REVIEW_INVALID",
                    "Existe um mandato sem revisão positiva e arquivo oficial válido.",
                )
            if row["existing_record_id"] is not None:
                block(
                    "ATTENDANCE_RECORD_ALREADY_EXISTS",
                    "Pelo menos uma observação já possui projeção pública.",
                )
        return blockers

    async def _inspect_context(
        self,
        *,
        case_id: str,
        connection: asyncpg.Connection | None,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, object]]:
        if lock and connection is not None:
            locked_case_id = await connection.fetchval(
                "SELECT id FROM editorial_cases WHERE id = $1 FOR UPDATE",
                case_id,
            )
            if locked_case_id is None:
                raise EditorialNotFoundError("Processo editorial de presenças não encontrado")
        case = await self._load_case(case_id=case_id, connection=connection)
        snapshot_id = str(case["subject_id"])
        candidate = await self.candidates.get_exact_candidate(
            snapshot_id=snapshot_id,
            connection=connection,
        )
        if candidate is None:
            raise EditorialSourceError(
                "A reunião aprovada deixou de corresponder à fonte oficial atestada"
            )
        normalized = _json_object(case["normalized_data"])
        proposal_observations = await self.candidates.load_proposal_observations(
            snapshot_id,
            connection=connection,
        )
        meeting_date = _meeting_datetime(candidate["meeting_date"])
        mappings = await self._load_mappings(
            snapshot_id=snapshot_id,
            legislature=str(candidate["legislature"]),
            meeting_date=meeting_date,
            connection=connection,
        )
        if lock and connection is not None:
            person_ids = sorted(
                {str(row["person_id"]) for row in mappings if row["person_id"] is not None}
            )
            mandate_ids = sorted(
                {str(row["mandate_id"]) for row in mappings if row["mandate_id"] is not None}
            )
            if person_ids:
                await connection.fetch(
                    "SELECT id FROM people WHERE id = ANY($1::text[]) FOR UPDATE",
                    person_ids,
                )
            if mandate_ids:
                await connection.fetch(
                    "SELECT id FROM mandates WHERE id = ANY($1::text[]) FOR UPDATE",
                    mandate_ids,
                )
            mappings = await self._load_mappings(
                snapshot_id=snapshot_id,
                legislature=str(candidate["legislature"]),
                meeting_date=meeting_date,
                connection=connection,
            )

        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        existing = await database.fetchrow(
            """
            SELECT session.id AS session_id,
                   public_review.id AS public_review_id,
                   publication_event.id AS publication_event_id
            FROM (SELECT $1::text AS snapshot_id) AS requested
            LEFT JOIN parliamentary_sessions AS session
              ON session.attendance_snapshot_id = requested.snapshot_id
            LEFT JOIN LATERAL (
                SELECT review.id
                FROM data_publication_reviews AS review
                WHERE review.entity_type = $2
                  AND review.entity_id = requested.snapshot_id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS public_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id
                FROM editorial_publication_events AS event
                WHERE event.case_id = $3
                  AND event.target_type = $2
                  AND event.target_id = requested.snapshot_id
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS publication_event ON TRUE
            """,
            snapshot_id,
            _SUBJECT_TYPE,
            case_id,
        )
        assert existing is not None

        blockers: list[dict[str, object]] = []

        def block(code: str, detail: str) -> None:
            blockers.append({"code": code, "detail": detail})

        if str(case["current_state"]) != EditorialState.APPROVED.value:
            block("CASE_NOT_APPROVED", "O processo não está no estado editorial APPROVED.")
        if not (
            str(case["latest_decision_action"] or "") == EditorialAction.APPROVE.value
            and str(case["latest_decision_state"] or "") == EditorialState.APPROVED.value
            and int(case["latest_decision_case_revision"] or -1) == int(case["revision"])
            and str(case["latest_decision_version_id"] or "")
            == str(case["current_version_id"] or "")
            and case["latest_source_confirmed"] is True
        ):
            block(
                "LATEST_APPROVAL_INVALID",
                "A decisão atual não confirma esta versão e esta fonte.",
            )
        if normalized.get("schema_version") != _PROPOSAL_SCHEMA_VERSION:
            block("PROPOSAL_SCHEMA_INVALID", "A versão aprovada usa outro contrato editorial.")
        expected_normalized = self.candidates._normalized_proposal(
            candidate,
            proposal_observations,
        )
        if normalized != expected_normalized:
            block(
                "APPROVED_VERSION_DRIFT",
                "A versão aprovada diverge da prova oficial reconstruída no servidor.",
            )
        candidate_blockers = candidate["blocked_reasons"]
        publication_blockers = candidate["publication_blockers"]
        assert isinstance(candidate_blockers, list)
        assert isinstance(publication_blockers, list)
        for detail in candidate_blockers + publication_blockers:
            block("SOURCE_CANDIDATE_BLOCKED", str(detail))
        record_count = _integer(candidate["record_count"], label="A contagem da reunião")
        if len(proposal_observations) != record_count or len(mappings) != record_count:
            block(
                "MEETING_NOT_COMPLETE",
                "As observações deixaram de corresponder à contagem integral da reunião.",
            )
        blockers.extend(self._mapping_blockers(mappings))
        if str(case["source_document_id"]) != str(candidate["source_document_id"]):
            block("SOURCE_DOCUMENT_CHANGED", "O documento do processo deixou de coincidir.")
        if existing["session_id"] is not None:
            block("SESSION_ALREADY_EXISTS", "A reunião já possui uma sessão pública.")
        if existing["public_review_id"] is not None:
            block("PUBLIC_REVIEW_ALREADY_EXISTS", "A reunião já possui revisão pública.")
        if existing["publication_event_id"] is not None:
            block("PUBLICATION_EVENT_ALREADY_EXISTS", "A reunião já possui evento público.")

        mapping_sha256: str | None = None
        if not self._mapping_blockers(mappings) and len(mappings) == record_count:
            mapping_sha256 = _attendance_mapping_sha256(mappings)
        manifest_counts = candidate["manifest_counts"]
        assert isinstance(manifest_counts, dict)
        public_effect = {
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
        source = candidate["source"]
        assert isinstance(source, dict)
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
                public_effect=public_effect,
            )
            if mapping_sha256 is not None and not blockers
            else None
        )
        preview: dict[str, object] = {
            "case_id": case_id,
            "case_state": str(case["current_state"]),
            "case_revision": int(case["revision"]),
            "version_id": str(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "snapshot_id": snapshot_id,
            "snapshot_sha256": str(candidate["normalised_sha256"]),
            "source": source,
            "archive": candidate["archive"],
            "meeting": {
                "legislature": candidate["legislature"],
                "official_meeting_id": candidate["official_meeting_id"],
                "date": candidate["meeting_date"],
                "type": candidate["meeting_type"],
                "session_number": candidate["session_number"],
            },
            "counts": manifest_counts,
            "identity_reconciliation": candidate["identity_reconciliation"],
            "mapping_sha256": mapping_sha256,
            "public_effect": public_effect,
            "publication_proof_sha256": publication_proof_sha256,
            "eligible": not blockers,
            "blockers": blockers,
            "automatic_publication": False,
            "human_review_required": True,
            "selective_processing_allowed": False,
            "name_matching_allowed": False,
            "absence_is_noncompliance": False,
            "withdrawal_required_before_real_activation": True,
            "publication_rule": (
                "A ação ADMIN volta a provar a reunião completa, a fonte, o arquivo, cada "
                "BID e exatamente um mandato revisto; sessão, linhas, revisão, auditoria, "
                "decisão e evento são acrescentados na mesma transação."
            ),
        }
        context: dict[str, object] = {
            "case": dict(case),
            "candidate": candidate,
            "mappings": mappings,
            "meeting_date": meeting_date,
        }
        return preview, context

    @staticmethod
    def _confirm_payload(
        *,
        case_id: str,
        preview: dict[str, object],
        payload: PoliticianAttendancePublicationRequest,
    ) -> None:
        source = preview["source"]
        public_effect = preview["public_effect"]
        assert isinstance(source, dict)
        assert isinstance(public_effect, dict)
        if case_id != payload.expected_case_id or str(preview["case_id"]) != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        checks = (
            (preview["version_id"], payload.expected_version_id, "A versão editorial mudou"),
            (
                preview["version_sha256"],
                payload.expected_version_sha256,
                "O SHA-256 da versão mudou",
            ),
            (source["content_sha256"], payload.expected_source_sha256, "A fonte mudou"),
            (
                preview["snapshot_sha256"],
                payload.expected_snapshot_sha256,
                "A fotografia normalizada mudou",
            ),
            (
                preview["mapping_sha256"],
                payload.expected_mapping_sha256,
                "O mapa exato de identidades e mandatos mudou",
            ),
            (
                preview["publication_proof_sha256"],
                payload.expected_publication_proof_sha256,
                "A prova de publicação mudou",
            ),
        )
        for actual, expected, message in checks:
            if str(actual) != expected:
                raise EditorialConflictError(f"{message} antes da publicação")
        if int(public_effect["attendance_records_to_create"]) != payload.expected_record_count:
            raise EditorialConflictError("A contagem integral mudou antes da publicação")

    async def publish(
        self,
        *,
        case_id: str,
        payload: PoliticianAttendancePublicationRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError("Esta publicação exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError("A publicação exige autenticação multifator")
        if case_id != payload.expected_case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"politician-attendance-publication:{case_id}",
                )
                preview, context = await self._inspect_context(
                    case_id=case_id,
                    connection=connection,
                    lock=True,
                )
                self._confirm_payload(case_id=case_id, preview=preview, payload=payload)
                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    raise EditorialSourceError("; ".join(str(item["detail"]) for item in blockers))

                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")
                case = context["case"]
                candidate = context["candidate"]
                mappings = context["mappings"]
                assert isinstance(case, dict)
                assert isinstance(candidate, dict)
                assert isinstance(mappings, list)

                session_id = _new_id("parliament_session")
                await connection.execute(
                    """
                    INSERT INTO parliamentary_sessions
                        (id, source_id, legislature, session_number, title,
                         starts_at, ends_at, snapshot_id, attendance_snapshot_id,
                         source_document_id)
                    VALUES ($1, $2, $3, $4, $5, $6, NULL, NULL, $7, $8)
                    """,
                    session_id,
                    str(candidate["official_meeting_id"]),
                    str(candidate["legislature"]),
                    candidate["session_number"],
                    f"Reunião plenária — {candidate['meeting_type']}",
                    context["meeting_date"],
                    str(candidate["snapshot_id"]),
                    str(candidate["source_document_id"]),
                )

                attendance_ids: list[str] = []
                attendance_values: list[tuple[object, ...]] = []
                for row in mappings:
                    assert isinstance(row, dict)
                    present, is_excused = _status_projection(row["status"])
                    attendance_id = _new_id("attendance")
                    attendance_ids.append(attendance_id)
                    attendance_values.append(
                        (
                            attendance_id,
                            str(row["mandate_id"]),
                            session_id,
                            present,
                            row["absence_reason"] if not present else None,
                            is_excused,
                            str(candidate["source_document_id"]),
                            str(row["observation_id"]),
                            str(row["source_record_sha256"]),
                            created_at,
                        )
                    )
                await connection.executemany(
                    """
                    INSERT INTO attendance_records
                        (id, mandate_id, session_id, present, absence_reason,
                         is_excused, source_document_id, source_observation_id,
                         source_record_sha256, recorded_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    attendance_values,
                )

                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, $2, $3,
                            CONCAT('Presenças factuais numa reunião plenária ',
                                   'para fiscalização democrática'),
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            CONCAT('A reunião, todos os BID, estados, mandatos, ',
                                   'fonte e arquivo foram revistos.'),
                            CONCAT('Publica a fotografia integral; não mede mérito ',
                                   'nem transforma falta em culpa.'),
                            TRUE, $4, $5, $6)
                    """,
                    review_id,
                    _SUBJECT_TYPE,
                    str(candidate["snapshot_id"]),
                    str(candidate["source_document_id"]),
                    actor.public_alias,
                    created_at,
                )

                audit_id = _new_id("audit")
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, $2, $3, 'PUBLISHED', $4,
                            $5::jsonb, $6::jsonb, $7, $8)
                    """,
                    audit_id,
                    _SUBJECT_TYPE,
                    str(candidate["snapshot_id"]),
                    actor.public_alias,
                    _canonical_json(
                        {
                            "publishable": False,
                            "case_reference_sha256": _reference_sha256(case_id),
                            "version_sha256": payload.expected_version_sha256,
                        }
                    ),
                    _canonical_json(
                        {
                            "publishable": True,
                            "source_sha256": payload.expected_source_sha256,
                            "snapshot_sha256": payload.expected_snapshot_sha256,
                            "mapping_sha256": payload.expected_mapping_sha256,
                            "publication_proof_sha256": (payload.expected_publication_proof_sha256),
                            "session_reference_sha256": _reference_sha256(session_id),
                            "attendance_records_created": len(attendance_ids),
                            "people_created": 0,
                            "mandates_created": 0,
                            "selective_processing": False,
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
                    action=EditorialAction.PUBLISH,
                    previous_state=EditorialState.APPROVED,
                    resulting_state=EditorialState.PUBLISHED,
                    case_revision=next_revision,
                    rationale=payload.rationale,
                    source_confirmed=True,
                    actor=actor,
                    created_at=created_at,
                )
                await self.editorial._insert_decision(
                    connection,
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.PUBLISH,
                    previous_state=EditorialState.APPROVED,
                    resulting_state=EditorialState.PUBLISHED,
                    case_revision=next_revision,
                    rationale=payload.rationale,
                    source_confirmed=True,
                    actor=actor,
                    decision_sha256=decision_sha256,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    UPDATE editorial_cases
                    SET current_state = 'PUBLISHED', revision = $2, updated_at = $3
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
                    action="PUBLISH",
                    target_id=str(candidate["snapshot_id"]),
                    rationale=payload.public_rationale,
                    actor_id=actor.staff_id,
                    actor_alias=actor.public_alias,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    INSERT INTO editorial_publication_events
                        (id, case_id, version_id, action, target_type, target_id,
                         rationale, actor_id, actor_alias, event_sha256, created_at)
                    VALUES ($1, $2, $3, 'PUBLISH'::"EditorialPublicationAction",
                            $4, $5, $6, $7, $8, $9, $10)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    _SUBJECT_TYPE,
                    str(candidate["snapshot_id"]),
                    payload.public_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )

                public_gate = await connection.fetchrow(
                    """
                    SELECT COUNT(*)::int AS record_count,
                           COUNT(*) FILTER (WHERE attendance.present = TRUE)::int
                               AS present_count,
                           COUNT(*) FILTER (
                               WHERE attendance.present = FALSE
                                 AND attendance.is_excused = TRUE
                           )::int AS justified_absence_count,
                           COUNT(*) FILTER (
                               WHERE attendance.present = FALSE
                                 AND attendance.is_excused = FALSE
                           )::int AS unjustified_absence_count
                    FROM parliamentary_sessions AS session
                    JOIN parliament_attendance_snapshots AS snapshot
                      ON snapshot.id = session.attendance_snapshot_id
                     AND snapshot.source_document_id = session.source_document_id
                    JOIN source_documents AS source
                      ON source.id = session.source_document_id
                    JOIN attendance_records AS attendance
                      ON attendance.session_id = session.id
                     AND attendance.source_document_id = source.id
                    JOIN parliament_attendance_observations AS observation
                      ON observation.id = attendance.source_observation_id
                     AND observation.snapshot_id = snapshot.id
                     AND observation.source_record_sha256 = attendance.source_record_sha256
                    JOIN mandates AS mandate
                      ON mandate.id = attendance.mandate_id
                     AND mandate.legislature = snapshot.legislature
                     AND mandate.started_at::date <= snapshot.meeting_date
                     AND (
                         mandate.ended_at IS NULL
                         OR mandate.ended_at::date >= snapshot.meeting_date
                     )
                    JOIN people AS person
                      ON person.id = mandate.person_id
                     AND person.source_id = observation.official_deputy_id
                     AND person.role = 'DEPUTY'
                     AND person.active = TRUE
                    JOIN LATERAL (
                        SELECT review.publishable
                        FROM data_publication_reviews AS review
                        WHERE review.entity_type = 'PERSON'
                          AND review.entity_id = person.id
                        ORDER BY review.reviewed_at DESC, review.id DESC
                        LIMIT 1
                    ) AS person_review ON person_review.publishable = TRUE
                    JOIN LATERAL (
                        SELECT review.publishable
                        FROM data_publication_reviews AS review
                        WHERE review.entity_type = 'MANDATE'
                          AND review.entity_id = mandate.id
                          AND review.source_document_id = mandate.source_document_id
                        ORDER BY review.reviewed_at DESC, review.id DESC
                        LIMIT 1
                    ) AS mandate_review ON mandate_review.publishable = TRUE
                    JOIN LATERAL (
                        SELECT review.publishable
                        FROM data_publication_reviews AS review
                        WHERE review.entity_type = $2
                          AND review.entity_id = snapshot.id
                          AND review.source_document_id = source.id
                        ORDER BY review.reviewed_at DESC, review.id DESC
                        LIMIT 1
                    ) AS attendance_review ON attendance_review.publishable = TRUE
                    WHERE snapshot.id = $1
                      AND source.publisher = 'PARLIAMENT'
                      AND source.kind = 'ATTENDANCE'
                      AND EXISTS (
                          SELECT 1
                          FROM source_archive_attestations AS attestation
                          WHERE attestation.source_document_id = source.id
                            AND attestation.content_sha256 = source.content_sha256
                            AND attestation.retrieval_url = source.url
                            AND attestation.retrieved_at = source.retrieved_at
                      )
                      AND (
                          (observation.status = 'PRESENT'
                           AND attendance.present = TRUE
                           AND attendance.is_excused IS NULL)
                          OR
                          (observation.status = 'JUSTIFIED_ABSENCE'
                           AND attendance.present = FALSE
                           AND attendance.is_excused = TRUE)
                          OR
                          (observation.status = 'UNJUSTIFIED_ABSENCE'
                           AND attendance.present = FALSE
                           AND attendance.is_excused = FALSE)
                      )
                    """,
                    str(candidate["snapshot_id"]),
                    _SUBJECT_TYPE,
                )
                assert public_gate is not None
                expected_counts = candidate["manifest_counts"]
                assert isinstance(expected_counts, dict)
                actual_counts = {
                    "records": int(public_gate["record_count"]),
                    "present": int(public_gate["present_count"]),
                    "justified_absence": int(public_gate["justified_absence_count"]),
                    "unjustified_absence": int(public_gate["unjustified_absence_count"]),
                    "unknown": 0,
                }
                if actual_counts != expected_counts:
                    raise EditorialSourceError(
                        "A projeção pública não satisfez a reunião integral e foi revertida"
                    )
        except asyncpg.IntegrityConstraintViolationError as exc:
            raise EditorialConflictError(
                "O processo, a reunião ou um mapeamento mudou; nada foi publicado"
            ) from exc

        return {
            "created": True,
            "case_id": case_id,
            "version_id": payload.expected_version_id,
            "state": EditorialState.PUBLISHED.value,
            "snapshot_id": str(candidate["snapshot_id"]),
            "session_id": session_id,
            "attendance_record_count": len(attendance_ids),
            "attendance_review_id": review_id,
            "audit_event_id": audit_id,
            "editorial_decision_id": decision_id,
            "publication_event_id": event_id,
            "source_sha256": payload.expected_source_sha256,
            "snapshot_sha256": payload.expected_snapshot_sha256,
            "mapping_sha256": payload.expected_mapping_sha256,
            "publication_proof_sha256": payload.expected_publication_proof_sha256,
            "people_created": 0,
            "mandates_created": 0,
            "party_links_created": 0,
            "automatic_publication": False,
            "selective_processing_allowed": False,
            "absence_is_noncompliance": False,
            "publication_rule": (
                "A reunião integral e toda a prova foram acrescentadas numa transação ADMIN "
                "com MFA; fonte, observações, linhas e histórico permanecem imutáveis."
            ),
        }
