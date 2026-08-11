"""Publicação parlamentar V5 específica por âmbito e fail-closed."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialCaseKind,
    EditorialState,
    ParliamentEditorialPublicationRequest,
    ParliamentEditorialScope,
    ParliamentEditorialWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.parliament_publication import (
    ParliamentSnapshotPublicationRepository,
)

_SCOPES = {
    (
        EditorialCaseKind.PARLIAMENT_ACTIVITY.value,
        "PARLIAMENT_ACTIVITY_SNAPSHOT",
    ): ParliamentEditorialScope.ACTIVITY,
    (
        EditorialCaseKind.PARLIAMENT_VOTE.value,
        "PARLIAMENT_VOTES_SNAPSHOT",
    ): ParliamentEditorialScope.VOTES,
}


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


def _digest_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def _iso_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds") + "Z"


def _publication_event_sha256(
    *,
    event_id: str,
    case_id: str,
    version_id: str,
    action: str,
    target_type: str,
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
            "target_type": target_type,
            "target_id": target_id,
            "rationale": rationale,
            "actor_id": actor_id,
            "actor_alias": actor_alias,
            "created_at": _iso_timestamp(created_at),
        }
    )


def _as_json_object(value: object) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _publication_proof(value: dict[str, Any]) -> dict[str, object] | None:
    """Extrai apenas os factos que a projeção pública materializada consegue representar."""

    try:
        snapshot = value["snapshot"]
        source_proof = value["source_proof"]
        manifest_counts = value["manifest_counts"]
        coverage = value["coverage"]
        differences = value["differences_from_previous_snapshot"]
        limitations = value["limitations"]
        publication = value["publication"]
    except KeyError:
        return None
    if not all(
        isinstance(item, dict)
        for item in (snapshot, source_proof, manifest_counts, coverage, differences, publication)
    ) or not isinstance(limitations, list):
        return None
    return {
        "schema_version": value.get("schema_version"),
        "scope": value.get("scope"),
        "legislature": value.get("legislature"),
        "snapshot": snapshot,
        "source_proof": source_proof,
        "manifest_counts": manifest_counts,
        "coverage": coverage,
        "differences_from_previous_snapshot": differences,
        "limitations": limitations,
        "publication": publication,
    }


class ParliamentEditorialPublicationRepository:
    """Liga uma aprovação privada à porta pública V4 numa única transação."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.parliament = ParliamentEditorialRepository(pool)

    async def inspect(self, *, case_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            case = await self._case(connection, case_id=case_id, lock=False)
            scope = self._scope(case)
            candidate = await self.parliament.load_snapshot_candidate_for_publication(
                connection,
                snapshot_id=str(case["subject_id"]),
                lock_snapshot=False,
            )
            return self._preview(case=case, candidate=candidate, scope=scope)

    async def publish(
        self,
        *,
        case_id: str,
        payload: ParliamentEditorialPublicationRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError("Esta publicação exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError("A publicação exige autenticação multifator")

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"editorial-parliament-publication:{case_id}",
                )
                case = await self._case(connection, case_id=case_id, lock=True)
                scope = self._scope(case)
                legislature = case["snapshot_legislature"]
                if legislature is None:
                    raise EditorialSourceError(
                        "A fotografia parlamentar associada ao processo já não existe"
                    )
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"parliament-publication:{legislature}",
                )
                # A porta V4 usa o mesmo bloqueio por legislatura. A releitura impede
                # confirmar uma projeção pública que tenha mudado enquanto aguardávamos.
                case = await self._case(connection, case_id=case_id, lock=True)
                scope = self._scope(case)
                candidate = await self.parliament.load_snapshot_candidate_for_publication(
                    connection,
                    snapshot_id=str(case["subject_id"]),
                    lock_snapshot=True,
                )
                preview = self._preview(case=case, candidate=candidate, scope=scope)
                self._confirm_payload(case=case, preview=preview, payload=payload)

                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    details = "; ".join(str(item["detail"]) for item in blockers)
                    if str(case["current_state"]) != EditorialState.APPROVED.value:
                        raise EditorialConflictError(details)
                    raise EditorialSourceError(details)

                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")
                next_revision = int(case["revision"]) + 1
                version_id = str(case["current_version_id"])
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

                manifest_counts = candidate["manifest_counts"]
                source = candidate["source"]
                assert isinstance(manifest_counts, dict)
                assert isinstance(source, dict)
                before = await self._latest_public_review(
                    connection,
                    entity_type=str(case["subject_type"]),
                    entity_id=str(case["subject_id"]),
                    source_document_id=str(case["source_document_id"]),
                )
                public_decision = (
                    await ParliamentSnapshotPublicationRepository.append_scope_decision(
                        connection,
                        scope=scope.value,
                        snapshot_id=str(case["subject_id"]),
                        source_document_id=str(case["source_document_id"]),
                        legislature=str(candidate["legislature"]),
                        publishable=True,
                        source_sha256=str(source["content_sha256"]),
                        normalised_sha256=str(candidate["normalised_sha256"]),
                        counts={key: int(value) for key, value in manifest_counts.items()},
                        reviewer_alias=actor.public_alias,
                        rationale=payload.rationale,
                        before=before,
                        audit_context={
                            "case_id": case_id,
                            "case_revision": next_revision,
                            "version_id": version_id,
                            "editorial_sha256": str(case["editorial_sha256"]),
                            "publication_proof_sha256": str(preview["publication_proof_sha256"]),
                        },
                    )
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
                    target_type=str(case["subject_type"]),
                    target_id=str(case["subject_id"]),
                    rationale=payload.rationale,
                    actor_id=actor.staff_id,
                    actor_alias=actor.public_alias,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    INSERT INTO editorial_publication_events
                        (id, case_id, version_id, action, target_type, target_id,
                         rationale, actor_id, actor_alias, event_sha256, created_at)
                    VALUES ($1, $2, $3, 'PUBLISH'::"EditorialPublicationAction", $4, $5,
                            $6, $7, $8, $9, $10)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    str(case["subject_type"]),
                    str(case["subject_id"]),
                    payload.rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A publicação já foi acrescentada ao histórico") from exc

        return {
            "created": True,
            "case_id": case_id,
            "state": EditorialState.PUBLISHED.value,
            "revision": next_revision,
            "scope": scope.value,
            "target_type": str(case["subject_type"]),
            "target_id": str(case["subject_id"]),
            "decision_sha256": decision_sha256,
            "event_sha256": event_sha256,
            "publication_review_id": public_decision["publication_review_id"],
            "audit_event_id": public_decision["audit_event_id"],
            "publication_rule": (
                "A revisão pública V4, a decisão PUBLISH e o evento editorial foram "
                "confirmados no mesmo commit transacional."
            ),
        }

    async def inspect_withdrawal(self, *, case_id: str) -> dict[str, object]:
        """Expõe a prova já publicada e simula o efeito sem efetuar escritas."""

        async with self.pool.acquire() as connection:
            case = await self._case(connection, case_id=case_id, lock=False)
            scope = self._scope(case)
            public_effect = await self._public_effect(
                connection,
                case=case,
                scope=scope,
            )
            return self._withdrawal_preview(
                case=case,
                scope=scope,
                public_effect=public_effect,
            )

    async def withdraw(
        self,
        *,
        case_id: str,
        payload: ParliamentEditorialWithdrawalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        """Retira um único âmbito, preservando toda a prova e o efeito público."""

        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError("Esta retirada exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError("A retirada exige autenticação multifator")

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"editorial-parliament-publication:{case_id}",
                )
                case = await self._case(connection, case_id=case_id, lock=True)
                scope = self._scope(case)
                legislature = case["snapshot_legislature"]
                if legislature is None:
                    raise EditorialSourceError(
                        "A fotografia parlamentar associada ao processo já não existe"
                    )
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"parliament-publication:{legislature}",
                )
                case = await self._case(connection, case_id=case_id, lock=True)
                scope = self._scope(case)
                public_effect = await self._public_effect(
                    connection,
                    case=case,
                    scope=scope,
                )
                preview = self._withdrawal_preview(
                    case=case,
                    scope=scope,
                    public_effect=public_effect,
                )
                self._confirm_withdrawal_payload(case=case, preview=preview, payload=payload)

                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    details = "; ".join(str(item["detail"]) for item in blockers)
                    if str(case["current_state"]) != EditorialState.PUBLISHED.value:
                        raise EditorialConflictError(details)
                    raise EditorialSourceError(details)

                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")
                next_revision = int(case["revision"]) + 1
                version_id = str(case["current_version_id"])
                decision_id = _new_id("editorial_decision")
                internal_rationale = f"[{payload.reason_category.value}] {payload.rationale}"
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

                manifest_counts = preview["manifest_counts"]
                assert isinstance(manifest_counts, dict)
                before = await self._latest_public_review(
                    connection,
                    entity_type=str(case["subject_type"]),
                    entity_id=str(case["subject_id"]),
                    source_document_id=str(case["source_document_id"]),
                )
                if (
                    str(before["id"] or "") != str(preview["public_review_id"])
                    or before["publishable"] is not True
                    or before["reviewed_at"] != case["public_reviewed_at"]
                ):
                    raise EditorialConflictError(
                        "A revisão pública mudou durante a confirmação da retirada"
                    )
                public_decision = (
                    await ParliamentSnapshotPublicationRepository.append_scope_decision(
                        connection,
                        scope=scope.value,
                        snapshot_id=str(case["subject_id"]),
                        source_document_id=str(case["source_document_id"]),
                        legislature=str(legislature),
                        publishable=False,
                        source_sha256=str(preview["source_sha256"]),
                        normalised_sha256=str(preview["snapshot_sha256"]),
                        counts={key: int(value) for key, value in manifest_counts.items()},
                        reviewer_alias=actor.public_alias,
                        rationale=payload.public_rationale,
                        before=before,
                        audit_context={
                            "case_id": case_id,
                            "case_revision": next_revision,
                            "version_id": version_id,
                            "editorial_sha256": str(preview["editorial_sha256"]),
                            "publication_proof_sha256": str(preview["publication_proof_sha256"]),
                            "publication_event_id": str(preview["publication_event_id"]),
                            "publication_event_sha256": str(preview["publication_event_sha256"]),
                            "publication_audit_event_id": str(
                                preview["publication_audit_event_id"]
                            ),
                            "withdrawal_reason_category": payload.reason_category.value,
                            "public_effect": public_effect,
                            "public_effect_sha256": str(preview["public_effect_sha256"]),
                        },
                    )
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
                    target_type=str(case["subject_type"]),
                    target_id=str(case["subject_id"]),
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
                    VALUES ($1, $2, $3, 'WITHDRAW'::"EditorialPublicationAction", $4, $5,
                            $6, $7, $8, $9, $10)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    str(case["subject_type"]),
                    str(case["subject_id"]),
                    internal_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A retirada já foi acrescentada ao histórico") from exc

        return {
            "created": True,
            "case_id": case_id,
            "state": EditorialState.WITHDRAWN.value,
            "revision": next_revision,
            "scope": scope.value,
            "target_type": str(case["subject_type"]),
            "target_id": str(case["subject_id"]),
            "reason_category": payload.reason_category.value,
            "decision_sha256": decision_sha256,
            "event_sha256": event_sha256,
            "publication_review_id": public_decision["publication_review_id"],
            "audit_event_id": public_decision["audit_event_id"],
            "public_effect": public_effect,
            "public_effect_sha256": str(preview["public_effect_sha256"]),
            "withdrawal_rule": (
                "A revisão pública negativa, a decisão WITHDRAW e o evento editorial foram "
                "acrescentados no mesmo commit; a publicação e a versão originais permanecem."
            ),
        }

    @staticmethod
    async def _public_effect(
        connection: asyncpg.Connection,
        *,
        case: asyncpg.Record,
        scope: ParliamentEditorialScope,
    ) -> dict[str, object]:
        """Simula a mesma seleção fail-closed usada pela leitura pública após a retirada."""

        row = await connection.fetchrow(
            """
            SELECT snapshot.id, snapshot.normalised_sha256, snapshot.collected_at,
                   source.url AS source_url, source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256,
                   review.reviewed_at AS verified_at
            FROM parliament_activity_snapshots AS snapshot
            JOIN source_documents AS source ON source.id = snapshot.source_document_id
            JOIN LATERAL (
                SELECT candidate.publishable, candidate.reviewed_at
                FROM data_publication_reviews AS candidate
                WHERE candidate.entity_type = $3
                  AND candidate.entity_id = snapshot.id
                  AND candidate.source_document_id = source.id
                ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                LIMIT 1
            ) AS review ON review.publishable = TRUE
            WHERE snapshot.legislature = $1
              AND snapshot.id <> $2
              AND source.publisher = 'PARLIAMENT'
              AND source.url LIKE 'https://%'
              AND source.kind <> 'NEWS_ARTICLE'
              AND EXISTS (
                  SELECT 1
                  FROM source_archive_attestations AS attestation
                  WHERE attestation.source_document_id = source.id
                    AND attestation.content_sha256 = source.content_sha256
                    AND attestation.retrieval_url = source.url
                    AND attestation.retrieved_at = source.retrieved_at
              )
            ORDER BY review.reviewed_at DESC, snapshot.collected_at DESC,
                     snapshot.created_at DESC, snapshot.id DESC
            LIMIT 1
            """,
            str(case["snapshot_legislature"]),
            str(case["subject_id"]),
            str(case["subject_type"]),
        )
        if row is None:
            return {
                "kind": "DATA_UNAVAILABLE",
                "scope": scope.value,
                "legislature": str(case["snapshot_legislature"]),
                "message": (
                    "Depois da retirada não ficará outra fotografia aprovada neste âmbito; "
                    "a interface mostrará dados indisponíveis."
                ),
            }
        verified_at = row["verified_at"]
        collected_at = row["collected_at"]
        source_retrieved_at = row["source_retrieved_at"]
        if not all(
            isinstance(value, datetime)
            for value in (verified_at, collected_at, source_retrieved_at)
        ):
            raise RuntimeError("A fotografia pública alternativa tem datas inválidas")
        return {
            "kind": "FALLBACK_TO_PREVIOUS_SNAPSHOT",
            "scope": scope.value,
            "legislature": str(case["snapshot_legislature"]),
            "snapshot_reference_sha256": hashlib.sha256(str(row["id"]).encode("utf-8")).hexdigest(),
            "snapshot_sha256": str(row["normalised_sha256"]),
            "collected_at": _iso_timestamp(collected_at),
            "source_url": str(row["source_url"]),
            "source_retrieved_at": _iso_timestamp(source_retrieved_at),
            "source_sha256": str(row["source_sha256"]),
            "verified_at": _iso_timestamp(verified_at),
            "message": (
                "Depois da retirada, a leitura pública recuará para esta fotografia anterior "
                "ainda aprovada no mesmo âmbito."
            ),
        }

    @staticmethod
    def _withdrawal_preview(
        *,
        case: asyncpg.Record,
        scope: ParliamentEditorialScope,
        public_effect: dict[str, object],
    ) -> dict[str, object]:
        blockers: list[dict[str, str]] = []

        def block(code: str, detail: str) -> None:
            blockers.append({"code": code, "detail": detail})

        if str(case["current_state"]) != EditorialState.PUBLISHED.value:
            block("CASE_NOT_PUBLISHED", "O processo tem de estar atualmente publicado")
        if str(case["origin"]) != "INGESTION":
            block(
                "INVALID_CASE_ORIGIN",
                "A retirada parlamentar exige um processo criado pelo adaptador de ingestão",
            )
        if case["snapshot_legislature"] is None:
            block("SNAPSHOT_RELATION_MISSING", "A fotografia parlamentar já não existe")
        if case["withdrawal_event_id"] is not None:
            block("WITHDRAWAL_ALREADY_RECORDED", "Esta versão já possui uma retirada imutável")

        stored_data = _as_json_object(case["normalized_json"])
        editorial_sha256 = str(case["editorial_sha256"])
        if stored_data is None or _sha256_json(stored_data) != editorial_sha256:
            block(
                "EDITORIAL_HASH_MISMATCH",
                "O JSON editorial atual não corresponde ao SHA-256 imutável da versão",
            )

        publication_event_id = case["publication_event_id"]
        publication_event_sha256 = _digest_or_none(case["publication_event_sha256"])
        if publication_event_id is None:
            block(
                "PUBLICATION_EVENT_MISSING",
                "A retirada exige o evento imutável da publicação desta versão",
            )
        else:
            created_at = case["publication_event_created_at"]
            if not isinstance(created_at, datetime):
                block("PUBLICATION_EVENT_INVALID", "O evento de publicação tem data inválida")
            else:
                rebuilt_event_sha256 = _publication_event_sha256(
                    event_id=str(publication_event_id),
                    case_id=str(case["id"]),
                    version_id=str(case["publication_event_version_id"]),
                    action="PUBLISH",
                    target_type=str(case["publication_event_target_type"]),
                    target_id=str(case["publication_event_target_id"]),
                    rationale=str(case["publication_event_rationale"]),
                    actor_id=str(case["publication_event_actor_id"]),
                    actor_alias=str(case["publication_event_actor_alias"]),
                    created_at=created_at,
                )
                if rebuilt_event_sha256 != publication_event_sha256:
                    block(
                        "PUBLICATION_EVENT_HASH_MISMATCH",
                        "O evento imutável de publicação já não corresponde ao seu SHA-256",
                    )
            if str(case["publication_event_version_id"]) != str(case["current_version_id"]):
                block(
                    "PUBLICATION_EVENT_VERSION_MISMATCH",
                    "O evento de publicação não pertence à versão editorial atual",
                )
            if str(case["publication_event_target_type"]) != str(case["subject_type"]) or str(
                case["publication_event_target_id"]
            ) != str(case["subject_id"]):
                block(
                    "PUBLICATION_EVENT_TARGET_MISMATCH",
                    "O evento de publicação não corresponde ao alvo exato do processo",
                )

        audit_after = _as_json_object(case["publication_audit_after_json"])
        editorial_link = (
            _as_json_object(audit_after.get("editorial_link")) if audit_after is not None else None
        )
        if case["publication_audit_event_id"] is None or audit_after is None:
            block(
                "PUBLICATION_AUDIT_MISSING",
                "A retirada exige o evento público que comprovou a publicação original",
            )
        elif audit_after.get("publishable") is not True:
            block(
                "PUBLICATION_AUDIT_INVALID",
                "O evento público original não confirma uma decisão publicável",
            )

        source_sha256 = _digest_or_none(
            audit_after.get("source_sha256") if audit_after is not None else None
        )
        snapshot_sha256 = _digest_or_none(
            audit_after.get("normalised_sha256") if audit_after is not None else None
        )
        publication_proof_sha256 = _digest_or_none(
            editorial_link.get("publication_proof_sha256") if editorial_link is not None else None
        )
        if source_sha256 != _digest_or_none(case["source_sha256"]):
            block(
                "PUBLICATION_SOURCE_HASH_MISMATCH",
                "O SHA-256 público original diverge do documento-fonte relacional",
            )
        if snapshot_sha256 != _digest_or_none(case["snapshot_normalised_sha256"]):
            block(
                "PUBLICATION_SNAPSHOT_HASH_MISMATCH",
                "O SHA-256 público original diverge da fotografia relacional",
            )
        if audit_after is not None and (
            audit_after.get("scope") != scope.value
            or audit_after.get("legislature") != case["snapshot_legislature"]
        ):
            block(
                "PUBLICATION_SCOPE_MISMATCH",
                "O evento público original não corresponde ao âmbito e legislatura do processo",
            )
        if editorial_link is None or any(
            (
                editorial_link.get("case_id") != str(case["id"]),
                editorial_link.get("version_id") != str(case["current_version_id"]),
                editorial_link.get("editorial_sha256") != editorial_sha256,
                editorial_link.get("case_revision") != int(case["revision"]),
            )
        ):
            block(
                "PUBLICATION_EDITORIAL_LINK_MISMATCH",
                "A ligação entre o evento público e a versão editorial já não é coerente",
            )
        if publication_proof_sha256 is None:
            block(
                "PUBLICATION_PROOF_MISSING",
                "O evento público original não contém a prova SHA-256 de publicação",
            )

        raw_counts = audit_after.get("counts") if audit_after is not None else None
        manifest_counts = raw_counts if isinstance(raw_counts, dict) else {}
        if set(manifest_counts) != {"sessions", "initiatives", "votes", "vote_records"} or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in manifest_counts.values()
        ):
            block(
                "PUBLICATION_COUNTS_INVALID",
                "O evento público original não preserva as quatro contagens válidas",
            )

        if case["public_review_id"] is None or case["public_publishable"] is not True:
            block(
                "PUBLIC_PROJECTION_NOT_ACTIVE",
                "A projeção pública exata já não está ativa e não pode ser retirada novamente",
            )
        if (
            case["publication_audit_created_at"] is not None
            and case["public_reviewed_at"] != case["publication_audit_created_at"]
        ):
            block(
                "PUBLIC_REVIEW_MISMATCH",
                "A revisão pública atual não é a revisão criada pela publicação editorial",
            )

        return {
            "case_id": str(case["id"]),
            "case_state": str(case["current_state"]),
            "revision": int(case["revision"]),
            "scope": scope.value,
            "scope_label": (
                "atividade parlamentar"
                if scope is ParliamentEditorialScope.ACTIVITY
                else "votações"
            ),
            "target_type": str(case["subject_type"]),
            "target_id": str(case["subject_id"]),
            "legislature": str(case["snapshot_legislature"] or ""),
            "source_sha256": source_sha256 or "0" * 64,
            "snapshot_sha256": snapshot_sha256 or "0" * 64,
            "editorial_sha256": editorial_sha256,
            "publication_proof_sha256": publication_proof_sha256 or "0" * 64,
            "manifest_counts": manifest_counts,
            "public_review_id": str(case["public_review_id"] or ""),
            "public_reviewed_at": case["public_reviewed_at"],
            "publication_audit_event_id": str(case["publication_audit_event_id"] or ""),
            "publication_event_id": str(publication_event_id or ""),
            "publication_event_sha256": publication_event_sha256 or "0" * 64,
            "publication_event_created_at": case["publication_event_created_at"],
            "public_effect": public_effect,
            "public_effect_sha256": _sha256_json(public_effect),
            "eligible": not blockers,
            "blockers": blockers,
            "automatic_withdrawal": False,
            "withdrawal_rule": (
                "Só um administrador com MFA pode retirar o âmbito inteiro por uma categoria "
                "prevista na governação. A versão, a publicação e todos os hashes permanecem."
            ),
        }

    @staticmethod
    def _confirm_withdrawal_payload(
        *,
        case: asyncpg.Record,
        preview: dict[str, object],
        payload: ParliamentEditorialWithdrawalRequest,
    ) -> None:
        if int(case["revision"]) != payload.expected_revision:
            raise EditorialConflictError(
                "O processo foi alterado por outra decisão; atualize antes de continuar"
            )
        confirmations = (
            (payload.confirmed_scope.value, preview["scope"], "âmbito"),
            (payload.expected_snapshot_id, preview["target_id"], "fotografia"),
            (payload.expected_source_sha256, preview["source_sha256"], "SHA-256 da fonte"),
            (
                payload.expected_snapshot_sha256,
                preview["snapshot_sha256"],
                "SHA-256 normalizado da fotografia",
            ),
            (
                payload.expected_editorial_sha256,
                preview["editorial_sha256"],
                "SHA-256 da versão editorial",
            ),
            (
                payload.expected_publication_proof_sha256,
                preview["publication_proof_sha256"],
                "SHA-256 da prova de publicação",
            ),
            (
                payload.expected_public_review_id,
                preview["public_review_id"],
                "revisão pública",
            ),
            (
                payload.expected_publication_audit_event_id,
                preview["publication_audit_event_id"],
                "evento público original",
            ),
            (
                payload.expected_publication_event_id,
                preview["publication_event_id"],
                "evento editorial de publicação",
            ),
            (
                payload.expected_publication_event_sha256,
                preview["publication_event_sha256"],
                "SHA-256 do evento editorial de publicação",
            ),
            (
                payload.expected_public_effect_sha256,
                preview["public_effect_sha256"],
                "efeito público da retirada",
            ),
        )
        for received, expected, label in confirmations:
            if received != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    @staticmethod
    async def _case(
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> asyncpg.Record:
        lock_clause = "FOR UPDATE OF c" if lock else ""
        row = await connection.fetchrow(
            f"""
            SELECT
                c.id, c.kind::text, c.subject_type, c.subject_id,
                c.source_document_id, c.origin::text, c.current_version_id,
                c.current_state::text, c.revision,
                version.normalized_json,
                version.normalized_sha256 AS editorial_sha256,
                source.content_sha256 AS source_sha256,
                snapshot.legislature AS snapshot_legislature,
                snapshot.normalised_sha256 AS snapshot_normalised_sha256,
                public_review.id AS public_review_id,
                public_review.publishable AS public_publishable,
                public_review.reviewed_at AS public_reviewed_at,
                public_review.reviewed_by AS public_reviewed_by,
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
                publication_audit.id AS publication_audit_event_id,
                publication_audit.after_json AS publication_audit_after_json,
                publication_audit.created_at AS publication_audit_created_at
            FROM editorial_cases AS c
            JOIN editorial_versions AS version ON version.id = c.current_version_id
            JOIN source_documents AS source ON source.id = c.source_document_id
            LEFT JOIN parliament_activity_snapshots AS snapshot
              ON snapshot.id = c.subject_id
             AND snapshot.source_document_id = c.source_document_id
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable, review.reviewed_at, review.reviewed_by
                FROM data_publication_reviews AS review
                WHERE review.entity_type = c.subject_type
                  AND review.entity_id = c.subject_id
                  AND review.source_document_id = c.source_document_id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS public_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id, event.version_id, event.target_type,
                       event.target_id, event.rationale, event.actor_id,
                       event.actor_alias, event.event_sha256, event.created_at
                FROM editorial_publication_events AS event
                WHERE event.case_id = c.id
                  AND event.version_id = c.current_version_id
                  AND event.action = 'PUBLISH'::"EditorialPublicationAction"
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS publication ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id
                FROM editorial_publication_events AS event
                WHERE event.case_id = c.id
                  AND event.version_id = c.current_version_id
                  AND event.action = 'WITHDRAW'::"EditorialPublicationAction"
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS withdrawal ON TRUE
            LEFT JOIN LATERAL (
                SELECT audit.id, audit.after_json, audit.created_at
                FROM audit_events AS audit
                WHERE audit.entity_type = c.subject_type
                  AND audit.entity_id = c.subject_id
                  AND audit.action = 'PUBLISHED'
                  AND audit.after_json -> 'editorial_link' ->> 'case_id' = c.id
                  AND audit.after_json -> 'editorial_link' ->> 'version_id'
                      = c.current_version_id
                ORDER BY audit.created_at DESC, audit.id DESC
                LIMIT 1
            ) AS publication_audit ON TRUE
            WHERE c.id = $1
            {lock_clause}
            """,
            case_id,
        )
        if row is None:
            raise EditorialNotFoundError("Processo editorial não encontrado")
        return row

    @staticmethod
    async def _latest_public_review(
        connection: asyncpg.Connection,
        *,
        entity_type: str,
        entity_id: str,
        source_document_id: str,
    ) -> dict[str, object]:
        """Relê o estado V4 depois de obter o bloqueio da fotografia."""

        row = await connection.fetchrow(
            """
            SELECT id, publishable, reviewed_at
            FROM data_publication_reviews
            WHERE entity_type = $1
              AND entity_id = $2
              AND source_document_id = $3
            ORDER BY reviewed_at DESC, id DESC
            LIMIT 1
            """,
            entity_type,
            entity_id,
            source_document_id,
        )
        return {
            "id": row["id"] if row is not None else None,
            "publishable": row["publishable"] if row is not None else None,
            "reviewed_at": row["reviewed_at"] if row is not None else None,
        }

    @staticmethod
    def _scope(case: asyncpg.Record) -> ParliamentEditorialScope:
        scope = _SCOPES.get((str(case["kind"]), str(case["subject_type"])))
        if scope is None:
            raise EditorialConflictError(
                "Este processo não corresponde a um âmbito parlamentar publicável"
            )
        return scope

    @staticmethod
    def _preview(
        *,
        case: asyncpg.Record,
        candidate: dict[str, object],
        scope: ParliamentEditorialScope,
    ) -> dict[str, object]:
        blockers: list[dict[str, str]] = []

        def block(code: str, detail: str) -> None:
            blockers.append({"code": code, "detail": detail})

        if str(case["current_state"]) != EditorialState.APPROVED.value:
            block("CASE_NOT_APPROVED", "O processo tem de estar aprovado e ainda privado")
        if str(case["origin"]) != "INGESTION":
            block(
                "INVALID_CASE_ORIGIN",
                "A publicação parlamentar exige um processo criado pelo adaptador de ingestão",
            )
        if str(candidate["source_document_id"]) != str(case["source_document_id"]):
            block("SOURCE_RELATION_MISMATCH", "A fonte relacional já não corresponde à fotografia")

        editorial_cases = candidate["editorial_cases"]
        assert isinstance(editorial_cases, dict)
        candidate_case = editorial_cases.get(scope.value)
        if not isinstance(candidate_case, dict) or candidate_case.get("id") != str(case["id"]):
            block(
                "CASE_RELATION_MISMATCH",
                "O processo não é a proposta canónica deste âmbito e fotografia",
            )
        if candidate["manifest_matches"] is not True:
            block(
                "MANIFEST_MISMATCH",
                "As contagens materializadas divergem do manifesto imutável",
            )

        manifest_counts = candidate["manifest_counts"]
        coverage = candidate["coverage"]
        assert isinstance(manifest_counts, dict)
        assert isinstance(coverage, dict)
        if scope is ParliamentEditorialScope.ACTIVITY and (
            int(manifest_counts["sessions"]) == 0 or int(manifest_counts["initiatives"]) == 0
        ):
            block(
                "EMPTY_ACTIVITY_COVERAGE",
                "Reuniões e iniciativas não podem ser publicadas com cobertura vazia",
            )
        if scope is ParliamentEditorialScope.VOTES and int(manifest_counts["votes"]) == 0:
            block("EMPTY_VOTE_COVERAGE", "Votações não podem ser publicadas com cobertura vazia")
        if scope is ParliamentEditorialScope.VOTES and int(coverage["inconsistent_actor_links"]):
            block(
                "INCONSISTENT_ACTOR_LINKS",
                "Existem ligações de atores incompatíveis com o tipo registado",
            )

        stored_data = _as_json_object(case["normalized_json"])
        stored_integrity_sha256 = _sha256_json(stored_data) if stored_data is not None else None
        if stored_integrity_sha256 != str(case["editorial_sha256"]):
            block(
                "EDITORIAL_HASH_MISMATCH",
                "O JSON editorial atual não corresponde ao SHA-256 imutável da versão",
            )

        rebuilt = ParliamentEditorialRepository.normalized_proposal_for_publication(
            candidate,
            scope,
        )
        stored_proof = _publication_proof(stored_data) if stored_data is not None else None
        rebuilt_proof = _publication_proof(rebuilt)
        assert rebuilt_proof is not None
        publication_proof_sha256 = _sha256_json(rebuilt_proof)
        if stored_proof is None or _sha256_json(stored_proof) != publication_proof_sha256:
            block(
                "PUBLICATION_PROOF_MISMATCH",
                "A prova factual da versão editorial diverge da fotografia reconstruída",
            )
        if case["publication_event_id"] is not None:
            block(
                "PUBLICATION_ALREADY_RECORDED",
                "Este processo já possui um evento imutável de publicação",
            )

        source = candidate["source"]
        archive = candidate["archive"]
        assert isinstance(source, dict)
        assert isinstance(archive, dict)
        return {
            "case_id": str(case["id"]),
            "case_state": str(case["current_state"]),
            "revision": int(case["revision"]),
            "scope": scope.value,
            "scope_label": (
                "atividade parlamentar"
                if scope is ParliamentEditorialScope.ACTIVITY
                else "votações"
            ),
            "target_type": str(case["subject_type"]),
            "target_id": str(case["subject_id"]),
            "legislature": str(candidate["legislature"]),
            "snapshot_sha256": str(candidate["normalised_sha256"]),
            "parser_version": str(candidate["parser_version"]),
            "collected_at": candidate["collected_at"],
            "source": source,
            "archive": archive,
            "manifest_counts": manifest_counts,
            "materialised_counts": candidate["materialised_counts"],
            "coverage": coverage,
            "editorial_version": {
                "id": str(case["current_version_id"]),
                "normalized_sha256": str(case["editorial_sha256"]),
                "integrity_matches": stored_integrity_sha256 == str(case["editorial_sha256"]),
                "proof_matches_snapshot": (
                    stored_proof is not None
                    and _sha256_json(stored_proof) == publication_proof_sha256
                ),
            },
            "publication_proof_sha256": publication_proof_sha256,
            "public_projection": {
                "publishable": case["public_publishable"],
                "reviewed_at": case["public_reviewed_at"],
                "reviewed_by": case["public_reviewed_by"],
            },
            "existing_publication_event": (
                {
                    "id": str(case["publication_event_id"]),
                    "version_id": str(case["publication_event_version_id"]),
                    "target_type": str(case["publication_event_target_type"]),
                    "target_id": str(case["publication_event_target_id"]),
                    "event_sha256": str(case["publication_event_sha256"]),
                    "created_at": case["publication_event_created_at"],
                }
                if case["publication_event_id"] is not None
                else None
            ),
            "eligible": not blockers,
            "blockers": blockers,
            "automatic_publication": False,
            "publication_rule": (
                "O servidor deriva o âmbito do processo, volta a validar fonte, arquivo, hashes, "
                "manifesto e ligações de atores, e só então confirma todas as provas no mesmo "
                "commit."
            ),
        }

    @staticmethod
    def _confirm_payload(
        *,
        case: asyncpg.Record,
        preview: dict[str, object],
        payload: ParliamentEditorialPublicationRequest,
    ) -> None:
        if int(case["revision"]) != payload.expected_revision:
            raise EditorialConflictError(
                "O processo foi alterado por outra decisão; atualize antes de continuar"
            )
        confirmations = (
            (payload.confirmed_scope.value, preview["scope"], "âmbito"),
            (payload.expected_snapshot_id, preview["target_id"], "fotografia"),
            (
                payload.expected_source_sha256,
                preview["source"]["content_sha256"],  # type: ignore[index]
                "SHA-256 da fonte",
            ),
            (
                payload.expected_snapshot_sha256,
                preview["snapshot_sha256"],
                "SHA-256 normalizado da fotografia",
            ),
            (
                payload.expected_editorial_sha256,
                preview["editorial_version"]["normalized_sha256"],  # type: ignore[index]
                "SHA-256 da versão editorial",
            ),
            (
                payload.expected_publication_proof_sha256,
                preview["publication_proof_sha256"],
                "SHA-256 da prova de publicação",
            ),
        )
        for received, expected, label in confirmations:
            if received != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")
