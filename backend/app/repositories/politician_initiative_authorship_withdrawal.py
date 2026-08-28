"""Retirada transacional e imutável de uma autoria parlamentar publicada."""

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
    PoliticianInitiativeAuthorshipWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.politician_initiative_authorship_editorial import (
    PoliticianInitiativeAuthorshipEditorialRepository,
    _reference_sha256,
)
from app.repositories.politician_initiative_authorship_publication import (
    PoliticianInitiativeAuthorshipPublicationRepository,
    _canonical_json,
    _new_id,
    _publication_event_sha256,
    _publication_proof_sha256,
    _sha256_json,
)

_SUBJECT_TYPE = "PARLIAMENT_INITIATIVE_AUTHORSHIP"
_PROPOSAL_SCHEMA_VERSION = "politician-initiative-authorship-editorial-v1"
_WITHDRAWAL_SCHEMA_VERSION = "politician-initiative-authorship-withdrawal-v1"
_TARGET_TYPE = "POLITICIAN_INITIATIVE_AUTHORSHIP"
_PUBLICATION_EFFECT = {
    "authorships_to_create": 1,
    "authorship_reviews_to_append": 1,
    "authorship_audits_to_append": 1,
    "editorial_decisions_to_append": 1,
    "publication_events_to_append": 1,
    "people_to_create": 0,
    "initiatives_to_create": 0,
    "party_links_to_create": 0,
}


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


