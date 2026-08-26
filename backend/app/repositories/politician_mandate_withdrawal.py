"""Retirada transacional e imutável de um mandato parlamentar publicado."""

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
    PoliticianMandateWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.politician_mandate_editorial import (
    PoliticianMandateEditorialRepository,
    _reference_sha256,
)
from app.repositories.politician_mandate_publication import (
    _OFFICE_TITLE,
    _canonical_json,
    _database_timestamp,
    _json_object,
    _mandate_publication_proof_sha256,
    _new_id,
    _publication_event_sha256,
    _sha256_json,
    _subject_parts,
)

_SUBJECT_TYPE = "PARLIAMENT_MANDATE_SITUATION"
_PROPOSAL_SCHEMA_VERSION = "politician-mandate-editorial-v1"
_WITHDRAWAL_SCHEMA_VERSION = "politician-mandate-withdrawal-v1"
_PUBLICATION_EFFECT = {
    "mandates_to_create": 1,
    "mandate_reviews_to_append": 1,
    "mandate_audits_to_append": 1,
    "editorial_decisions_to_append": 1,
    "publication_events_to_append": 1,
    "people_to_create": 0,
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


class PoliticianMandateWithdrawalRepository:
    """Retira a visibilidade de um mandato sem apagar ou alterar a sua prova."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.candidates = PoliticianMandateEditorialRepository(pool)

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
                raise EditorialNotFoundError("Processo editorial de mandato não encontrado")

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
                   source.publisher::text AS source_publisher,
                   source.kind::text AS source_kind, source.url AS source_url,
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
                   mandate.id AS mandate_id, mandate.person_id,
                   mandate.party_id AS mandate_party_id,
                   mandate.legislature AS mandate_legislature,
                   mandate.office_title AS mandate_office_title,
                   mandate.constituency AS mandate_constituency,
                   mandate.started_at AS mandate_started_at,
                   mandate.ended_at AS mandate_ended_at,
                   mandate.source_document_id AS mandate_source_document_id,
                   mandate.source_observation_id,
                   mandate.source_period_ordinal,
                   mandate.source_period_sha256,
                   observation.source_id AS official_deputy_id,
                   observation.snapshot_id,
                   snapshot.source_document_id AS snapshot_source_document_id,
                   snapshot.legislature AS snapshot_legislature,
                   person.role::text AS person_role, person.active AS person_active,
                   membership.id AS membership_id,
                   membership.constituency AS membership_constituency,
                   membership.party_id AS membership_party_id,
                   person_review.id AS person_review_id,
                   person_review.publishable AS person_publishable,
                   mandate_review.id AS mandate_review_id,
                   mandate_review.publishable AS mandate_publishable,
                   mandate_review.reviewed_at AS mandate_reviewed_at,
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
                WHERE attestation.source_document_id = source.id
                  AND attestation.content_sha256 = source.content_sha256
                  AND attestation.retrieval_url = source.url
                  AND attestation.retrieved_at = source.retrieved_at
                ORDER BY attestation.archived_at ASC, attestation.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id, event.version_id, event.target_type,
                       event.target_id, event.rationale, event.actor_id,
                       event.actor_alias, event.event_sha256, event.created_at
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
            LEFT JOIN mandates AS mandate
              ON mandate.id = publication.target_id
             AND publication.target_type = 'MANDATE'
            LEFT JOIN parliament_deputy_observations AS observation
              ON observation.id = mandate.source_observation_id
            LEFT JOIN parliament_deputy_snapshots AS snapshot
              ON snapshot.id = observation.snapshot_id
            LEFT JOIN people AS person ON person.id = mandate.person_id
            LEFT JOIN parliamentary_membership_snapshots AS membership
              ON membership.person_id = person.id
             AND membership.source_document_id = source.id
             AND membership.legislature = mandate.legislature
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'PERSON'
                  AND review.entity_id = person.id
                  AND review.source_document_id = source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS person_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable, review.reviewed_at
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'MANDATE'
                  AND review.entity_id = mandate.id
                  AND review.source_document_id = source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS mandate_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT audit.id, audit.before_json, audit.after_json, audit.created_at
                FROM audit_events AS audit
                WHERE audit.entity_type = 'MANDATE'
                  AND audit.entity_id = mandate.id
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
            raise EditorialNotFoundError("Processo editorial de mandato não encontrado")

        if lock and row["mandate_id"] is not None:
            await connection.fetchval(
                "SELECT id FROM mandates WHERE id = $1 FOR UPDATE",
                str(row["mandate_id"]),
            )
            if row["person_id"] is not None:
                await connection.fetchval(
                    "SELECT id FROM people WHERE id = $1 FOR UPDATE",
                    str(row["person_id"]),
                )
            if row["membership_id"] is not None:
                await connection.fetchval(
                    "SELECT id FROM parliamentary_membership_snapshots WHERE id = $1 FOR UPDATE",
                    str(row["membership_id"]),
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
        observation_id, period_ordinal = _subject_parts(case["subject_id"])
        normalized = _json_object(case["normalized_json"])
        mandate_candidate = normalized.get("mandate_candidate")
        if not isinstance(mandate_candidate, dict):
            raise EditorialSourceError("A versão publicada perdeu o candidato a mandato")
        period_sha256 = _digest(mandate_candidate.get("source_period_sha256"))
        if period_sha256 is None:
            raise EditorialSourceError("A versão publicada perdeu o SHA-256 do intervalo")

        candidate = await self.candidates.get_exact_candidate(
            observation_id=observation_id,
            source_period_sha256=period_sha256,
            connection=connection,
        )
        if candidate is None:
            raise EditorialSourceError(
                "O intervalo publicado deixou de corresponder à fonte oficial atestada"
            )
        source_period = candidate["source_period"]
        constituency = candidate["constituency"]
        source = candidate["source"]
        assert isinstance(source_period, dict)
        assert isinstance(constituency, dict)
        assert isinstance(source, dict)

        mandate_id = str(case["mandate_id"] or "")
        person_id = str(case["person_id"] or "")
        public_effect = await self._public_effect(
            connection,
            mandate_id=mandate_id,
            person_id=person_id,
            identity_review_positive=case["person_publishable"] is True,
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
        if normalized != self.candidates._normalized_proposal(candidate):
            block(
                "PUBLISHED_VERSION_DRIFT",
                "A versão publicada diverge da prova oficial reconstruída no servidor.",
            )
        candidate_blockers = candidate["blocked_reasons"]
        assert isinstance(candidate_blockers, list)
        for detail in candidate_blockers:
            block("SOURCE_CANDIDATE_BLOCKED", str(detail))

        if case["withdrawal_event_id"] is not None:
            block("WITHDRAWAL_ALREADY_RECORDED", "O mandato já possui uma retirada imutável.")
        if not mandate_id:
            block("MANDATE_MISSING", "O evento de publicação já não encontra o mandato exato.")
        if str(case["publication_event_target_type"] or "") != "MANDATE":
            block("PUBLICATION_TARGET_INVALID", "O evento não aponta para um mandato.")
        if str(case["source_document_id"]) != str(candidate["source_document_id"]):
            block("SOURCE_DOCUMENT_CHANGED", "O documento oficial do processo deixou de coincidir.")
        if str(case["mandate_source_document_id"] or "") != str(case["source_document_id"]):
            block("MANDATE_SOURCE_CHANGED", "O mandato deixou de apontar para a fonte publicada.")
        if str(case["source_observation_id"] or "") != observation_id:
            block("MANDATE_OBSERVATION_CHANGED", "O mandato deixou de apontar para a observação.")
        if int(case["source_period_ordinal"] or 0) != period_ordinal:
            block("MANDATE_PERIOD_CHANGED", "A posição do intervalo deixou de coincidir.")
        if _digest(case["source_period_sha256"]) != period_sha256:
            block("MANDATE_PERIOD_HASH_CHANGED", "O SHA-256 do intervalo deixou de coincidir.")
        if str(case["mandate_office_title"] or "") != _OFFICE_TITLE:
            block("MANDATE_OFFICE_CHANGED", "O cargo publicado deixou de ser o cargo revisto.")
        if str(case["mandate_legislature"] or "") != str(candidate["legislature"]):
            block("MANDATE_LEGISLATURE_CHANGED", "A legislatura publicada deixou de coincidir.")
        if str(case["mandate_constituency"] or "") != str(constituency["label"] or ""):
            block("MANDATE_CONSTITUENCY_CHANGED", "O círculo publicado deixou de coincidir.")
        if case["mandate_party_id"] is not None or case["membership_party_id"] is not None:
            block("PARTY_LINK_OUT_OF_SCOPE", "Foi encontrada uma filiação fora desta porta.")
        if str(case["person_role"] or "") != "DEPUTY" or case["person_active"] is not True:
            block("PERSON_NOT_ACTIVE_DEPUTY", "O DepId já não está ligado à identidade prevista.")
        if str(case["official_deputy_id"] or "") != str(candidate["official_deputy_id"]):
            block("OFFICIAL_ID_CHANGED", "O DepId relacional deixou de coincidir.")
        if str(case["snapshot_source_document_id"] or "") != str(case["source_document_id"]):
            block("SNAPSHOT_SOURCE_CHANGED", "A fotografia deixou de apontar para a mesma fonte.")
        if str(case["snapshot_legislature"] or "") != str(candidate["legislature"]):
            block("SNAPSHOT_LEGISLATURE_CHANGED", "A fotografia pertence a outra legislatura.")
        if case["membership_id"] is None or str(case["membership_constituency"] or "") != str(
            constituency["label"] or ""
        ):
            block("MEMBERSHIP_CHANGED", "A identidade e o círculo já não coincidem exatamente.")
        if case["person_review_id"] is None or case["person_publishable"] is not True:
            block("PERSON_REVIEW_INACTIVE", "A revisão pública da identidade já não está ativa.")
        if case["mandate_review_id"] is None or case["mandate_publishable"] is not True:
            block("MANDATE_REVIEW_INACTIVE", "A revisão pública do mandato já não está ativa.")
        if case["archive_id"] is None:
            block("ARCHIVE_MISSING", "A atestação exata do arquivo oficial já não está disponível.")
        if (
            str(case["source_publisher"] or "") != "PARLIAMENT"
            or str(case["source_kind"] or "") == "NEWS_ARTICLE"
        ):
            block("SOURCE_NOT_OFFICIAL", "A origem relacional deixou de ser parlamentar oficial.")

        expected_started_at: datetime | None
        expected_ended_at: datetime | None
        try:
            expected_started_at = _database_timestamp(source_period["starts_at"])
            expected_ended_at = (
                _database_timestamp(source_period["ends_at"])
                if source_period["ends_at"] is not None
                else None
            )
        except EditorialSourceError as exc:
            block("SOURCE_PERIOD_INVALID", str(exc))
            expected_started_at = expected_ended_at = None
        if case["mandate_started_at"] != expected_started_at:
            block("MANDATE_START_CHANGED", "A data inicial publicada deixou de coincidir.")
        if case["mandate_ended_at"] != expected_ended_at:
            block("MANDATE_END_CHANGED", "A data final publicada deixou de coincidir.")

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
            or str(case["publication_event_target_id"] or "") != mandate_id
        ):
            block(
                "PUBLICATION_EVENT_LINK_CHANGED",
                "O evento já não aponta para esta versão e alvo.",
            )

        audit_before = _json_object_or_none(case["publication_audit_before_json"])
        audit_after = _json_object_or_none(case["publication_audit_after_json"])
        if (
            case["publication_audit_event_id"] is None
            or audit_before is None
            or audit_after is None
        ):
            block(
                "PUBLICATION_AUDIT_MISSING",
                "A auditoria da publicação original está incompleta.",
            )
        elif audit_after.get("publishable") is not True:
            block("PUBLICATION_AUDIT_INVALID", "A auditoria original não confirma publicação.")

        publication_proof_sha256 = _mandate_publication_proof_sha256(
            case_id=case_id,
            version_id=case["current_version_id"],
            version_sha256=case["normalized_sha256"],
            source_sha256=source["content_sha256"],
            observation_id=observation_id,
            person_id=person_id,
            source_period_ordinal=period_ordinal,
            source_period_sha256=period_sha256,
            legislature=candidate["legislature"],
            constituency=constituency["label"],
            started_at=source_period["starts_at"],
            ended_at=source_period["ends_at"],
            public_effect=_PUBLICATION_EFFECT,
        )
        if audit_before is not None and audit_after is not None:
            audit_checks = (
                (audit_before.get("publishable"), False),
                (audit_before.get("case_reference_sha256"), _reference_sha256(case_id)),
                (audit_before.get("version_sha256"), str(case["normalized_sha256"])),
                (audit_after.get("source_sha256"), source["content_sha256"]),
                (audit_after.get("source_period_sha256"), period_sha256),
                (
                    audit_after.get("observation_reference_sha256"),
                    _reference_sha256(observation_id),
                ),
                (
                    audit_after.get("official_deputy_id_reference_sha256"),
                    _reference_sha256(candidate["official_deputy_id"]),
                ),
                (audit_after.get("publication_proof_sha256"), publication_proof_sha256),
                (audit_after.get("party_link_created"), False),
            )
            if any(received != expected for received, expected in audit_checks):
                block(
                    "PUBLICATION_AUDIT_PROOF_MISMATCH",
                    "A prova pública original já não corresponde às relações atuais.",
                )
        if (
            case["publication_audit_created_at"] is not None
            and case["mandate_reviewed_at"] != case["publication_audit_created_at"]
        ):
            block("PUBLICATION_REVIEW_MISMATCH", "A revisão ativa não é a revisão publicada.")

        withdrawal_payload = {
            "schema_version": _WITHDRAWAL_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case_id),
            "version_reference_sha256": _reference_sha256(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "mandate_reference_sha256": _reference_sha256(mandate_id),
            "source_sha256": str(source["content_sha256"]),
            "source_period_sha256": period_sha256,
            "publication_proof_sha256": publication_proof_sha256,
            "public_review_reference_sha256": _reference_sha256(case["mandate_review_id"]),
            "publication_audit_reference_sha256": _reference_sha256(
                case["publication_audit_event_id"]
            ),
            "publication_event_reference_sha256": _reference_sha256(case["publication_event_id"]),
            "publication_event_sha256": publication_event_sha256,
            "public_effect": public_effect,
            "mandate_row_preserved": True,
            "person_and_membership_unchanged": True,
            "automatic_withdrawal": False,
        }
        eligible = not blockers
        preview: dict[str, object] = {
            "case_id": case_id,
            "case_state": str(case["current_state"]),
            "case_revision": int(case["revision"]),
            "version_id": str(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "mandate_id": mandate_id,
            "source": source,
            "source_period_sha256": period_sha256,
            "publication_proof_sha256": publication_proof_sha256,
            "withdrawal_proof_sha256": _sha256_json(withdrawal_payload) if eligible else None,
            "public_review_id": str(case["mandate_review_id"] or ""),
            "publication_audit_event_id": str(case["publication_audit_event_id"] or ""),
            "publication_event_id": str(case["publication_event_id"] or ""),
            "publication_event_sha256": publication_event_sha256 or "0" * 64,
            "public_effect": public_effect,
            "public_effect_sha256": _sha256_json(public_effect),
            "eligible": eligible,
            "blockers": blockers,
            "automatic_withdrawal": False,
            "mandates_to_delete": 0,
            "people_to_delete": 0,
            "memberships_to_delete": 0,
            "withdrawal_rule": (
                "A revisão negativa, a auditoria, a decisão e o evento de retirada são "
                "acrescentados na mesma transação. O mandato e toda a prova original permanecem."
            ),
        }
        return preview, {"case": dict(case), "candidate": candidate}

    @staticmethod
    async def _public_effect(
        connection: asyncpg.Connection,
        *,
        mandate_id: str,
        person_id: str,
        identity_review_positive: bool,
    ) -> dict[str, object]:
        remaining = await connection.fetchval(
            """
            SELECT COUNT(*)::int
            FROM mandates AS mandate
            JOIN source_documents AS source ON source.id = mandate.source_document_id
            JOIN LATERAL (
                SELECT review.publishable
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'MANDATE'
                  AND review.entity_id = mandate.id
                  AND review.source_document_id = source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS latest_review ON latest_review.publishable = TRUE
            WHERE mandate.person_id = $1
              AND mandate.id <> $2
              AND source.publisher <> 'MEDIA'
              AND source.kind <> 'NEWS_ARTICLE'
              AND EXISTS (
                  SELECT 1
                  FROM source_archive_attestations AS archive
                  WHERE archive.source_document_id = source.id
                    AND archive.content_sha256 = source.content_sha256
                    AND archive.retrieval_url = source.url
              )
            """,
            person_id,
            mandate_id,
        )
        return {
            "kind": "MANDATE_HIDDEN_HISTORY_PRESERVED",
            "mandate_reference_sha256": _reference_sha256(mandate_id),
            "identity_publication_review_unchanged": identity_review_positive,
            "exact_mandate_public_after_withdrawal": False,
            "remaining_public_mandates_for_person": int(remaining or 0),
            "mandate_row_preserved": True,
            "message": (
                "Este mandato deixa de integrar a consulta ativa; a linha histórica, a fonte, "
                "a versão, a publicação e a identidade permanecem preservadas."
            ),
        }

    @staticmethod
    def _confirm_payload(
        *,
        case_id: str,
        preview: dict[str, object],
        payload: PoliticianMandateWithdrawalRequest,
    ) -> None:
        if case_id != payload.expected_case_id or str(preview["case_id"]) != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        confirmations = (
            (payload.expected_revision, preview["case_revision"], "revisão"),
            (payload.expected_version_id, preview["version_id"], "versão"),
            (payload.expected_version_sha256, preview["version_sha256"], "SHA-256 da versão"),
            (payload.expected_mandate_id, preview["mandate_id"], "mandato"),
            (
                payload.expected_source_sha256,
                cast(dict[str, object], preview["source"])["content_sha256"],
                "SHA-256 da fonte",
            ),
            (payload.expected_period_sha256, preview["source_period_sha256"], "intervalo"),
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
        payload: PoliticianMandateWithdrawalRequest,
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
                    f"politician-mandate-publication:{case_id}",
                )
                _initial_preview, initial_context = await self._inspect_context(
                    connection,
                    case_id=case_id,
                    lock=False,
                )
                initial_candidate = initial_context["candidate"]
                assert isinstance(initial_candidate, dict)
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"parliament-people-publication:{initial_candidate['legislature']}",
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
                assert isinstance(case, dict)
                assert isinstance(candidate, dict)
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
                    VALUES ($1, 'MANDATE', $2,
                            'Retirada documentada de mandato parlamentar da consulta ativa',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'A linha histórica permanece; só a revisão pública mais recente muda.',
                            'A decisão não altera a identidade, outros mandatos, '
                            'a fonte ou a versão.',
                            FALSE, $3, $4, $5)
                    """,
                    review_id,
                    str(preview["mandate_id"]),
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
                    VALUES ($1, 'MANDATE', $2, 'WITHDRAWN', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    audit_id,
                    str(preview["mandate_id"]),
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
                            "source_period_sha256": payload.expected_period_sha256,
                            "withdrawal_proof_sha256": (payload.expected_withdrawal_proof_sha256),
                            "public_effect": preview["public_effect"],
                            "public_effect_sha256": payload.expected_public_effect_sha256,
                            "withdrawal_reason_category": payload.reason_category.value,
                            "mandate_deleted": False,
                            "person_deleted": False,
                            "membership_deleted": False,
                            "party_link_changed": False,
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
                    target_id=str(preview["mandate_id"]),
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
                            'MANDATE', $4, $5, $6, $7, $8, $9)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    str(preview["mandate_id"]),
                    internal_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )

                final = await connection.fetchrow(
                    """
                    SELECT EXISTS (
                               SELECT 1 FROM mandates WHERE id = $1
                           ) AS mandate_preserved,
                           EXISTS (
                               SELECT 1
                               FROM mandates AS mandate
                               JOIN source_documents AS source
                                 ON source.id = mandate.source_document_id
                               JOIN LATERAL (
                                   SELECT review.publishable
                                   FROM data_publication_reviews AS review
                                   WHERE review.entity_type = 'MANDATE'
                                     AND review.entity_id = mandate.id
                                     AND review.source_document_id = source.id
                                   ORDER BY review.reviewed_at DESC, review.id DESC
                                   LIMIT 1
                               ) AS latest_review ON latest_review.publishable = TRUE
                               WHERE mandate.id = $1
                           ) AS still_public
                    """,
                    str(preview["mandate_id"]),
                )
                if final is None or final["mandate_preserved"] is not True:
                    raise EditorialSourceError(
                        "A linha histórica deixou de existir; tudo foi revertido"
                    )
                if final["still_public"] is True:
                    raise EditorialSourceError("O mandato ainda seria público; tudo foi revertido")
                confirmed_effect = await self._public_effect(
                    connection,
                    mandate_id=str(preview["mandate_id"]),
                    person_id=str(case["person_id"]),
                    identity_review_positive=case["person_publishable"] is True,
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
            "mandate_id": payload.expected_mandate_id,
            "reason_category": payload.reason_category.value,
            "mandate_review_id": review_id,
            "audit_event_id": audit_id,
            "editorial_decision_id": decision_id,
            "withdrawal_event_id": event_id,
            "decision_sha256": decision_sha256,
            "event_sha256": event_sha256,
            "withdrawal_proof_sha256": payload.expected_withdrawal_proof_sha256,
            "public_effect": preview["public_effect"],
            "public_effect_sha256": payload.expected_public_effect_sha256,
            "mandates_deleted": 0,
            "people_deleted": 0,
            "memberships_deleted": 0,
            "automatic_withdrawal": False,
            "withdrawal_rule": (
                "A revisão negativa, a auditoria, a decisão e o evento foram acrescentados "
                "numa transação ADMIN com MFA; a linha e a publicação originais permanecem."
            ),
        }
