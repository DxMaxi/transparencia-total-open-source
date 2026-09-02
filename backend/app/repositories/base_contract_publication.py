"""Publicação e retirada específicas de contratos BASE com prova append-only."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import asyncpg

from app.models.editorial import (
    BaseContractPublicationRequest,
    BaseContractWithdrawalRequest,
    EditorialAction,
    EditorialState,
    StaffRole,
    StaffSession,
)
from app.repositories.base_contract_editorial import BaseContractEditorialRepository
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)

_SUBJECT_TYPE = "BASE_CONTRACT_SNAPSHOT"
_TARGET_TYPE = "BASE_PUBLIC_CONTRACT"
_PUBLICATION_SCHEMA_VERSION = "base-contract-publication-v1"
_WITHDRAWAL_SCHEMA_VERSION = "base-contract-withdrawal-v1"


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


def _reference_sha256(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _iso_timestamp(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _database_timestamp(value: object, *, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EditorialSourceError(f"{label} deixou de ter formato ISO-8601")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EditorialSourceError(f"{label} deixou de ter formato ISO-8601") from exc
    aware = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return aware.replace(tzinfo=None)


def _decimal(value: object, *, label: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EditorialSourceError(f"{label} deixou de ter formato decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise EditorialSourceError(f"{label} deixou de ter formato decimal") from exc
    exponent = parsed.as_tuple().exponent
    if not parsed.is_finite() or parsed < 0 or not isinstance(exponent, int) or exponent < -2:
        raise EditorialSourceError(f"{label} deixou de ter um valor permitido")
    return parsed


def _integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EditorialSourceError(f"{label} deixou de ser um número inteiro")
    return value


def _json_object(value: object, *, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise EditorialSourceError(f"{label} deixou de ser JSON válido") from exc
    if not isinstance(decoded, dict):
        raise EditorialSourceError(f"{label} deixou de ser um objeto JSON")
    return cast(dict[str, Any], decoded)


def _public_contract_id(official_contract_id: object) -> str:
    return f"base_contract_{_reference_sha256(official_contract_id)}"


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
            "target_type": _TARGET_TYPE,
            "target_id": target_id,
            "rationale": rationale,
            "actor_id": actor_id,
            "actor_alias": actor_alias,
            "created_at": _iso_timestamp(created_at),
        }
    )


def _public_fields(candidate: Mapping[str, Any]) -> dict[str, object]:
    return {
        "official_contract_id": candidate["official_contract_id"],
        "object": candidate["object"],
        "procedure": candidate["procedure"],
        "cpv_code": candidate["cpv_code"],
        "base_value": candidate["base_value"],
        "contract_value": candidate["contract_value"],
        "currency": candidate["currency"],
        "decision_at": candidate["decision_at"],
        "signed_at": candidate["signed_at"],
        "published_at": candidate["published_at"],
        "execution_days": candidate["execution_days"],
        "direct_official_url": candidate["direct_official_url"],
    }


def _publication_proof_sha256(
    *,
    case: Mapping[str, Any],
    candidate: Mapping[str, Any],
    public_contract_id: str,
) -> str:
    source = candidate["source"]
    archive = candidate["archive"]
    batch = candidate["batch"]
    catalogue = candidate["catalogue"]
    assert isinstance(source, Mapping)
    assert isinstance(archive, Mapping)
    assert isinstance(batch, Mapping)
    assert isinstance(catalogue, Mapping)
    return _sha256_json(
        {
            "schema_version": _PUBLICATION_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case["id"]),
            "version_reference_sha256": _reference_sha256(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "public_contract_reference_sha256": _reference_sha256(public_contract_id),
            "contract_snapshot_reference_sha256": _reference_sha256(
                candidate["contract_snapshot_id"]
            ),
            "official_contract_id_sha256": _reference_sha256(candidate["official_contract_id"]),
            "source_record_sha256": candidate["source_record_sha256"],
            "source_sha256": source["content_sha256"],
            "archive_attestation_sha256": archive["attestation_sha256"],
            "batch_normalised_sha256": batch["normalised_sha256"],
            "catalogue_scope_sha256": catalogue["scope_sha256"],
            "catalogue_resource_sha256": catalogue["metadata_sha256"],
            "public_fields": _public_fields(candidate),
            "coverage_claim": "SPECIFIC_SOURCE_RECORD_ONLY",
            "parties_published": 0,
            "organisations_created": 0,
            "interest_entities_created": 0,
            "match_reviews_created": 0,
            "relationships_created": 0,
            "identity_or_name_matching_used": False,
            "fuzzy_matching_used": False,
            "automatic_publication": False,
        }
    )


class BaseContractPublicationRepository:
    """Publica só o contrato factual; partes e grafo exigem portas independentes."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.candidates = BaseContractEditorialRepository(pool)

    @staticmethod
    def _require_admin(actor: StaffSession, *, action: str) -> None:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError(f"A {action} exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError(f"A {action} exige autenticação multifator")

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
                raise EditorialNotFoundError("Processo editorial BASE não encontrado")
        row = await connection.fetchrow(
            f"""
            SELECT editorial_case.id, editorial_case.kind::text AS kind,
                   editorial_case.subject_type, editorial_case.subject_id,
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
                   withdrawal.id AS withdrawal_event_id
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
            WHERE editorial_case.id = $1
              AND editorial_case.kind = 'PUBLIC_CONTRACT'::"EditorialCaseKind"
              AND editorial_case.subject_type = '{_SUBJECT_TYPE}'
            """,
            case_id,
        )
        if row is None:
            raise EditorialNotFoundError("Processo editorial BASE não encontrado")
        return cast(Mapping[str, Any], row)

    async def _contract(
        self,
        connection: asyncpg.Connection,
        *,
        source_id: str | None = None,
        public_contract_id: str | None = None,
        lock: bool,
    ) -> Mapping[str, Any] | None:
        if (source_id is None) == (public_contract_id is None):
            raise RuntimeError("A consulta pública BASE exige uma referência exata")
        selector = "contract.source_id = $1" if source_id is not None else "contract.id = $1"
        value = source_id if source_id is not None else public_contract_id
        lock_clause = "FOR UPDATE OF contract" if lock else ""
        row = await connection.fetchrow(
            f"""
            SELECT contract.id, contract.source_id, contract.object,
                   contract.procedure::text AS procedure, contract.cpv_code,
                   contract.base_value, contract.contract_value, contract.currency,
                   contract.decision_at, contract.signed_at, contract.published_at,
                   contract.execution_days, contract.source_document_id,
                   contract.verification_status::text AS verification_status,
                   contract.publication_status::text AS publication_status,
                   contract.current_publication_snapshot_id,
                   snapshot.contract_snapshot_id,
                   snapshot.editorial_case_id,
                   snapshot.editorial_version_id,
                   snapshot.source_record_sha256,
                   snapshot.publication_proof_sha256,
                   snapshot.created_by_alias AS snapshot_created_by_alias,
                   snapshot.created_at AS snapshot_created_at,
                   latest_review.id AS public_review_id,
                   latest_review.publishable AS public_review_publishable,
                   latest_review.source_document_id AS public_review_source_document_id,
                   publication_audit.id AS publication_audit_event_id,
                   publication_audit.before_json AS publication_audit_before_json,
                   publication_audit.after_json AS publication_audit_after_json,
                   publication_audit.created_at AS publication_audit_created_at,
                   latest_event.id AS latest_publication_event_id,
                   latest_event.action::text AS latest_publication_action,
                   latest_event.case_id AS latest_publication_case_id,
                   latest_event.version_id AS latest_publication_version_id,
                   latest_event.event_sha256 AS latest_publication_event_sha256,
                   (SELECT COUNT(*)::int FROM public_contract_parties AS party
                    WHERE party.public_contract_id = contract.id) AS party_count,
                   (SELECT COUNT(*)::int FROM contract_match_reviews AS review
                    WHERE review.public_contract_id = contract.id) AS match_review_count,
                   (SELECT COUNT(*)::int FROM interest_relationships AS relationship
                    WHERE relationship.public_contract_id = contract.id) AS relationship_count
            FROM public_contracts AS contract
            LEFT JOIN base_public_contract_publication_snapshots AS snapshot
              ON snapshot.id = contract.current_publication_snapshot_id
            LEFT JOIN LATERAL (
                SELECT review.id, review.publishable, review.source_document_id
                FROM data_publication_reviews AS review
                WHERE review.entity_type = '{_TARGET_TYPE}'
                  AND review.entity_id = contract.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS latest_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT audit.id, audit.before_json, audit.after_json, audit.created_at
                FROM audit_events AS audit
                WHERE audit.entity_type = '{_TARGET_TYPE}'
                  AND audit.entity_id = contract.id
                  AND audit.action IN ('PUBLISHED', 'REPUBLISHED')
                ORDER BY audit.created_at DESC, audit.id DESC
                LIMIT 1
            ) AS publication_audit ON TRUE
            LEFT JOIN LATERAL (
                SELECT event.id, event.action, event.case_id, event.version_id,
                       event.event_sha256, event.created_at
                FROM editorial_publication_events AS event
                WHERE event.target_type = '{_TARGET_TYPE}'
                  AND event.target_id = contract.id
                ORDER BY event.created_at DESC, event.id DESC
                LIMIT 1
            ) AS latest_event ON TRUE
            WHERE {selector}
            {lock_clause}
            """,
            value,
        )
        return cast(Mapping[str, Any], row) if row is not None else None

    async def _candidate_for_case(
        self,
        connection: asyncpg.Connection,
        case: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, object]]:
        normalized = _json_object(case["normalized_json"], label="A versão editorial")
        normalized_candidate = normalized.get("candidate")
        if not isinstance(normalized_candidate, dict):
            raise EditorialSourceError("A versão editorial perdeu o candidato BASE")
        source_record_sha256 = normalized_candidate.get("source_record_sha256")
        if not isinstance(source_record_sha256, str):
            raise EditorialSourceError("A versão editorial perdeu o SHA-256 do registo BASE")
        candidate = await self.candidates.get_exact_candidate(
            contract_snapshot_id=str(case["subject_id"]),
            source_record_sha256=source_record_sha256,
            connection=connection,
        )
        if candidate is None:
            raise EditorialSourceError(
                "O contrato aprovado deixou de coincidir com o snapshot oficial atestado"
            )
        return normalized, candidate

    @staticmethod
    def _common_blockers(
        *,
        case: Mapping[str, Any],
        normalized: Mapping[str, Any],
        candidate: Mapping[str, Any],
    ) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []

        def block(code: str, detail: str) -> None:
            blockers.append({"code": code, "detail": detail})

        if str(case["origin"]) != "INGESTION":
            block("INVALID_CASE_ORIGIN", "O processo não nasceu da ingestão oficial BASE.")
        if str(case["subject_id"]) != str(candidate["contract_snapshot_id"]):
            block("SNAPSHOT_MISMATCH", "O snapshot do processo deixou de coincidir.")
        if str(case["source_document_id"]) != str(candidate["source_document_id"]):
            block("SOURCE_DOCUMENT_MISMATCH", "A fonte do processo deixou de coincidir.")
        if case["archive_id"] is None:
            block("ARCHIVE_MISSING", "O original anual deixou de ter arquivo atestado.")
        if (
            str(case["source_publisher"]) != "BASE_GOV"
            or str(case["source_kind"]) != "OPEN_DATASET"
        ):
            block("SOURCE_NOT_BASE", "A fonte deixou de ser o dataset oficial do Portal BASE.")
        if normalized != self_normalized(candidate):
            block(
                "EDITORIAL_VERSION_DRIFT",
                "A versão aprovada diverge da prova reconstruída no servidor.",
            )
        candidate_blockers = candidate["blocked_reasons"]
        if isinstance(candidate_blockers, list):
            for detail in candidate_blockers:
                block("SOURCE_CANDIDATE_BLOCKED", str(detail))
        else:
            block("SOURCE_CANDIDATE_INVALID", "As limitações do candidato estão inválidas.")
        parties = candidate["parties"]
        if not isinstance(parties, list):
            block("SOURCE_PARTIES_INVALID", "As partes privadas deixaram de ser uma lista.")
        if candidate["protected_identifier_exposed"] is not False:
            block("PROTECTED_IDENTIFIER_EXPOSED", "Foi detetada exposição de identificador.")
        return blockers

    async def inspect_publication(self, *, case_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            preview, _context = await self._inspect_publication_context(
                connection,
                case_id=case_id,
                lock=False,
            )
            return preview

    async def _inspect_publication_context(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, object]]:
        case = await self._case(connection, case_id=case_id, lock=lock)
        normalized, candidate = await self._candidate_for_case(connection, case)
        official_contract_id = str(candidate["official_contract_id"])
        existing = await self._contract(
            connection,
            source_id=official_contract_id,
            lock=lock,
        )
        public_contract_id = (
            str(existing["id"])
            if existing is not None
            else _public_contract_id(official_contract_id)
        )
        blockers = self._common_blockers(
            case=case,
            normalized=normalized,
            candidate=candidate,
        )

        def block(code: str, detail: str) -> None:
            blockers.append({"code": code, "detail": detail})

        if str(case["current_state"]) != EditorialState.APPROVED.value:
            block("CASE_NOT_APPROVED", "O processo tem de estar aprovado em privado.")
        if not (
            str(case["latest_decision_action"] or "") == EditorialAction.APPROVE.value
            and str(case["latest_decision_state"] or "") == EditorialState.APPROVED.value
            and int(case["latest_decision_case_revision"] or -1) == int(case["revision"])
            and str(case["latest_decision_version_id"] or "") == str(case["current_version_id"])
            and case["latest_source_confirmed"] is True
        ):
            block("LATEST_APPROVAL_INVALID", "A decisão atual não prova esta aprovação.")
        if case["publication_event_id"] is not None:
            block("PUBLICATION_ALREADY_RECORDED", "Esta versão já possui uma publicação.")
        if existing is not None:
            if (
                str(existing["publication_status"]) != "WITHDRAWN"
                or str(existing["verification_status"]) != "VERIFIED"
                or str(existing["latest_publication_action"] or "") != "WITHDRAW"
                or existing["current_publication_snapshot_id"] is None
            ):
                block(
                    "OFFICIAL_ID_ALREADY_ACTIVE",
                    "O identificador oficial já possui uma projeção que não está "
                    "validamente retirada.",
                )
            if any(
                int(existing[name] or 0) != 0
                for name in ("party_count", "match_review_count", "relationship_count")
            ):
                block(
                    "DEPENDENT_GRAPH_PRESENT",
                    "A projeção anterior tem partes ou relações e exige retirada coordenada.",
                )

        publication_proof = _publication_proof_sha256(
            case=case,
            candidate=candidate,
            public_contract_id=public_contract_id,
        )
        source = candidate["source"]
        archive = candidate["archive"]
        batch = candidate["batch"]
        catalogue = candidate["catalogue"]
        parties = candidate["parties"]
        assert isinstance(source, Mapping)
        assert isinstance(archive, Mapping)
        assert isinstance(batch, Mapping)
        assert isinstance(catalogue, Mapping)
        assert isinstance(parties, list)
        return (
            {
                "case_id": str(case["id"]),
                "case_state": str(case["current_state"]),
                "revision": int(case["revision"]),
                "version_id": str(case["current_version_id"]),
                "version_sha256": str(case["normalized_sha256"]),
                "contract_snapshot_id": str(candidate["contract_snapshot_id"]),
                "public_contract_id": public_contract_id,
                "official_contract_id": official_contract_id,
                "official_contract_id_sha256": _reference_sha256(official_contract_id),
                "source_record_sha256": str(candidate["source_record_sha256"]),
                "source": {
                    "url": str(source["url"]),
                    "retrieved_at": source["retrieved_at"],
                    "content_sha256": str(source["content_sha256"]),
                    "archive_attestation_sha256": str(archive["attestation_sha256"]),
                },
                "public_fields": _public_fields(candidate),
                "source_party_count": len(parties),
                "protected_identifier_count": _integer(
                    candidate["protected_identifier_count"],
                    label="A contagem de identificadores protegidos",
                ),
                "parties_to_publish": 0,
                "organisations_to_create": 0,
                "interest_entities_to_create": 0,
                "match_reviews_to_create": 0,
                "relationships_to_create": 0,
                "coverage_claim": "SPECIFIC_SOURCE_RECORD_ONLY",
                "batch_normalised_sha256": str(batch["normalised_sha256"]),
                "catalogue_scope_sha256": str(catalogue["scope_sha256"]),
                "publication_proof_sha256": publication_proof,
                "reuses_withdrawn_public_contract": existing is not None,
                "eligible": not blockers,
                "blockers": blockers,
                "publication_rule": (
                    "Só um administrador com MFA pode publicar. A ação conserva uma fotografia "
                    "imutável e publica zero partes, organizações, correspondências ou relações."
                ),
            },
            {
                "case": dict(case),
                "candidate": candidate,
                "existing": dict(existing) if existing is not None else None,
            },
        )

    @staticmethod
    def _confirm_publication(
        *,
        case_id: str,
        preview: Mapping[str, Any],
        payload: BaseContractPublicationRequest,
    ) -> None:
        confirmations = (
            (case_id, payload.expected_case_id, "processo indicado no URL"),
            (preview["case_id"], payload.expected_case_id, "processo"),
            (preview["revision"], payload.expected_revision, "revisão"),
            (preview["version_id"], payload.expected_version_id, "versão"),
            (preview["version_sha256"], payload.expected_version_sha256, "SHA-256 editorial"),
            (
                preview["contract_snapshot_id"],
                payload.expected_contract_snapshot_id,
                "snapshot privado",
            ),
            (
                preview["public_contract_id"],
                payload.expected_public_contract_id,
                "contrato público",
            ),
            (
                preview["official_contract_id_sha256"],
                payload.expected_official_contract_id_sha256,
                "identificador oficial",
            ),
            (
                cast(Mapping[str, Any], preview["source"])["content_sha256"],
                payload.expected_source_sha256,
                "SHA-256 da fonte",
            ),
            (
                preview["source_record_sha256"],
                payload.expected_source_record_sha256,
                "SHA-256 do registo",
            ),
            (
                preview["publication_proof_sha256"],
                payload.expected_publication_proof_sha256,
                "prova de publicação",
            ),
        )
        for actual, expected, label in confirmations:
            if actual != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    async def publish(
        self,
        *,
        case_id: str,
        payload: BaseContractPublicationRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor, action="publicação")
        if case_id != payload.expected_case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base-contract-publication:{case_id}",
                )
                initial = await self._case(connection, case_id=case_id, lock=False)
                normalized = _json_object(initial["normalized_json"], label="A versão editorial")
                normalized_candidate = normalized.get("candidate")
                if not isinstance(normalized_candidate, dict):
                    raise EditorialSourceError("A versão editorial perdeu o candidato BASE")
                official_contract_id = str(normalized_candidate.get("official_contract_id", ""))
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base-public-contract:{official_contract_id}",
                )
                preview, context = await self._inspect_publication_context(
                    connection,
                    case_id=case_id,
                    lock=True,
                )
                self._confirm_publication(case_id=case_id, preview=preview, payload=payload)
                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    raise EditorialSourceError("; ".join(str(item["detail"]) for item in blockers))

                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")
                case = cast(dict[str, Any], context["case"])
                candidate = cast(dict[str, Any], context["candidate"])
                existing = cast(dict[str, Any] | None, context["existing"])
                public_contract_id = str(preview["public_contract_id"])
                public_fields = cast(Mapping[str, Any], preview["public_fields"])
                source_document_id = str(candidate["source_document_id"])
                is_republication = existing is not None

                if not is_republication:
                    await connection.execute(
                        """
                        INSERT INTO public_contracts
                            (id, source_id, object, procedure, cpv_code, base_value,
                             contract_value, currency, decision_at, signed_at,
                             published_at, execution_days, source_document_id,
                             verification_status, publication_status,
                             current_publication_snapshot_id, created_at, updated_at)
                        VALUES ($1, $2, $3, $4::"PublicContractProcedure", $5, $6,
                                $7, $8, $9, $10, $11, $12, $13,
                                'PENDING_REVIEW', 'UNDER_REVIEW', NULL, $14, $14)
                        """,
                        public_contract_id,
                        public_fields["official_contract_id"],
                        public_fields["object"],
                        public_fields["procedure"],
                        public_fields["cpv_code"],
                        _decimal(public_fields["base_value"], label="O valor base"),
                        _decimal(public_fields["contract_value"], label="O valor do contrato"),
                        public_fields["currency"],
                        _database_timestamp(public_fields["decision_at"], label="A decisão"),
                        _database_timestamp(public_fields["signed_at"], label="A assinatura"),
                        _database_timestamp(public_fields["published_at"], label="A publicação"),
                        public_fields["execution_days"],
                        source_document_id,
                        created_at,
                    )

                publication_snapshot_id = _new_id("base_contract_publication")
                await connection.execute(
                    """
                    INSERT INTO base_public_contract_publication_snapshots
                        (id, public_contract_id, contract_snapshot_id,
                         editorial_case_id, editorial_version_id, source_document_id,
                         source_id, object, procedure, cpv_code, base_value,
                         contract_value, currency, decision_at, signed_at, published_at,
                         execution_days, direct_official_url, source_record_sha256,
                         publication_proof_sha256, created_by_alias, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                            $9::"PublicContractProcedure", $10, $11, $12, $13,
                            $14, $15, $16, $17, $18, $19, $20, $21, $22)
                    """,
                    publication_snapshot_id,
                    public_contract_id,
                    preview["contract_snapshot_id"],
                    case_id,
                    preview["version_id"],
                    source_document_id,
                    public_fields["official_contract_id"],
                    public_fields["object"],
                    public_fields["procedure"],
                    public_fields["cpv_code"],
                    _decimal(public_fields["base_value"], label="O valor base"),
                    _decimal(public_fields["contract_value"], label="O valor do contrato"),
                    public_fields["currency"],
                    _database_timestamp(public_fields["decision_at"], label="A decisão"),
                    _database_timestamp(public_fields["signed_at"], label="A assinatura"),
                    _database_timestamp(public_fields["published_at"], label="A publicação"),
                    public_fields["execution_days"],
                    public_fields["direct_official_url"],
                    preview["source_record_sha256"],
                    preview["publication_proof_sha256"],
                    actor.public_alias,
                    created_at,
                )
                await connection.execute(
                    """
                    UPDATE public_contracts
                    SET object = $2, procedure = $3::"PublicContractProcedure",
                        cpv_code = $4, base_value = $5, contract_value = $6,
                        currency = $7, decision_at = $8, signed_at = $9,
                        published_at = $10, execution_days = $11,
                        source_document_id = $12,
                        current_publication_snapshot_id = $13,
                        verification_status = 'VERIFIED',
                        publication_status = 'PUBLISHED', updated_at = $14
                    WHERE id = $1
                    """,
                    public_contract_id,
                    public_fields["object"],
                    public_fields["procedure"],
                    public_fields["cpv_code"],
                    _decimal(public_fields["base_value"], label="O valor base"),
                    _decimal(public_fields["contract_value"], label="O valor do contrato"),
                    public_fields["currency"],
                    _database_timestamp(public_fields["decision_at"], label="A decisão"),
                    _database_timestamp(public_fields["signed_at"], label="A assinatura"),
                    _database_timestamp(public_fields["published_at"], label="A publicação"),
                    public_fields["execution_days"],
                    source_document_id,
                    publication_snapshot_id,
                    created_at,
                )

                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, $2, $3,
                            'Contrato público factual para fiscalização da despesa pública',
                            'PUBLIC_INTEREST', 'PUBLIC_OFFICIAL',
                            'Identificador, campos do contrato, fonte, arquivo e versão '
                            'foram revistos.',
                            'Publica só o contrato; partes, identidades e relações ficam '
                            'excluídas.',
                            TRUE, $4, $5, $6)
                    """,
                    review_id,
                    _TARGET_TYPE,
                    public_contract_id,
                    source_document_id,
                    actor.public_alias,
                    created_at,
                )

                audit_id = _new_id("audit")
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9)
                    """,
                    audit_id,
                    _TARGET_TYPE,
                    public_contract_id,
                    "REPUBLISHED" if is_republication else "PUBLISHED",
                    actor.public_alias,
                    _canonical_json(
                        {
                            "publishable": False,
                            "previous_publication_snapshot_reference_sha256": (
                                _reference_sha256(existing["current_publication_snapshot_id"])
                                if existing is not None
                                else None
                            ),
                        }
                    ),
                    _canonical_json(
                        {
                            "publishable": True,
                            "publication_snapshot_reference_sha256": _reference_sha256(
                                publication_snapshot_id
                            ),
                            "source_sha256": payload.expected_source_sha256,
                            "source_record_sha256": payload.expected_source_record_sha256,
                            "publication_proof_sha256": payload.expected_publication_proof_sha256,
                            "parties_published": 0,
                            "organisations_created": 0,
                            "match_reviews_created": 0,
                            "relationships_created": 0,
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
                    target_id=public_contract_id,
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
                    _TARGET_TYPE,
                    public_contract_id,
                    payload.public_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )
                verified = await connection.fetchrow(
                    """
                    SELECT contract.publication_status::text AS status,
                           contract.verification_status::text AS verification,
                           contract.current_publication_snapshot_id,
                           (SELECT COUNT(*) FROM public_contract_parties party
                            WHERE party.public_contract_id = contract.id) AS parties,
                           (SELECT COUNT(*) FROM contract_match_reviews review
                            WHERE review.public_contract_id = contract.id) AS matches,
                           (SELECT COUNT(*) FROM interest_relationships relation
                            WHERE relation.public_contract_id = contract.id) AS relationships,
                           (SELECT event.action::text
                            FROM editorial_publication_events event
                            WHERE event.target_type = $2 AND event.target_id = contract.id
                            ORDER BY event.created_at DESC, event.id DESC LIMIT 1) AS latest_action
                    FROM public_contracts contract WHERE contract.id = $1
                    """,
                    public_contract_id,
                    _TARGET_TYPE,
                )
                if (
                    verified is None
                    or verified["status"] != "PUBLISHED"
                    or verified["verification"] != "VERIFIED"
                    or str(verified["current_publication_snapshot_id"]) != publication_snapshot_id
                    or int(verified["parties"]) != 0
                    or int(verified["matches"]) != 0
                    or int(verified["relationships"]) != 0
                    or verified["latest_action"] != "PUBLISH"
                ):
                    raise RuntimeError("A verificação final da publicação BASE falhou")
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError(
                "A fotografia, a versão ou o contrato BASE já possui publicação"
            ) from exc
        return {
            "case_id": case_id,
            "state": EditorialState.PUBLISHED.value,
            "revision": next_revision,
            "public_contract_id": public_contract_id,
            "publication_snapshot_id": publication_snapshot_id,
            "publication_proof_sha256": payload.expected_publication_proof_sha256,
            "publication_event_id": event_id,
            "publication_event_sha256": event_sha256,
            "public_review_id": review_id,
            "publication_audit_event_id": audit_id,
            "parties_published": 0,
            "organisations_created": 0,
            "match_reviews_created": 0,
            "relationships_created": 0,
            "republished": is_republication,
        }

    async def inspect_withdrawal(self, *, case_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            preview, _context = await self._inspect_withdrawal_context(
                connection,
                case_id=case_id,
                lock=False,
            )
            return preview

    async def _inspect_withdrawal_context(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, object]]:
        case = await self._case(connection, case_id=case_id, lock=lock)
        normalized, candidate = await self._candidate_for_case(connection, case)
        target_id = str(case["publication_event_target_id"] or "")
        contract = (
            await self._contract(
                connection,
                public_contract_id=target_id,
                lock=lock,
            )
            if target_id
            else None
        )
        blockers = self._common_blockers(
            case=case,
            normalized=normalized,
            candidate=candidate,
        )

        def block(code: str, detail: str) -> None:
            blockers.append({"code": code, "detail": detail})

        if str(case["current_state"]) != EditorialState.PUBLISHED.value:
            block("CASE_NOT_PUBLISHED", "O processo tem de estar atualmente publicado.")
        if not (
            str(case["latest_decision_action"] or "") == EditorialAction.PUBLISH.value
            and str(case["latest_decision_state"] or "") == EditorialState.PUBLISHED.value
            and int(case["latest_decision_case_revision"] or -1) == int(case["revision"])
            and str(case["latest_decision_version_id"] or "") == str(case["current_version_id"])
            and case["latest_source_confirmed"] is True
        ):
            block("LATEST_PUBLICATION_INVALID", "A decisão atual não prova esta publicação.")
        if case["publication_event_id"] is None:
            block("PUBLICATION_EVENT_MISSING", "O evento imutável de publicação está ausente.")
        if str(case["publication_event_target_type"] or "") != _TARGET_TYPE:
            block("PUBLICATION_TARGET_INVALID", "O evento não aponta para um contrato BASE.")
        if case["withdrawal_event_id"] is not None:
            block("WITHDRAWAL_ALREADY_RECORDED", "Esta versão já possui uma retirada.")
        if contract is None:
            block("PUBLIC_CONTRACT_MISSING", "A projeção pública deixou de existir.")
            contract = {}
        else:
            expected_proof = _publication_proof_sha256(
                case=case,
                candidate=candidate,
                public_contract_id=str(contract["id"]),
            )
            if str(contract["publication_status"]) != "PUBLISHED":
                block("CONTRACT_NOT_PUBLISHED", "O contrato já não está publicado.")
            if str(contract["verification_status"]) != "VERIFIED":
                block("CONTRACT_NOT_VERIFIED", "O contrato já não está verificado.")
            if contract["current_publication_snapshot_id"] is None:
                block("PUBLICATION_SNAPSHOT_MISSING", "A fotografia pública está ausente.")
            if str(contract["contract_snapshot_id"] or "") != str(
                candidate["contract_snapshot_id"]
            ):
                block(
                    "PUBLICATION_SNAPSHOT_DRIFT",
                    "A fotografia pública aponta para outro snapshot.",
                )
            if str(contract["editorial_case_id"] or "") != case_id or str(
                contract["editorial_version_id"] or ""
            ) != str(case["current_version_id"]):
                block(
                    "PUBLICATION_EDITORIAL_DRIFT",
                    "A fotografia pública aponta para outra versão.",
                )
            if str(contract["source_record_sha256"] or "") != str(
                candidate["source_record_sha256"]
            ):
                block("SOURCE_RECORD_DRIFT", "A fotografia perdeu o SHA-256 do registo.")
            if str(contract["publication_proof_sha256"] or "") != expected_proof:
                block("PUBLICATION_PROOF_DRIFT", "A prova da publicação deixou de coincidir.")
            if (
                contract["public_review_id"] is None
                or contract["public_review_publishable"] is not True
            ):
                block("PUBLIC_REVIEW_INACTIVE", "A revisão pública positiva já não está ativa.")
            if str(contract["public_review_source_document_id"] or "") != str(
                candidate["source_document_id"]
            ):
                block("PUBLIC_REVIEW_SOURCE_DRIFT", "A revisão pública aponta para outra fonte.")
            if contract["publication_audit_event_id"] is None:
                block("PUBLICATION_AUDIT_MISSING", "A auditoria da publicação está ausente.")
            audit_after = _json_object(
                contract["publication_audit_after_json"] or {},
                label="A auditoria da publicação",
            )
            if audit_after.get("publication_proof_sha256") != expected_proof:
                block("PUBLICATION_AUDIT_DRIFT", "A auditoria não prova esta publicação.")
            if str(contract["latest_publication_action"] or "") != "PUBLISH":
                block("PUBLICATION_NOT_ACTIVE", "O último evento público não é uma publicação.")
            if str(contract["latest_publication_case_id"] or "") != case_id or str(
                contract["latest_publication_version_id"] or ""
            ) != str(case["current_version_id"]):
                block("LATEST_EVENT_DRIFT", "O último evento pertence a outro processo ou versão.")
            if any(
                int(contract[name] or 0) != 0
                for name in ("party_count", "match_review_count", "relationship_count")
            ):
                block(
                    "DEPENDENT_GRAPH_PRESENT",
                    "Existem partes ou relações que exigem uma retirada coordenada própria.",
                )

        publication_created_at = case["publication_event_created_at"]
        rebuilt_event_sha256: str | None = None
        if (
            isinstance(publication_created_at, datetime)
            and case["publication_event_id"] is not None
        ):
            rebuilt_event_sha256 = _publication_event_sha256(
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
            if rebuilt_event_sha256 != str(case["publication_event_sha256"]):
                block("PUBLICATION_EVENT_HASH_DRIFT", "O SHA-256 do evento deixou de coincidir.")
        else:
            block("PUBLICATION_EVENT_INCOMPLETE", "O evento de publicação está incompleto.")

        public_effect = {
            "kind": "DATA_UNAVAILABLE",
            "message": (
                "O contrato deixa a consulta ativa; a fonte, a fotografia publicada, o histórico "
                "e todos os direitos de resposta permanecem preservados."
            ),
            "contract_deleted": False,
            "publication_snapshot_deleted": False,
            "editorial_history_deleted": False,
            "right_of_reply_deleted": False,
            "party_deleted": False,
            "relationship_deleted": False,
        }
        public_effect_sha256 = _sha256_json(public_effect)
        publication_proof = str(contract.get("publication_proof_sha256") or "0" * 64)
        withdrawal_proof_payload = {
            "schema_version": _WITHDRAWAL_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case_id),
            "version_sha256": str(case["normalized_sha256"]),
            "public_contract_reference_sha256": _reference_sha256(target_id),
            "publication_snapshot_reference_sha256": _reference_sha256(
                contract.get("current_publication_snapshot_id") or ""
            ),
            "source_sha256": str(case["source_sha256"]),
            "source_record_sha256": candidate["source_record_sha256"],
            "publication_proof_sha256": publication_proof,
            "public_review_reference_sha256": _reference_sha256(
                contract.get("public_review_id") or ""
            ),
            "publication_audit_reference_sha256": _reference_sha256(
                contract.get("publication_audit_event_id") or ""
            ),
            "publication_event_reference_sha256": _reference_sha256(
                case["publication_event_id"] or ""
            ),
            "publication_event_sha256": rebuilt_event_sha256,
            "public_effect": public_effect,
            "public_effect_sha256": public_effect_sha256,
            "automatic_withdrawal": False,
            "selective_removal_allowed": False,
        }
        withdrawal_proof = _sha256_json(withdrawal_proof_payload) if not blockers else None
        return (
            {
                "case_id": case_id,
                "case_state": str(case["current_state"]),
                "revision": int(case["revision"]),
                "version_id": str(case["current_version_id"]),
                "version_sha256": str(case["normalized_sha256"]),
                "public_contract_id": target_id,
                "publication_snapshot_id": str(
                    contract.get("current_publication_snapshot_id") or ""
                ),
                "source_sha256": str(case["source_sha256"]),
                "source_record_sha256": str(candidate["source_record_sha256"]),
                "publication_proof_sha256": publication_proof,
                "withdrawal_proof_sha256": withdrawal_proof,
                "public_review_id": str(contract.get("public_review_id") or ""),
                "publication_audit_event_id": str(contract.get("publication_audit_event_id") or ""),
                "publication_event_id": str(case["publication_event_id"] or ""),
                "publication_event_sha256": str(case["publication_event_sha256"] or ""),
                "public_effect": public_effect,
                "public_effect_sha256": public_effect_sha256,
                "eligible": not blockers,
                "blockers": blockers,
                "withdrawal_rule": (
                    "Só um administrador com MFA pode retirar. A ação acrescenta revisão, "
                    "auditoria, decisão e evento; nunca apaga o contrato ou o histórico."
                ),
            },
            {"case": dict(case), "candidate": candidate, "contract": dict(contract)},
        )

    @staticmethod
    def _confirm_withdrawal(
        *,
        case_id: str,
        preview: Mapping[str, Any],
        payload: BaseContractWithdrawalRequest,
    ) -> None:
        confirmations = (
            (case_id, payload.expected_case_id, "processo indicado no URL"),
            (preview["case_id"], payload.expected_case_id, "processo"),
            (preview["revision"], payload.expected_revision, "revisão"),
            (preview["version_id"], payload.expected_version_id, "versão"),
            (preview["version_sha256"], payload.expected_version_sha256, "SHA-256 editorial"),
            (
                preview["public_contract_id"],
                payload.expected_public_contract_id,
                "contrato público",
            ),
            (
                preview["publication_snapshot_id"],
                payload.expected_publication_snapshot_id,
                "fotografia pública",
            ),
            (preview["source_sha256"], payload.expected_source_sha256, "SHA-256 da fonte"),
            (
                preview["source_record_sha256"],
                payload.expected_source_record_sha256,
                "SHA-256 do registo",
            ),
            (
                preview["publication_proof_sha256"],
                payload.expected_publication_proof_sha256,
                "prova de publicação",
            ),
            (
                preview["withdrawal_proof_sha256"],
                payload.expected_withdrawal_proof_sha256,
                "prova de retirada",
            ),
            (preview["public_review_id"], payload.expected_public_review_id, "revisão pública"),
            (
                preview["publication_audit_event_id"],
                payload.expected_publication_audit_event_id,
                "auditoria de publicação",
            ),
            (
                preview["publication_event_id"],
                payload.expected_publication_event_id,
                "evento de publicação",
            ),
            (
                preview["publication_event_sha256"],
                payload.expected_publication_event_sha256,
                "SHA-256 do evento",
            ),
            (
                preview["public_effect_sha256"],
                payload.expected_public_effect_sha256,
                "efeito público",
            ),
        )
        for actual, expected, label in confirmations:
            if actual != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    async def withdraw(
        self,
        *,
        case_id: str,
        payload: BaseContractWithdrawalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor, action="retirada")
        if case_id != payload.expected_case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base-contract-publication:{case_id}",
                )
                initial = await self._case(connection, case_id=case_id, lock=False)
                target_id = str(initial["publication_event_target_id"] or "")
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base-public-contract:{target_id}",
                )
                preview, context = await self._inspect_withdrawal_context(
                    connection,
                    case_id=case_id,
                    lock=True,
                )
                self._confirm_withdrawal(case_id=case_id, preview=preview, payload=payload)
                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    details = "; ".join(str(item["detail"]) for item in blockers)
                    if str(preview["case_state"]) != EditorialState.PUBLISHED.value:
                        raise EditorialConflictError(details)
                    raise EditorialSourceError(details)

                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")
                case = cast(dict[str, Any], context["case"])
                public_contract_id = str(preview["public_contract_id"])
                source_document_id = str(case["source_document_id"])

                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, $2, $3,
                            'Retirada documentada de contrato BASE da consulta ativa',
                            'PUBLIC_INTEREST', 'PUBLIC_OFFICIAL',
                            'A fotografia e o histórico permanecem; só a projeção ativa muda.',
                            'Não apaga contrato, fonte, direito de resposta, partes ou relações.',
                            FALSE, $4, $5, $6)
                    """,
                    review_id,
                    _TARGET_TYPE,
                    public_contract_id,
                    source_document_id,
                    actor.public_alias,
                    created_at,
                )
                await connection.execute(
                    """
                    UPDATE public_contracts
                    SET publication_status = 'WITHDRAWN', updated_at = $2
                    WHERE id = $1
                    """,
                    public_contract_id,
                    created_at,
                )

                audit_id = _new_id("audit")
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, $2, $3, 'WITHDRAWN', $4,
                            $5::jsonb, $6::jsonb, $7, $8)
                    """,
                    audit_id,
                    _TARGET_TYPE,
                    public_contract_id,
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
                            "withdrawal_proof_sha256": preview["withdrawal_proof_sha256"],
                            "public_effect": preview["public_effect"],
                            "public_effect_sha256": preview["public_effect_sha256"],
                            "withdrawal_reason_category": payload.reason_category.value,
                            "contract_deleted": False,
                            "publication_snapshot_deleted": False,
                            "editorial_history_deleted": False,
                            "right_of_reply_deleted": False,
                        }
                    ),
                    payload.public_rationale,
                    created_at,
                )

                version_id = str(case["current_version_id"])
                next_revision = int(case["revision"]) + 1
                internal_rationale = f"[{payload.reason_category.value}] {payload.rationale}"
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
                    target_id=public_contract_id,
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
                    VALUES ($1, $2, $3, 'WITHDRAW'::"EditorialPublicationAction",
                            $4, $5, $6, $7, $8, $9, $10)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    _TARGET_TYPE,
                    public_contract_id,
                    payload.public_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )
                final = await connection.fetchrow(
                    """
                    SELECT contract.publication_status::text AS status,
                           contract.current_publication_snapshot_id,
                           EXISTS (SELECT 1 FROM public_contracts preserved
                                   WHERE preserved.id = contract.id) AS contract_preserved,
                           EXISTS (SELECT 1
                                   FROM base_public_contract_publication_snapshots snapshot
                                   WHERE snapshot.id = contract.current_publication_snapshot_id)
                               AS snapshot_preserved,
                           (SELECT event.action::text
                            FROM editorial_publication_events event
                            WHERE event.target_type = $2 AND event.target_id = contract.id
                            ORDER BY event.created_at DESC, event.id DESC LIMIT 1) AS latest_action
                    FROM public_contracts contract WHERE contract.id = $1
                    """,
                    public_contract_id,
                    _TARGET_TYPE,
                )
                if (
                    final is None
                    or final["status"] != "WITHDRAWN"
                    or final["contract_preserved"] is not True
                    or final["snapshot_preserved"] is not True
                    or final["latest_action"] != "WITHDRAW"
                ):
                    raise RuntimeError("A verificação final da retirada BASE falhou")
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A retirada BASE já consta do histórico") from exc
        return {
            "case_id": case_id,
            "state": EditorialState.WITHDRAWN.value,
            "revision": next_revision,
            "public_contract_id": public_contract_id,
            "publication_snapshot_id": preview["publication_snapshot_id"],
            "withdrawal_proof_sha256": payload.expected_withdrawal_proof_sha256,
            "public_effect": preview["public_effect"],
            "public_effect_sha256": payload.expected_public_effect_sha256,
            "withdrawal_event_id": event_id,
            "withdrawal_event_sha256": event_sha256,
            "public_review_id": review_id,
            "withdrawal_audit_event_id": audit_id,
            "contract_deleted": False,
            "publication_snapshot_deleted": False,
            "editorial_history_deleted": False,
            "right_of_reply_deleted": False,
        }


def self_normalized(candidate: Mapping[str, Any]) -> dict[str, object]:
    """Centraliza a reconstrução exata sem confiar no JSON submetido pelo cliente."""

    return BaseContractEditorialRepository._normalized_proposal(candidate)