class PoliticianInitiativeAuthorshipWithdrawalRepository:
    """Retira a visibilidade de uma autoria sem apagar ou alterar a prova."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.candidates = PoliticianInitiativeAuthorshipEditorialRepository(pool)
        self.publisher = PoliticianInitiativeAuthorshipPublicationRepository(pool)

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
                raise EditorialNotFoundError("Processo editorial de autoria não encontrado")

        row = await connection.fetchrow(
            f"""
            SELECT editorial_case.id, editorial_case.subject_id,
                   editorial_case.source_document_id,
                   editorial_case.origin::text AS origin,
                   editorial_case.current_state::text AS current_state,
                   editorial_case.revision, editorial_case.current_version_id,
                   version.normalized_json, version.normalized_sha256,
                   latest_decision.action::text AS latest_decision_action,
                   latest_decision.resulting_state::text AS latest_decision_state,
                   latest_decision.case_revision AS latest_decision_case_revision,
                   latest_decision.version_id AS latest_decision_version_id,
                   latest_decision.source_confirmed AS latest_source_confirmed,
                   author_source.publisher::text AS source_publisher,
                   author_source.kind::text AS source_kind,
                   author_source.url AS source_url,
                   author_source.retrieved_at AS source_retrieved_at,
                   author_source.content_sha256 AS source_sha256,
                   author_archive.id AS author_archive_id,
                   author_archive.attestation_sha256 AS author_archive_attestation_sha256,
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
                   authorship.id AS authorship_id,
                   authorship.person_id, authorship.initiative_id,
                   authorship.source_observation_id,
                   authorship.relation AS authorship_relation,
                   authorship.source_document_id AS authorship_source_document_id,
                   authorship.source_record_sha256 AS authorship_source_record_sha256,
                   observation.snapshot_id AS author_snapshot_id,
                   observation.initiative_source_id,
                   observation.official_deputy_id,
                   observation.relation AS observation_relation,
                   observation.source_record_sha256 AS observation_source_record_sha256,
                   author_snapshot.source_document_id AS author_snapshot_source_document_id,
                   author_snapshot.legislature AS author_snapshot_legislature,
                   person.source_id AS person_source_id,
                   person.role::text AS person_role,
                   person.active AS person_active,
                   initiative.source_id AS public_initiative_source_id,
                   initiative.legislature AS public_initiative_legislature,
                   initiative.snapshot_id AS activity_snapshot_id,
                   initiative.source_document_id AS activity_source_document_id,
                   activity_snapshot.normalised_sha256 AS activity_snapshot_sha256,
                   activity_snapshot.source_document_id AS snapshot_activity_source_document_id,
                   activity_source.publisher::text AS activity_source_publisher,
                   activity_source.kind::text AS activity_source_kind,
                   activity_source.url AS activity_source_url,
                   activity_source.retrieved_at AS activity_source_retrieved_at,
                   activity_source.content_sha256 AS activity_source_sha256,
                   activity_archive.id AS activity_archive_id,
                   person_review.id AS person_review_id,
                   person_review.publishable AS person_publishable,
                   activity_review.id AS activity_review_id,
                   activity_review.publishable AS activity_publishable,
                   authorship_review.id AS authorship_review_id,
                   authorship_review.publishable AS authorship_publishable,
                   authorship_review.reviewed_at AS authorship_reviewed_at,
                   publication_audit.id AS publication_audit_event_id,
                   publication_audit.before_json AS publication_audit_before_json,
                   publication_audit.after_json AS publication_audit_after_json,
                   publication_audit.created_at AS publication_audit_created_at
            FROM editorial_cases AS editorial_case
            JOIN editorial_versions AS version
              ON version.id = editorial_case.current_version_id
             AND version.case_id = editorial_case.id
            JOIN source_documents AS author_source
              ON author_source.id = editorial_case.source_document_id
            LEFT JOIN LATERAL (
                SELECT decision.action, decision.resulting_state,
                       decision.case_revision, decision.version_id,
                       decision.source_confirmed
                FROM editorial_decisions AS decision
                WHERE decision.case_id = editorial_case.id
                ORDER BY decision.case_revision DESC, decision.id DESC
                LIMIT 1
            ) AS latest_decision ON TRUE
            LEFT JOIN LATERAL (
                SELECT attestation.id, attestation.attestation_sha256
                FROM source_archive_attestations AS attestation
                WHERE attestation.source_document_id = author_source.id
                  AND attestation.content_sha256 = author_source.content_sha256
                  AND attestation.retrieval_url = author_source.url
                  AND attestation.retrieved_at = author_source.retrieved_at
                ORDER BY attestation.archived_at ASC, attestation.id ASC
                LIMIT 1
            ) AS author_archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id, event.version_id, event.target_type,
                       event.target_id, event.rationale, event.actor_id,
                       event.actor_alias, event.event_sha256, event.created_at
                FROM editorial_publication_events AS event
                WHERE event.case_id = editorial_case.id
                  AND event.version_id = editorial_case.current_version_id
                  AND event.action = 'PUBLISH'::"EditorialPublicationAction"
                  AND event.target_type = '{_TARGET_TYPE}'
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS publication ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id
                FROM editorial_publication_events AS event
                WHERE event.case_id = editorial_case.id
                  AND event.version_id = editorial_case.current_version_id
                  AND event.action = 'WITHDRAW'::"EditorialPublicationAction"
                  AND event.target_type = '{_TARGET_TYPE}'
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS withdrawal ON TRUE
            LEFT JOIN politician_initiative_authorships AS authorship
              ON authorship.id = publication.target_id
             AND publication.target_type = '{_TARGET_TYPE}'
            LEFT JOIN parliament_initiative_author_observations AS observation
              ON observation.id = authorship.source_observation_id
            LEFT JOIN parliament_initiative_author_snapshots AS author_snapshot
              ON author_snapshot.id = observation.snapshot_id
            LEFT JOIN people AS person ON person.id = authorship.person_id
            LEFT JOIN parliamentary_initiatives AS initiative
              ON initiative.id = authorship.initiative_id
            LEFT JOIN parliament_activity_snapshots AS activity_snapshot
              ON activity_snapshot.id = initiative.snapshot_id
            LEFT JOIN source_documents AS activity_source
              ON activity_source.id = initiative.source_document_id
            LEFT JOIN LATERAL (
                SELECT attestation.id
                FROM source_archive_attestations AS attestation
                WHERE attestation.source_document_id = activity_source.id
                  AND attestation.content_sha256 = activity_source.content_sha256
                  AND attestation.retrieval_url = activity_source.url
                  AND attestation.retrieved_at = activity_source.retrieved_at
                ORDER BY attestation.archived_at ASC, attestation.id ASC
                LIMIT 1
            ) AS activity_archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'PERSON'
                  AND review.entity_id = person.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS person_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                  AND review.entity_id = activity_snapshot.id
                  AND review.source_document_id = activity_source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS activity_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable, review.reviewed_at
                FROM data_publication_reviews AS review
                WHERE review.entity_type = '{_TARGET_TYPE}'
                  AND review.entity_id = authorship.id
                  AND review.source_document_id = author_source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS authorship_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT audit.id, audit.before_json, audit.after_json, audit.created_at
                FROM audit_events AS audit
                WHERE audit.entity_type = '{_TARGET_TYPE}'
                  AND audit.entity_id = authorship.id
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
            raise EditorialNotFoundError("Processo editorial de autoria não encontrado")

        if lock and row["authorship_id"] is not None:
            await connection.fetchval(
                "SELECT id FROM politician_initiative_authorships WHERE id = $1 FOR UPDATE",
                str(row["authorship_id"]),
            )
            if row["person_id"] is not None:
                await connection.fetchval(
                    "SELECT id FROM people WHERE id = $1 FOR UPDATE",
                    str(row["person_id"]),
                )
            if row["initiative_id"] is not None:
                await connection.fetchval(
                    "SELECT id FROM parliamentary_initiatives WHERE id = $1 FOR UPDATE",
                    str(row["initiative_id"]),
                )
        return cast(Mapping[str, Any], row)

    async def _inspect_context(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, object]]:
        case = await self._case(connection, case_id=case_id, lock=lock)
        observation_id = str(case["subject_id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", observation_id):
            raise EditorialSourceError("A referência editorial da autoria deixou de ser válida")

        candidate = await self.candidates.get_exact_candidate(
            observation_id=observation_id,
            connection=connection,
        )
        if candidate is None:
            raise EditorialSourceError(
                "A autoria publicada deixou de corresponder à fonte oficial atestada"
            )
        normalized = _json_object_or_none(case["normalized_json"])
        if normalized is None:
            raise EditorialSourceError("A versão publicada deixou de ser um objeto JSON")
        source = candidate["source"]
        assert isinstance(source, dict)

        authorship_id = str(case["authorship_id"] or "")
        person_id = str(case["person_id"] or "")
        initiative_id = str(case["initiative_id"] or "")
        public_effect = await self._public_effect(
            connection,
            authorship_id=authorship_id,
            person_id=person_id,
            identity_review_positive=case["person_publishable"] is True,
            initiative_review_positive=case["activity_publishable"] is True,
        )
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
        if not self.publisher._proposal_matches_candidate(normalized, candidate):
            block(
                "PUBLISHED_VERSION_DRIFT",
                "A versão publicada diverge da autoria reconstruída no servidor.",
            )
        candidate_blockers = candidate["blocked_reasons"]
        assert isinstance(candidate_blockers, list)
        for detail in candidate_blockers:
            block("SOURCE_CANDIDATE_BLOCKED", str(detail))

        if case["withdrawal_event_id"] is not None:
            block("WITHDRAWAL_ALREADY_RECORDED", "A autoria já possui uma retirada imutável.")
        if not authorship_id:
            block("AUTHORSHIP_MISSING", "O evento de publicação já não encontra a autoria.")
        if str(case["publication_event_target_type"] or "") != _TARGET_TYPE:
            block("PUBLICATION_TARGET_INVALID", "O evento não aponta para uma autoria individual.")
        if str(case["publication_event_target_id"] or "") != authorship_id:
            block("PUBLICATION_TARGET_CHANGED", "O evento já não aponta para a ligação publicada.")
        if str(case["source_document_id"]) != str(candidate["source_document_id"]):
            block("SOURCE_DOCUMENT_CHANGED", "O documento oficial do processo deixou de coincidir.")
        if str(case["authorship_source_document_id"] or "") != str(case["source_document_id"]):
            block(
                "AUTHORSHIP_SOURCE_CHANGED", "A autoria deixou de apontar para a fonte publicada."
            )
        if str(case["source_observation_id"] or "") != observation_id:
            block(
                "AUTHORSHIP_OBSERVATION_CHANGED", "A autoria deixou de apontar para a observação."
            )
        if str(case["authorship_relation"] or "") != "AUTHOR":
            block(
                "AUTHORSHIP_RELATION_CHANGED", "A ligação deixou de ser a relação literal AUTHOR."
            )
        if str(case["observation_relation"] or "") != "AUTHOR":
            block("SOURCE_RELATION_CHANGED", "A fonte deixou de declarar a relação literal AUTHOR.")
        if _digest(case["authorship_source_record_sha256"]) != _digest(
            candidate["source_record_sha256"]
        ):
            block("AUTHORSHIP_RECORD_HASH_CHANGED", "O SHA-256 da autoria deixou de coincidir.")
        if _digest(case["observation_source_record_sha256"]) != _digest(
            candidate["source_record_sha256"]
        ):
            block("SOURCE_RECORD_HASH_CHANGED", "A observação já não tem o SHA-256 publicado.")
        if str(case["initiative_source_id"] or "") != str(candidate["initiative_source_id"]):
            block("OFFICIAL_INITIATIVE_ID_CHANGED", "O IniId da observação deixou de coincidir.")
        if str(case["official_deputy_id"] or "") != str(candidate["official_deputy_id"]):
            block("OFFICIAL_DEPUTY_ID_CHANGED", "O idCadastro da observação deixou de coincidir.")
        if str(case["person_source_id"] or "") != str(candidate["official_deputy_id"]):
            block("PERSON_ID_CHANGED", "A pessoa deixou de corresponder ao idCadastro oficial.")
        if str(case["person_role"] or "") != "DEPUTY" or case["person_active"] is not True:
            block("PERSON_NOT_ACTIVE_DEPUTY", "A identidade já não é um deputado ativo exato.")
        if str(case["public_initiative_source_id"] or "") != str(candidate["initiative_source_id"]):
            block(
                "PUBLIC_INITIATIVE_ID_CHANGED", "A iniciativa pública deixou de ter o IniId exato."
            )
        if str(case["public_initiative_legislature"] or "") != str(candidate["legislature"]):
            block(
                "PUBLIC_INITIATIVE_LEGISLATURE_CHANGED",
                "A iniciativa pertence a outra legislatura.",
            )
        if str(case["author_snapshot_id"] or "") != str(candidate["snapshot_id"]):
            block("AUTHOR_SNAPSHOT_CHANGED", "A observação já não pertence à fotografia publicada.")
        if str(case["author_snapshot_source_document_id"] or "") != str(case["source_document_id"]):
            block("AUTHOR_SNAPSHOT_SOURCE_CHANGED", "A fotografia de autoria mudou de fonte.")
        if str(case["author_snapshot_legislature"] or "") != str(candidate["legislature"]):
            block(
                "AUTHOR_SNAPSHOT_LEGISLATURE_CHANGED", "A fotografia pertence a outra legislatura."
            )
        if str(case["snapshot_activity_source_document_id"] or "") != str(
            case["activity_source_document_id"] or ""
        ):
            block("ACTIVITY_SNAPSHOT_SOURCE_CHANGED", "A fotografia pública mudou de fonte.")
        if case["person_review_id"] is None or case["person_publishable"] is not True:
            block("PERSON_REVIEW_INACTIVE", "A revisão pública da identidade já não está ativa.")
        if case["activity_review_id"] is None or case["activity_publishable"] is not True:
            block("ACTIVITY_REVIEW_INACTIVE", "A revisão pública da iniciativa já não está ativa.")
        if case["authorship_review_id"] is None or case["authorship_publishable"] is not True:
            block("AUTHORSHIP_REVIEW_INACTIVE", "A revisão pública da autoria já não está ativa.")
        if case["author_archive_id"] is None:
            block("AUTHOR_ARCHIVE_MISSING", "O arquivo exato da autoria já não está disponível.")
        if case["activity_archive_id"] is None:
            block(
                "ACTIVITY_ARCHIVE_MISSING", "O arquivo exato da iniciativa já não está disponível."
            )
        if (
            str(case["source_publisher"] or "") != "PARLIAMENT"
            or str(case["source_kind"] or "") == "NEWS_ARTICLE"
        ):
            block(
                "AUTHOR_SOURCE_NOT_OFFICIAL",
                "A fonte de autoria deixou de ser parlamentar oficial.",
            )
        if (
            str(case["activity_source_publisher"] or "") != "PARLIAMENT"
            or str(case["activity_source_kind"] or "") == "NEWS_ARTICLE"
        ):
            block("ACTIVITY_SOURCE_NOT_OFFICIAL", "A fonte da iniciativa deixou de ser oficial.")

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
        if str(case["publication_event_version_id"] or "") != str(case["current_version_id"]):
            block("PUBLICATION_EVENT_VERSION_CHANGED", "O evento já não aponta para esta versão.")

        audit_before = _json_object_or_none(case["publication_audit_before_json"])
        audit_after = _json_object_or_none(case["publication_audit_after_json"])
        if (
            case["publication_audit_event_id"] is None
            or audit_before is None
            or audit_after is None
        ):
            block("PUBLICATION_AUDIT_MISSING", "A auditoria da publicação está incompleta.")
        elif audit_after.get("publishable") is not True:
            block("PUBLICATION_AUDIT_INVALID", "A auditoria original não confirma publicação.")

        source_record_sha256 = _digest(candidate["source_record_sha256"]) or "0" * 64
        activity_snapshot_sha256 = _digest(case["activity_snapshot_sha256"]) or "0" * 64
        activity_source_sha256 = _digest(case["activity_source_sha256"]) or "0" * 64
        publication_proof_sha256 = _publication_proof_sha256(
            case_id=case_id,
            version_id=case["current_version_id"],
            version_sha256=case["normalized_sha256"],
            source_sha256=source["content_sha256"],
            source_record_sha256=source_record_sha256,
            observation_id=observation_id,
            person_id=person_id,
            official_deputy_id=candidate["official_deputy_id"],
            initiative_id=initiative_id,
            initiative_source_id=candidate["initiative_source_id"],
            activity_source_sha256=activity_source_sha256,
            activity_snapshot_sha256=activity_snapshot_sha256,
            relation="AUTHOR",
            public_effect=_PUBLICATION_EFFECT,
        )
        if audit_before is not None and audit_after is not None:
            audit_checks = (
                (audit_before.get("publishable"), False),
                (audit_before.get("case_reference_sha256"), _reference_sha256(case_id)),
                (audit_before.get("version_sha256"), str(case["normalized_sha256"])),
                (audit_after.get("authorship_source_sha256"), source["content_sha256"]),
                (audit_after.get("source_record_sha256"), source_record_sha256),
                (audit_after.get("activity_snapshot_sha256"), activity_snapshot_sha256),
                (
                    audit_after.get("observation_reference_sha256"),
                    _reference_sha256(observation_id),
                ),
                (
                    audit_after.get("official_deputy_id_reference_sha256"),
                    _reference_sha256(candidate["official_deputy_id"]),
                ),
                (
                    audit_after.get("initiative_source_id_reference_sha256"),
                    _reference_sha256(candidate["initiative_source_id"]),
                ),
                (audit_after.get("relation"), "AUTHOR"),
                (audit_after.get("people_created"), 0),
                (audit_after.get("initiatives_created"), 0),
                (audit_after.get("party_links_created"), 0),
                (audit_after.get("publication_proof_sha256"), publication_proof_sha256),
            )
            if any(received != expected for received, expected in audit_checks):
                block(
                    "PUBLICATION_AUDIT_PROOF_MISMATCH",
                    "A prova original já não corresponde às relações exatas atuais.",
                )
        if (
            case["publication_audit_created_at"] is not None
            and case["authorship_reviewed_at"] != case["publication_audit_created_at"]
        ):
            block("PUBLICATION_REVIEW_MISMATCH", "A revisão ativa não é a revisão publicada.")

        withdrawal_payload = {
            "schema_version": _WITHDRAWAL_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case_id),
            "version_reference_sha256": _reference_sha256(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "authorship_reference_sha256": _reference_sha256(authorship_id),
            "authorship_source_sha256": str(source["content_sha256"]),
            "source_record_sha256": source_record_sha256,
            "activity_snapshot_sha256": activity_snapshot_sha256,
            "publication_proof_sha256": publication_proof_sha256,
            "public_review_reference_sha256": _reference_sha256(case["authorship_review_id"]),
            "publication_audit_reference_sha256": _reference_sha256(
                case["publication_audit_event_id"]
            ),
            "publication_event_reference_sha256": _reference_sha256(case["publication_event_id"]),
            "publication_event_sha256": publication_event_sha256,
            "public_effect": public_effect,
            "authorship_row_preserved": True,
            "person_and_initiative_unchanged": True,
            "party_link_unchanged": True,
            "vote_or_collective_position_inference": False,
            "automatic_withdrawal": False,
        }
        eligible = not blockers
        preview: dict[str, object] = {
            "case_id": case_id,
            "case_state": str(case["current_state"]),
            "case_revision": int(case["revision"]),
            "version_id": str(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "authorship_id": authorship_id,
            "source": source,
            "source_record_sha256": source_record_sha256,
            "activity_snapshot_sha256": activity_snapshot_sha256,
            "publication_proof_sha256": publication_proof_sha256,
            "withdrawal_proof_sha256": _sha256_json(withdrawal_payload) if eligible else None,
            "public_review_id": str(case["authorship_review_id"] or ""),
            "publication_audit_event_id": str(case["publication_audit_event_id"] or ""),
            "publication_event_id": str(case["publication_event_id"] or ""),
            "publication_event_sha256": publication_event_sha256 or "0" * 64,
            "public_effect": public_effect,
            "public_effect_sha256": _sha256_json(public_effect),
            "eligible": eligible,
            "blockers": blockers,
            "automatic_withdrawal": False,
            "authorships_to_delete": 0,
            "people_to_delete": 0,
            "initiatives_to_delete": 0,
            "party_links_to_delete": 0,
            "withdrawal_rule": (
                "A revisão negativa, a auditoria, a decisão e o evento de retirada são "
                "acrescentados na mesma transação. A autoria e toda a prova original permanecem."
            ),
        }
        return preview, {"case": dict(case), "candidate": candidate}

    @staticmethod
    async def _public_effect(
        connection: asyncpg.Connection,
        *,
        authorship_id: str,
        person_id: str,
        identity_review_positive: bool,
        initiative_review_positive: bool,
    ) -> dict[str, object]:
        remaining = await connection.fetchval(
            """
            SELECT COUNT(*)::int
            FROM politician_initiative_authorships AS authorship
            JOIN parliament_initiative_author_observations AS observation
              ON observation.id = authorship.source_observation_id
             AND observation.relation = 'AUTHOR'
             AND observation.source_record_sha256 = authorship.source_record_sha256
            JOIN parliament_initiative_author_snapshots AS author_snapshot
              ON author_snapshot.id = observation.snapshot_id
             AND author_snapshot.source_document_id = authorship.source_document_id
            JOIN source_documents AS author_source
              ON author_source.id = authorship.source_document_id
            JOIN people AS person
              ON person.id = authorship.person_id
             AND person.source_id = observation.official_deputy_id
             AND person.role = 'DEPUTY'
             AND person.active = TRUE
            JOIN parliamentary_initiatives AS initiative
              ON initiative.id = authorship.initiative_id
             AND initiative.source_id = observation.initiative_source_id
             AND initiative.legislature = author_snapshot.legislature
            JOIN parliament_activity_snapshots AS activity_snapshot
              ON activity_snapshot.id = initiative.snapshot_id
             AND activity_snapshot.source_document_id = initiative.source_document_id
            JOIN source_documents AS activity_source
              ON activity_source.id = initiative.source_document_id
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
                WHERE review.entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                  AND review.entity_id = activity_snapshot.id
                  AND review.source_document_id = activity_source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS activity_review ON activity_review.publishable = TRUE
            JOIN LATERAL (
                SELECT review.publishable
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'POLITICIAN_INITIATIVE_AUTHORSHIP'
                  AND review.entity_id = authorship.id
                  AND review.source_document_id = author_source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS authorship_review ON authorship_review.publishable = TRUE
            WHERE authorship.person_id = $1
              AND authorship.id <> $2
              AND authorship.relation = 'AUTHOR'
              AND author_source.publisher = 'PARLIAMENT'
              AND author_source.kind <> 'NEWS_ARTICLE'
              AND activity_source.publisher = 'PARLIAMENT'
              AND activity_source.kind <> 'NEWS_ARTICLE'
              AND EXISTS (
                  SELECT 1 FROM source_archive_attestations AS archive
                  WHERE archive.source_document_id = author_source.id
                    AND archive.content_sha256 = author_source.content_sha256
                    AND archive.retrieval_url = author_source.url
                    AND archive.retrieved_at = author_source.retrieved_at
              )
              AND EXISTS (
                  SELECT 1 FROM source_archive_attestations AS archive
                  WHERE archive.source_document_id = activity_source.id
                    AND archive.content_sha256 = activity_source.content_sha256
                    AND archive.retrieval_url = activity_source.url
                    AND archive.retrieved_at = activity_source.retrieved_at
              )
            """,
            person_id,
            authorship_id,
        )
        return {
            "kind": "INITIATIVE_AUTHORSHIP_HIDDEN_HISTORY_PRESERVED",
            "authorship_reference_sha256": _reference_sha256(authorship_id),
            "identity_publication_review_unchanged": identity_review_positive,
            "initiative_publication_review_unchanged": initiative_review_positive,
            "exact_authorship_public_after_withdrawal": False,
            "remaining_public_authorships_for_person": int(remaining or 0),
            "authorship_row_preserved": True,
            "message": (
                "Esta autoria deixa de integrar a consulta ativa; a ligação, as duas fontes, "
                "a versão, a publicação e as identidades oficiais permanecem preservadas."
            ),
        }

    @staticmethod
    def _confirm_payload(
        *,
        case_id: str,
        preview: dict[str, object],
        payload: PoliticianInitiativeAuthorshipWithdrawalRequest,
    ) -> None:
        if case_id != payload.expected_case_id or str(preview["case_id"]) != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        source = cast(dict[str, object], preview["source"])
        confirmations = (
            (payload.expected_revision, preview["case_revision"], "revisão"),
            (payload.expected_version_id, preview["version_id"], "versão"),
            (payload.expected_version_sha256, preview["version_sha256"], "SHA-256 da versão"),
            (payload.expected_authorship_id, preview["authorship_id"], "autoria"),
            (payload.expected_source_sha256, source["content_sha256"], "SHA-256 da fonte"),
            (
                payload.expected_source_record_sha256,
                preview["source_record_sha256"],
                "SHA-256 da relação",
            ),
            (
                payload.expected_activity_snapshot_sha256,
                preview["activity_snapshot_sha256"],
                "fotografia pública",
            ),
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
        )
        for received, expected, label in confirmations:
            if received != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    async def withdraw(
        self,
        *,
        case_id: str,
        payload: PoliticianInitiativeAuthorshipWithdrawalRequest,
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
                    f"politician-initiative-authorship-publication:{case_id}",
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
                assert isinstance(case, dict)
                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")

                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'POLITICIAN_INITIATIVE_AUTHORSHIP', $2,
                            'Retirada documentada de autoria parlamentar da consulta ativa',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'A ligação permanece; só a revisão pública mais recente muda.',
                            'A decisão não altera pessoa, iniciativa, partido, fonte ou versão.',
                            FALSE, $3, $4, $5)
                    """,
                    review_id,
                    str(preview["authorship_id"]),
                    str(case["source_document_id"]),
                    actor.public_alias,
                    created_at,
                )

                internal_rationale = f"[{payload.reason_category.value}] {payload.rationale}"
                audit_id = _new_id("audit")
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, 'POLITICIAN_INITIATIVE_AUTHORSHIP', $2, 'WITHDRAWN', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    audit_id,
                    str(preview["authorship_id"]),
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
                            "authorship_source_sha256": payload.expected_source_sha256,
                            "source_record_sha256": payload.expected_source_record_sha256,
                            "activity_snapshot_sha256": (payload.expected_activity_snapshot_sha256),
                            "withdrawal_proof_sha256": (payload.expected_withdrawal_proof_sha256),
                            "public_effect": preview["public_effect"],
                            "public_effect_sha256": payload.expected_public_effect_sha256,
                            "withdrawal_reason_category": payload.reason_category.value,
                            "authorship_deleted": False,
                            "person_deleted": False,
                            "initiative_deleted": False,
                            "party_link_changed": False,
                            "vote_or_collective_position_inferred": False,
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
                    target_id=str(preview["authorship_id"]),
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
                            'POLITICIAN_INITIATIVE_AUTHORSHIP', $4, $5, $6, $7, $8, $9)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    str(preview["authorship_id"]),
                    internal_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )

                final = await connection.fetchrow(
                    """
                    SELECT EXISTS (
                               SELECT 1 FROM politician_initiative_authorships WHERE id = $1
                           ) AS authorship_preserved,
                           EXISTS (
                               SELECT 1
                               FROM politician_initiative_authorships AS authorship
                               JOIN LATERAL (
                                   SELECT review.publishable
                                   FROM data_publication_reviews AS review
                                   WHERE review.entity_type =
                                         'POLITICIAN_INITIATIVE_AUTHORSHIP'
                                     AND review.entity_id = authorship.id
                                     AND review.source_document_id =
                                         authorship.source_document_id
                                   ORDER BY review.reviewed_at DESC, review.id DESC
                                   LIMIT 1
                               ) AS latest_review ON latest_review.publishable = TRUE
                               WHERE authorship.id = $1
                           ) AS still_public
                    """,
                    str(preview["authorship_id"]),
                )
                if final is None or final["authorship_preserved"] is not True:
                    raise EditorialSourceError(
                        "A linha histórica deixou de existir; tudo foi revertido"
                    )
                if final["still_public"] is True:
                    raise EditorialSourceError("A autoria ainda seria pública; tudo foi revertido")
                confirmed_effect = await self._public_effect(
                    connection,
                    authorship_id=str(preview["authorship_id"]),
                    person_id=str(case["person_id"]),
                    identity_review_positive=case["person_publishable"] is True,
                    initiative_review_positive=case["activity_publishable"] is True,
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
            "authorship_id": payload.expected_authorship_id,
            "reason_category": payload.reason_category.value,
            "authorship_review_id": review_id,
            "audit_event_id": audit_id,
            "editorial_decision_id": decision_id,
            "withdrawal_event_id": event_id,
            "decision_sha256": decision_sha256,
            "event_sha256": event_sha256,
            "withdrawal_proof_sha256": payload.expected_withdrawal_proof_sha256,
            "public_effect": preview["public_effect"],
            "public_effect_sha256": payload.expected_public_effect_sha256,
            "authorships_deleted": 0,
            "people_deleted": 0,
            "initiatives_deleted": 0,
            "party_links_deleted": 0,
            "automatic_withdrawal": False,
            "withdrawal_rule": (
                "A revisão negativa, a auditoria, a decisão e o evento foram acrescentados "
                "numa transação ADMIN com MFA; a autoria e a publicação originais permanecem."
            ),
        }
