"""Retirada transacional e imutável de uma fotografia completa de perfis."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialState,
    PoliticianProfileSnapshotWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.politician_profile_editorial import _reference_sha256
from app.repositories.politician_profile_snapshot_publication import (
    _canonical_json,
    _iso_timestamp,
    _new_id,
    _publication_event_sha256,
    _sha256_json,
)

_WITHDRAWAL_SCHEMA_VERSION = "politician-profile-snapshot-withdrawal-v1"
_SNAPSHOT_ENTITY_TYPE = "PARLIAMENT_DEPUTY_SNAPSHOT"
_SUBJECT_TYPE = "PARLIAMENT_DEPUTY_OBSERVATION"


def _json_object(value: object) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return dict(value) if isinstance(value, dict) else None


def _digest(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def _https_url(value: object) -> bool:
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


class PoliticianProfileSnapshotWithdrawalRepository:
    """Retira todos os perfis da fotografia ou nenhum, sem apagar a projeção histórica."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    async def inspect(self, *, snapshot_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            snapshot = await self._snapshot(connection, snapshot_id=snapshot_id, lock=False)
            rows = await self._rows(connection, snapshot_id=snapshot_id)
            public_effect = await self._public_effect(
                connection,
                source_document_id=str(snapshot["source_document_id"]),
                legislature=str(snapshot["legislature"]),
            )
            return self._preview(snapshot=snapshot, rows=rows, public_effect=public_effect)

    async def withdraw(
        self,
        *,
        snapshot_id: str,
        payload: PoliticianProfileSnapshotWithdrawalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError("Esta retirada exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError("A retirada exige autenticação multifator")
        if snapshot_id != payload.expected_snapshot_id:
            raise EditorialConflictError("O pedido não confirma a fotografia indicada no URL")

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"politician-profile-snapshot-publication:{snapshot_id}",
                )
                snapshot = await self._snapshot(connection, snapshot_id=snapshot_id, lock=True)
                legislature = str(snapshot["legislature"])
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"parliament-people-publication:{legislature}",
                )
                await self._lock_targets(connection, snapshot_id=snapshot_id)
                snapshot = await self._snapshot(connection, snapshot_id=snapshot_id, lock=True)
                rows = await self._rows(connection, snapshot_id=snapshot_id)
                public_effect = await self._public_effect(
                    connection,
                    source_document_id=str(snapshot["source_document_id"]),
                    legislature=legislature,
                )
                preview = self._preview(
                    snapshot=snapshot,
                    rows=rows,
                    public_effect=public_effect,
                )
                self._confirm_payload(preview=preview, payload=payload)
                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    details = "; ".join(str(item["detail"]) for item in blockers)
                    raise EditorialSourceError(details)

                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")

                source_document_id = str(snapshot["source_document_id"])
                internal_rationale = f"[{payload.reason_category.value}] {payload.rationale}"
                person_review_ids: list[str] = []
                person_audit_ids: list[str] = []
                decision_ids: list[str] = []
                withdrawal_event_ids: list[str] = []

                for row in rows:
                    case_id = str(row["case_id"])
                    person_id = str(row["person_id"])
                    version_id = str(row["current_version_id"])
                    next_revision = int(row["case_revision"]) + 1

                    review_id = _new_id("publication_review")
                    await connection.execute(
                        """
                        INSERT INTO data_publication_reviews
                            (id, entity_type, entity_id, purpose, legal_basis,
                             sensitivity, necessity_assessment, proportionality_test,
                             publishable, source_document_id, reviewed_by, reviewed_at)
                        VALUES ($1, 'PERSON', $2,
                                'Retirada integral de fotografia parlamentar documentada',
                                'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                                'A identidade permanece preservada; a fotografia deixa de integrar '
                                'a consulta ativa.',
                                'A decisão abrange todos os perfis e mantém fonte, versões e '
                                'histórico.',
                                FALSE, $3, $4, $5)
                        """,
                        review_id,
                        person_id,
                        source_document_id,
                        actor.public_alias,
                        created_at,
                    )
                    person_review_ids.append(review_id)

                    audit_id = _new_id("audit")
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'PERSON', $2, 'WITHDRAWN', $3,
                                $4::jsonb, $5::jsonb, $6, $7)
                        """,
                        audit_id,
                        person_id,
                        actor.public_alias,
                        _canonical_json(
                            {
                                "publishable": True,
                                "publication_review_reference_sha256": _reference_sha256(
                                    str(row["person_review_id"])
                                ),
                                "publication_event_reference_sha256": _reference_sha256(
                                    str(row["publication_event_id"])
                                ),
                            }
                        ),
                        _canonical_json(
                            {
                                "publishable": False,
                                "snapshot_reference_sha256": _reference_sha256(snapshot_id),
                                "source_sha256": payload.expected_source_sha256,
                                "withdrawal_proof_sha256": (
                                    payload.expected_withdrawal_proof_sha256
                                ),
                                "public_effect_sha256": payload.expected_public_effect_sha256,
                                "withdrawal_reason_category": payload.reason_category.value,
                                "person_deleted": False,
                                "membership_deleted": False,
                            }
                        ),
                        payload.public_rationale,
                        created_at,
                    )
                    person_audit_ids.append(audit_id)

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
                    decision_ids.append(decision_id)

                    event_id = _new_id("editorial_publication")
                    event_sha256 = _publication_event_sha256(
                        event_id=event_id,
                        case_id=case_id,
                        version_id=version_id,
                        action="WITHDRAW",
                        target_id=person_id,
                        rationale=internal_rationale,
                        actor_id=actor.staff_id,
                        actor_alias=actor.public_alias,
                        created_at=created_at,
                    )
                    await connection.execute(
                        """
                        INSERT INTO editorial_publication_events
                            (id, case_id, version_id, action, target_type, target_id,
                             rationale, actor_id, actor_alias, event_sha256, created_at)
                        VALUES ($1, $2, $3, 'WITHDRAW'::"EditorialPublicationAction",
                                'PERSON', $4, $5, $6, $7, $8, $9)
                        """,
                        event_id,
                        case_id,
                        version_id,
                        person_id,
                        internal_rationale,
                        actor.staff_id,
                        actor.public_alias,
                        event_sha256,
                        created_at,
                    )
                    withdrawal_event_ids.append(event_id)

                if await self._source_is_public(
                    connection,
                    source_document_id=source_document_id,
                    legislature=legislature,
                ):
                    raise EditorialSourceError(
                        "A fotografia ainda seria consultável após a retirada; tudo foi revertido"
                    )

                snapshot_review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'PARLIAMENT_DEPUTY_SNAPSHOT', $2,
                            'Retirada integral de fotografia parlamentar documentada',
                            'PUBLIC_INTEREST', 'PUBLIC_OFFICIAL',
                            'A fotografia completa foi retirada por decisão humana explícita.',
                            'Fontes, pessoas, observações, versões e decisões permanecem intactas.',
                            FALSE, $3, $4, $5)
                    """,
                    snapshot_review_id,
                    snapshot_id,
                    source_document_id,
                    actor.public_alias,
                    created_at,
                )
                snapshot_audit_id = _new_id("audit")
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, 'PARLIAMENT_DEPUTY_SNAPSHOT', $2, 'WITHDRAWN', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    snapshot_audit_id,
                    snapshot_id,
                    actor.public_alias,
                    _canonical_json(
                        {
                            "publishable": True,
                            "publication_proof_sha256": (payload.expected_publication_proof_sha256),
                            "deputy_count": payload.expected_deputy_count,
                        }
                    ),
                    _canonical_json(
                        {
                            "publishable": False,
                            "withdrawal_proof_sha256": (payload.expected_withdrawal_proof_sha256),
                            "public_effect": public_effect,
                            "public_effect_sha256": payload.expected_public_effect_sha256,
                            "withdrawal_reason_category": payload.reason_category.value,
                            "people_deleted": 0,
                            "memberships_deleted": 0,
                            "versions_deleted": 0,
                        }
                    ),
                    payload.public_rationale,
                    created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError(
                "A fotografia já foi retirada ou mudou durante a confirmação"
            ) from exc

        return {
            "created": True,
            "snapshot_id": snapshot_id,
            "legislature": legislature,
            "state": EditorialState.WITHDRAWN.value,
            "reason_category": payload.reason_category.value,
            "deputy_count": payload.expected_deputy_count,
            "person_reviews_created": len(person_review_ids),
            "person_audits_created": len(person_audit_ids),
            "editorial_decisions_created": len(decision_ids),
            "withdrawal_events_created": len(withdrawal_event_ids),
            "snapshot_review_id": snapshot_review_id,
            "snapshot_audit_id": snapshot_audit_id,
            "withdrawal_proof_sha256": payload.expected_withdrawal_proof_sha256,
            "public_effect": public_effect,
            "public_effect_sha256": payload.expected_public_effect_sha256,
            "people_deleted": 0,
            "memberships_deleted": 0,
            "versions_deleted": 0,
            "withdrawal_rule": (
                "A fotografia inteira foi retirada numa só transação; pessoas, observações, "
                "fontes, versões, decisões e prova da publicação original permanecem."
            ),
        }

    @staticmethod
    async def _snapshot(
        connection: asyncpg.Connection,
        *,
        snapshot_id: str,
        lock: bool,
    ) -> asyncpg.Record:
        lock_clause = "FOR UPDATE OF snapshot, source" if lock else ""
        row = await connection.fetchrow(
            f"""
            SELECT snapshot.id, snapshot.source_document_id, snapshot.legislature,
                   snapshot.normalised_sha256, snapshot.collected_at,
                   snapshot.deputy_count, snapshot.group_period_count,
                   snapshot.situation_period_count, snapshot.office_period_count,
                   source.publisher::text AS source_publisher,
                   source.kind::text AS source_kind, source.url AS source_url,
                   source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256,
                   archive.id AS archive_id,
                   snapshot_review.id AS snapshot_review_id,
                   snapshot_review.publishable AS snapshot_publishable,
                   snapshot_review.reviewed_at AS snapshot_reviewed_at,
                   snapshot_review.reviewed_by AS snapshot_reviewed_by,
                   publication_audit.id AS publication_audit_id,
                   publication_audit.after_json AS publication_audit_after,
                   publication_audit.actor_alias AS publication_audit_actor,
                   publication_audit.created_at AS publication_audit_created_at,
                   materialised.deputy_count AS materialised_deputy_count,
                   materialised.group_period_count AS materialised_group_period_count,
                   materialised.situation_period_count AS materialised_situation_period_count,
                   materialised.office_period_count AS materialised_office_period_count
            FROM parliament_deputy_snapshots AS snapshot
            JOIN source_documents AS source ON source.id = snapshot.source_document_id
            LEFT JOIN LATERAL (
                SELECT attestation.id
                FROM source_archive_attestations AS attestation
                WHERE attestation.source_document_id = source.id
                  AND attestation.content_sha256 = source.content_sha256
                  AND attestation.retrieval_url = source.url
                  AND attestation.retrieved_at = source.retrieved_at
                ORDER BY attestation.archived_at ASC, attestation.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable, review.reviewed_at, review.reviewed_by
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'PARLIAMENT_DEPUTY_SNAPSHOT'
                  AND review.entity_id = snapshot.id
                  AND review.source_document_id = source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS snapshot_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT audit.id, audit.after_json, audit.actor_alias, audit.created_at
                FROM audit_events AS audit
                WHERE audit.entity_type = 'PARLIAMENT_DEPUTY_SNAPSHOT'
                  AND audit.entity_id = snapshot.id
                  AND audit.action = 'PUBLISHED'
                ORDER BY audit.created_at DESC, audit.id DESC
                LIMIT 1
            ) AS publication_audit ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS deputy_count,
                       COALESCE(SUM(jsonb_array_length(observation.parliamentary_groups)), 0)::int
                           AS group_period_count,
                       COALESCE(SUM(jsonb_array_length(observation.mandate_situations)), 0)::int
                           AS situation_period_count,
                       COALESCE(SUM(jsonb_array_length(observation.offices)), 0)::int
                           AS office_period_count
                FROM parliament_deputy_observations AS observation
                WHERE observation.snapshot_id = snapshot.id
            ) AS materialised ON TRUE
            WHERE snapshot.id = $1
            {lock_clause}
            """,
            snapshot_id,
        )
        if row is None:
            raise EditorialNotFoundError("Fotografia privada de deputados não encontrada")
        return row

    @staticmethod
    async def _lock_targets(connection: asyncpg.Connection, *, snapshot_id: str) -> None:
        await connection.fetch(
            """
            SELECT editorial_case.id
            FROM parliament_deputy_observations AS observation
            JOIN parliament_deputy_snapshots AS snapshot
              ON snapshot.id = observation.snapshot_id
            JOIN editorial_cases AS editorial_case
              ON editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
             AND editorial_case.subject_type = 'PARLIAMENT_DEPUTY_OBSERVATION'
             AND editorial_case.subject_id = observation.id
             AND editorial_case.source_document_id = snapshot.source_document_id
            WHERE snapshot.id = $1
            ORDER BY editorial_case.id
            FOR UPDATE OF editorial_case
            """,
            snapshot_id,
        )
        await connection.fetch(
            """
            SELECT person.id
            FROM parliament_deputy_observations AS observation
            JOIN people AS person ON person.source_id = observation.source_id
            WHERE observation.snapshot_id = $1
            ORDER BY person.id
            FOR UPDATE OF person
            """,
            snapshot_id,
        )
        await connection.fetch(
            """
            SELECT membership.id
            FROM parliament_deputy_observations AS observation
            JOIN people AS person ON person.source_id = observation.source_id
            JOIN parliament_deputy_snapshots AS snapshot
              ON snapshot.id = observation.snapshot_id
            JOIN parliamentary_membership_snapshots AS membership
              ON membership.person_id = person.id
             AND membership.legislature = snapshot.legislature
             AND membership.source_document_id = snapshot.source_document_id
            WHERE observation.snapshot_id = $1
            ORDER BY membership.id
            FOR UPDATE OF membership
            """,
            snapshot_id,
        )

    @staticmethod
    async def _rows(
        connection: asyncpg.Connection,
        *,
        snapshot_id: str,
    ) -> list[asyncpg.Record]:
        return list(
            await connection.fetch(
                """
                SELECT observation.id AS observation_id, observation.source_id,
                       person.id AS person_id, person.source_id AS person_source_id,
                       person.role::text AS person_role, person.active AS person_active,
                       membership.id AS membership_id,
                       membership.party_id AS membership_party_id,
                       editorial_case.id AS case_id,
                       editorial_case.origin::text AS case_origin,
                       editorial_case.current_state::text AS case_state,
                       editorial_case.revision AS case_revision,
                       editorial_case.current_version_id,
                       version.normalized_json, version.normalized_sha256,
                       person_review.id AS person_review_id,
                       person_review.publishable AS person_publishable,
                       person_review.reviewed_at AS person_reviewed_at,
                       person_review.reviewed_by AS person_reviewed_by,
                       publication.id AS publication_event_id,
                       publication.version_id AS publication_version_id,
                       publication.target_type AS publication_target_type,
                       publication.target_id AS publication_target_id,
                       publication.rationale AS publication_rationale,
                       publication.actor_id AS publication_actor_id,
                       publication.actor_alias AS publication_actor_alias,
                       publication.event_sha256 AS publication_event_sha256,
                       publication.created_at AS publication_created_at,
                       withdrawal.id AS withdrawal_event_id,
                       publication_audit.id AS person_publication_audit_id,
                       publication_audit.after_json AS person_publication_audit_after,
                       publication_audit.actor_alias AS person_publication_audit_actor,
                       publication_audit.created_at AS person_publication_audit_created_at,
                       (
                           SELECT COUNT(*)::int
                           FROM editorial_publication_events AS event
                           WHERE event.case_id = editorial_case.id
                       ) AS publication_event_count
                FROM parliament_deputy_observations AS observation
                JOIN parliament_deputy_snapshots AS snapshot
                  ON snapshot.id = observation.snapshot_id
                LEFT JOIN people AS person ON person.source_id = observation.source_id
                LEFT JOIN parliamentary_membership_snapshots AS membership
                  ON membership.person_id = person.id
                 AND membership.legislature = snapshot.legislature
                 AND membership.source_document_id = snapshot.source_document_id
                LEFT JOIN editorial_cases AS editorial_case
                  ON editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
                 AND editorial_case.subject_type = 'PARLIAMENT_DEPUTY_OBSERVATION'
                 AND editorial_case.subject_id = observation.id
                 AND editorial_case.source_document_id = snapshot.source_document_id
                LEFT JOIN editorial_versions AS version
                  ON version.id = editorial_case.current_version_id
                LEFT JOIN LATERAL (
                    SELECT review.id, review.publishable, review.reviewed_at, review.reviewed_by
                    FROM data_publication_reviews AS review
                    WHERE review.entity_type = 'PERSON'
                      AND review.entity_id = person.id
                      AND review.source_document_id = snapshot.source_document_id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) AS person_review ON TRUE
                LEFT JOIN LATERAL (
                    SELECT event.id, event.version_id, event.target_type, event.target_id,
                           event.rationale, event.actor_id, event.actor_alias,
                           event.event_sha256, event.created_at
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
                LEFT JOIN LATERAL (
                    SELECT audit.id, audit.after_json, audit.actor_alias, audit.created_at
                    FROM audit_events AS audit
                    WHERE audit.entity_type = 'PERSON'
                      AND audit.entity_id = person.id
                      AND audit.action = 'PUBLISHED'
                      AND audit.after_json ->> 'snapshot_reference_sha256' = $2
                    ORDER BY audit.created_at DESC, audit.id DESC
                    LIMIT 1
                ) AS publication_audit ON TRUE
                WHERE observation.snapshot_id = $1
                ORDER BY observation.source_id COLLATE "C", observation.id
                """,
                snapshot_id,
                _reference_sha256(snapshot_id),
            )
        )

    @staticmethod
    async def _public_effect(
        connection: asyncpg.Connection,
        *,
        source_document_id: str,
        legislature: str,
    ) -> dict[str, object]:
        row = await connection.fetchrow(
            """
            WITH reviewed_sources AS (
                SELECT membership.source_document_id, membership.legislature,
                       MAX(latest_review.reviewed_at) AS fully_reviewed_at,
                       source.retrieved_at, COUNT(*)::int AS profile_count
                FROM parliamentary_membership_snapshots AS membership
                JOIN source_documents AS source
                  ON source.id = membership.source_document_id
                JOIN LATERAL (
                    SELECT review.publishable, review.reviewed_at
                    FROM data_publication_reviews AS review
                    WHERE review.entity_type = 'PERSON'
                      AND review.entity_id = membership.person_id
                      AND review.source_document_id = membership.source_document_id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) AS latest_review ON latest_review.publishable = TRUE
                WHERE membership.legislature = $1
                  AND membership.source_document_id <> $2
                  AND source.publisher = 'PARLIAMENT'
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations AS archive
                      WHERE archive.source_document_id = source.id
                        AND archive.content_sha256 = source.content_sha256
                        AND archive.retrieval_url = source.url
                        AND archive.retrieved_at = source.retrieved_at
                  )
                GROUP BY membership.source_document_id, membership.legislature,
                         source.retrieved_at
                HAVING COUNT(*) = (
                    SELECT COUNT(*)
                    FROM parliamentary_membership_snapshots AS candidate
                    WHERE candidate.source_document_id = membership.source_document_id
                      AND candidate.legislature = membership.legislature
                )
            )
            SELECT reviewed.source_document_id, reviewed.profile_count,
                   reviewed.fully_reviewed_at,
                   source.url, source.retrieved_at, source.content_sha256
            FROM reviewed_sources AS reviewed
            JOIN source_documents AS source ON source.id = reviewed.source_document_id
            ORDER BY reviewed.fully_reviewed_at DESC,
                     reviewed.retrieved_at DESC, reviewed.source_document_id DESC
            LIMIT 1
            """,
            legislature,
            source_document_id,
        )
        if row is None:
            return {
                "kind": "DATA_UNAVAILABLE",
                "legislature": legislature,
                "message": (
                    "Depois da retirada não ficará outra fotografia integralmente aprovada; "
                    "a consulta mostrará dados indisponíveis."
                ),
            }
        verified_at = row["fully_reviewed_at"]
        retrieved_at = row["retrieved_at"]
        if not isinstance(verified_at, datetime) or not isinstance(retrieved_at, datetime):
            raise RuntimeError("A fotografia pública alternativa tem datas inválidas")
        return {
            "kind": "FALLBACK_TO_PREVIOUS_SNAPSHOT",
            "legislature": legislature,
            "source_document_reference_sha256": _reference_sha256(row["source_document_id"]),
            "profile_count": int(row["profile_count"]),
            "source_url": str(row["url"]),
            "source_retrieved_at": _iso_timestamp(retrieved_at),
            "source_sha256": str(row["content_sha256"]),
            "verified_at": _iso_timestamp(verified_at),
            "message": (
                "Depois da retirada, a consulta recuará para esta fotografia anterior ainda "
                "integralmente aprovada na mesma legislatura."
            ),
        }

    @staticmethod
    async def _source_is_public(
        connection: asyncpg.Connection,
        *,
        source_document_id: str,
        legislature: str,
    ) -> bool:
        return bool(
            await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM parliamentary_membership_snapshots AS membership
                    JOIN LATERAL (
                        SELECT review.publishable
                        FROM data_publication_reviews AS review
                        WHERE review.entity_type = 'PERSON'
                          AND review.entity_id = membership.person_id
                          AND review.source_document_id = membership.source_document_id
                        ORDER BY review.reviewed_at DESC, review.id DESC
                        LIMIT 1
                    ) AS latest_review ON latest_review.publishable = TRUE
                    WHERE membership.source_document_id = $1
                      AND membership.legislature = $2
                )
                """,
                source_document_id,
                legislature,
            )
        )

    @staticmethod
    def _preview(
        *,
        snapshot: asyncpg.Record,
        rows: list[asyncpg.Record],
        public_effect: dict[str, object],
    ) -> dict[str, object]:
        blockers: list[dict[str, object]] = []

        def block(code: str, detail: str, count: int = 1) -> None:
            blockers.append({"code": code, "detail": detail, "count": count})

        snapshot_id = str(snapshot["id"])
        source_document_id = str(snapshot["source_document_id"])
        source_sha256 = str(snapshot["source_sha256"] or "")
        snapshot_sha256 = str(snapshot["normalised_sha256"] or "")
        if str(snapshot["source_publisher"]) != "PARLIAMENT":
            block("SOURCE_NOT_PARLIAMENT", "A fonte deixou de estar identificada como Parlamento.")
        if str(snapshot["source_kind"]) == "NEWS_ARTICLE":
            block("SOURCE_KIND_NOT_ALLOWED", "Uma notícia não pode provar esta fotografia.")
        if not _https_url(snapshot["source_url"]):
            block("SOURCE_URL_INVALID", "A fonte oficial não possui um URL HTTPS válido.")
        if _digest(source_sha256) is None:
            block("SOURCE_SHA256_INVALID", "O SHA-256 dos bytes oficiais é inválido.")
        if _digest(snapshot_sha256) is None:
            block("SNAPSHOT_SHA256_INVALID", "O SHA-256 normalizado é inválido.")
        if snapshot["archive_id"] is None:
            block(
                "ARCHIVE_ATTESTATION_MISSING",
                "A prova arquivada já não coincide em URL, data e SHA-256.",
            )

        manifest_counts = {
            "deputies": int(snapshot["deputy_count"]),
            "group_periods": int(snapshot["group_period_count"]),
            "situation_periods": int(snapshot["situation_period_count"]),
            "office_periods": int(snapshot["office_period_count"]),
        }
        materialised_counts = {
            "deputies": int(snapshot["materialised_deputy_count"] or 0),
            "group_periods": int(snapshot["materialised_group_period_count"] or 0),
            "situation_periods": int(snapshot["materialised_situation_period_count"] or 0),
            "office_periods": int(snapshot["materialised_office_period_count"] or 0),
        }
        if manifest_counts != materialised_counts or len(rows) != manifest_counts["deputies"]:
            block(
                "SNAPSHOT_SET_MISMATCH",
                "A fotografia materializada deixou de coincidir com o manifesto imutável.",
            )
        if manifest_counts["deputies"] < 1:
            block("EMPTY_SNAPSHOT", "Uma fotografia vazia não pode ter sido publicada.")

        snapshot_reviewed_at = snapshot["snapshot_reviewed_at"]
        if snapshot["snapshot_review_id"] is None or snapshot["snapshot_publishable"] is not True:
            block(
                "SNAPSHOT_PUBLIC_REVIEW_INACTIVE",
                "A revisão pública mais recente da fotografia não está positiva.",
            )
        snapshot_audit_after = _json_object(snapshot["publication_audit_after"])
        publication_proof_sha256 = _digest(
            snapshot_audit_after.get("publication_proof_sha256")
            if snapshot_audit_after is not None
            else None
        )
        if snapshot["publication_audit_id"] is None or snapshot_audit_after is None:
            block(
                "SNAPSHOT_PUBLICATION_AUDIT_MISSING",
                "A fotografia não conserva a auditoria da publicação original.",
            )
        elif (
            snapshot_audit_after.get("publishable") is not True
            or snapshot_audit_after.get("deputy_count") != manifest_counts["deputies"]
            or snapshot_audit_after.get("mandates_created") != 0
            or snapshot_audit_after.get("party_links_created") != 0
        ):
            block(
                "SNAPSHOT_PUBLICATION_AUDIT_INVALID",
                "A auditoria original não prova a fotografia integral e as limitações declaradas.",
            )
        if publication_proof_sha256 is None:
            block(
                "PUBLICATION_PROOF_MISSING",
                "A auditoria original não conserva a prova SHA-256 da publicação.",
            )
        if (
            snapshot_reviewed_at is None
            or snapshot_reviewed_at != snapshot["publication_audit_created_at"]
            or snapshot["snapshot_reviewed_by"] != snapshot["publication_audit_actor"]
        ):
            block(
                "SNAPSHOT_PUBLICATION_BATCH_MISMATCH",
                "A revisão e a auditoria da fotografia não pertencem à mesma publicação.",
            )

        source_ids: set[str] = set()
        proof_entries: list[dict[str, str]] = []
        for row in rows:
            source_id = str(row["source_id"] or "").strip()
            if not source_id or source_id in source_ids:
                block(
                    "EXACT_IDENTIFIER_SET_INVALID",
                    "Existem DepId oficiais ausentes ou repetidos na fotografia.",
                )
            source_ids.add(source_id)

            if (
                row["person_id"] is None
                or str(row["person_source_id"] or "") != source_id
                or str(row["person_role"] or "") != "DEPUTY"
                or row["person_active"] is not True
            ):
                block(
                    "EXACT_PERSON_MISSING",
                    "Uma observação deixou de corresponder a uma identidade DEPUTY pelo "
                    "DepId exato.",
                )
            if row["membership_id"] is None:
                block(
                    "MEMBERSHIP_OBSERVATION_MISSING",
                    "Uma pessoa publicada perdeu a observação desta fotografia.",
                )
            if row["membership_party_id"] is not None:
                block(
                    "UNVERIFIED_PARTY_LINK_PRESENT",
                    "Uma observação contém uma filiação que a publicação não podia inferir.",
                )
            if (
                row["case_id"] is None
                or str(row["case_origin"] or "") != "INGESTION"
                or str(row["case_state"] or "") != "PUBLISHED"
                or row["current_version_id"] is None
            ):
                block(
                    "EDITORIAL_CASE_NOT_PUBLISHED",
                    "Um processo da fotografia já não está publicado na versão exata.",
                )

            normalized = _json_object(row["normalized_json"])
            version_sha256 = _digest(row["normalized_sha256"])
            if (
                normalized is None
                or version_sha256 is None
                or _sha256_json(normalized) != version_sha256
            ):
                block(
                    "EDITORIAL_VERSION_HASH_MISMATCH",
                    "Uma versão publicada já não coincide com o respetivo SHA-256.",
                )

            if row["person_review_id"] is None or row["person_publishable"] is not True:
                block(
                    "PERSON_PUBLIC_REVIEW_INACTIVE",
                    "A revisão pública mais recente de uma pessoa não está positiva.",
                )
            if (
                snapshot_reviewed_at is None
                or row["person_reviewed_at"] != snapshot_reviewed_at
                or row["person_reviewed_by"] != snapshot["snapshot_reviewed_by"]
            ):
                block(
                    "PERSON_PUBLICATION_BATCH_MISMATCH",
                    "Uma revisão individual não pertence à publicação integral da fotografia.",
                )

            publication_created_at = row["publication_created_at"]
            event_sha256 = _digest(row["publication_event_sha256"])
            if row["publication_event_id"] is None or not isinstance(
                publication_created_at, datetime
            ):
                block(
                    "PUBLICATION_EVENT_MISSING",
                    "Um perfil não conserva o evento imutável de publicação.",
                )
            else:
                rebuilt = _publication_event_sha256(
                    event_id=str(row["publication_event_id"]),
                    case_id=str(row["case_id"]),
                    version_id=str(row["publication_version_id"]),
                    action="PUBLISH",
                    target_id=str(row["publication_target_id"]),
                    rationale=str(row["publication_rationale"]),
                    actor_id=str(row["publication_actor_id"]),
                    actor_alias=str(row["publication_actor_alias"]),
                    created_at=publication_created_at,
                )
                if rebuilt != event_sha256:
                    block(
                        "PUBLICATION_EVENT_HASH_MISMATCH",
                        "Um evento de publicação já não corresponde ao respetivo SHA-256.",
                    )
            if (
                str(row["publication_version_id"] or "") != str(row["current_version_id"] or "")
                or str(row["publication_target_type"] or "") != "PERSON"
                or str(row["publication_target_id"] or "") != str(row["person_id"] or "")
                or row["withdrawal_event_id"] is not None
                or int(row["publication_event_count"] or 0) != 1
            ):
                block(
                    "PUBLICATION_EVENT_TARGET_MISMATCH",
                    "O histórico editorial não corresponde a uma única publicação ativa.",
                )
            if (
                publication_created_at != snapshot_reviewed_at
                or row["publication_actor_alias"] != snapshot["snapshot_reviewed_by"]
            ):
                block(
                    "PUBLICATION_EVENT_BATCH_MISMATCH",
                    "Um evento individual não pertence à publicação integral da fotografia.",
                )

            person_audit_after = _json_object(row["person_publication_audit_after"])
            if row["person_publication_audit_id"] is None or person_audit_after is None:
                block(
                    "PERSON_PUBLICATION_AUDIT_MISSING",
                    "Um perfil não conserva a auditoria pública original.",
                )
            elif (
                person_audit_after.get("publishable") is not True
                or person_audit_after.get("snapshot_reference_sha256")
                != _reference_sha256(snapshot_id)
                or person_audit_after.get("source_sha256") != source_sha256
                or person_audit_after.get("official_deputy_id_reference_sha256")
                != _reference_sha256(source_id)
                or person_audit_after.get("mandate_created") is not False
                or person_audit_after.get("party_link_created") is not False
            ):
                block(
                    "PERSON_PUBLICATION_AUDIT_INVALID",
                    "Uma auditoria individual diverge da fonte e das limitações publicadas.",
                )
            if (
                row["person_publication_audit_created_at"] != snapshot_reviewed_at
                or row["person_publication_audit_actor"] != snapshot["snapshot_reviewed_by"]
            ):
                block(
                    "PERSON_PUBLICATION_AUDIT_BATCH_MISMATCH",
                    "Uma auditoria individual não pertence à publicação integral da fotografia.",
                )

            if all(
                value is not None
                for value in (
                    row["case_id"],
                    row["current_version_id"],
                    row["person_id"],
                    row["person_review_id"],
                    row["publication_event_id"],
                    row["person_publication_audit_id"],
                    version_sha256,
                    event_sha256,
                )
            ):
                proof_entries.append(
                    {
                        "case_reference_sha256": _reference_sha256(row["case_id"]),
                        "version_sha256": str(version_sha256),
                        "person_reference_sha256": _reference_sha256(row["person_id"]),
                        "review_reference_sha256": _reference_sha256(row["person_review_id"]),
                        "publication_event_reference_sha256": _reference_sha256(
                            row["publication_event_id"]
                        ),
                        "publication_event_sha256": str(event_sha256),
                        "audit_reference_sha256": _reference_sha256(
                            row["person_publication_audit_id"]
                        ),
                    }
                )

        public_effect_sha256 = _sha256_json(public_effect)
        proof_payload = {
            "schema_version": _WITHDRAWAL_SCHEMA_VERSION,
            "snapshot_reference_sha256": _reference_sha256(snapshot_id),
            "source_document_reference_sha256": _reference_sha256(source_document_id),
            "source_sha256": source_sha256,
            "snapshot_sha256": snapshot_sha256,
            "publication_proof_sha256": publication_proof_sha256,
            "snapshot_review_reference_sha256": _reference_sha256(
                snapshot["snapshot_review_id"] or ""
            ),
            "snapshot_audit_reference_sha256": _reference_sha256(
                snapshot["publication_audit_id"] or ""
            ),
            "deputy_count": manifest_counts["deputies"],
            "published_profiles": proof_entries,
            "public_effect": public_effect,
            "public_effect_sha256": public_effect_sha256,
            "removal_scope": "COMPLETE_SNAPSHOT_ONLY",
            "people_deleted": 0,
            "memberships_deleted": 0,
            "versions_deleted": 0,
        }
        eligible = not blockers and len(proof_entries) == manifest_counts["deputies"]
        return {
            "snapshot_id": snapshot_id,
            "legislature": str(snapshot["legislature"]),
            "source": {
                "url": str(snapshot["source_url"]),
                "retrieved_at": snapshot["source_retrieved_at"],
                "content_sha256": source_sha256,
            },
            "normalised_sha256": snapshot_sha256,
            "collected_at": snapshot["collected_at"],
            "manifest_counts": manifest_counts,
            "materialised_counts": materialised_counts,
            "publication_proof_sha256": publication_proof_sha256 or "0" * 64,
            "withdrawal_proof_sha256": _sha256_json(proof_payload) if eligible else None,
            "public_effect": public_effect,
            "public_effect_sha256": public_effect_sha256,
            "published_profile_count": len(proof_entries),
            "eligible": eligible,
            "blockers": blockers,
            "automatic_withdrawal": False,
            "people_to_delete": 0,
            "memberships_to_delete": 0,
            "versions_to_delete": 0,
            "withdrawal_rule": (
                "Só um administrador com MFA pode retirar a fotografia inteira. A ação acrescenta "
                "revisões, auditorias, decisões e eventos; nunca apaga pessoas ou histórico."
            ),
        }

    @staticmethod
    def _confirm_payload(
        *,
        preview: dict[str, object],
        payload: PoliticianProfileSnapshotWithdrawalRequest,
    ) -> None:
        manifest_counts = preview["manifest_counts"]
        source = preview["source"]
        assert isinstance(manifest_counts, dict)
        assert isinstance(source, dict)
        confirmations = (
            (payload.expected_snapshot_id, preview["snapshot_id"], "fotografia"),
            (payload.expected_source_sha256, source["content_sha256"], "SHA-256 da fonte"),
            (
                payload.expected_snapshot_sha256,
                preview["normalised_sha256"],
                "SHA-256 normalizado",
            ),
            (
                payload.expected_publication_proof_sha256,
                preview["publication_proof_sha256"],
                "prova da publicação original",
            ),
            (
                payload.expected_withdrawal_proof_sha256,
                preview["withdrawal_proof_sha256"],
                "prova integral da retirada",
            ),
            (
                payload.expected_public_effect_sha256,
                preview["public_effect_sha256"],
                "efeito público calculado",
            ),
            (payload.expected_deputy_count, manifest_counts["deputies"], "contagem de deputados"),
        )
        for received, expected, label in confirmations:
            if received != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")
