"""Porta EPT específica: avaliação jurídica, identidade exata e histórico público."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import asyncpg

from app.core.config import Settings
from app.core.security import (
    hmac_private_reference_identifier,
    is_individual_ept_source_url,
)
from app.models.editorial import EditorialAction, EditorialState, StaffRole, StaffSession
from app.models.ept_declaration import (
    EptExactIdentityLinkRequest,
    EptLegalAssessmentRecordRequest,
    EptPublicInterestPublicationRequest,
    EptPublicInterestWithdrawalRequest,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)

_SUBJECT_TYPE = "EPT_PUBLIC_INTEREST_OBSERVATION"
_TARGET_TYPE = "EPT_PUBLIC_INTEREST_DECLARATION"
_PROPOSAL_SCHEMA_VERSION = "ept-public-interest-editorial-v1"
_PUBLICATION_SCHEMA_VERSION = "ept-public-interest-publication-v1"
_WITHDRAWAL_SCHEMA_VERSION = "ept-public-interest-withdrawal-v1"
_LEGAL_SCOPE = "PUBLIC_INTEREST_METADATA_ONLY"
_LEGAL_PERMISSION = "PERMITS_PUBLIC_INTEREST_METADATA_ONLY"


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


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _database_timestamp(value: datetime) -> datetime:
    return _aware(value).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_object(value: object) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    return cast(dict[str, Any], value)


def _declaration_id(case_id: str) -> str:
    return f"ept_declaration_{_reference_sha256(case_id)}"


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
            "created_at": f"{created_at.isoformat(timespec='milliseconds')}Z",
        }
    )


def _block(blockers: list[dict[str, str]], code: str, detail: str) -> None:
    blockers.append({"code": code, "detail": detail})


class EptDeclarationPublicationGateRepository:
    """Exige provas separadas e nunca produz a avaliação jurídica que verifica."""

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self.pool = pool
        self.settings = settings
        self.editorial = EditorialRepository(pool)

    @staticmethod
    def _require_admin(actor: StaffSession) -> None:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError("Esta ação EPT exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError("Esta ação EPT exige autenticação multifator")

    async def _load_core(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> dict[str, Any]:
        if lock:
            locked = await connection.fetchval(
                "SELECT id FROM editorial_cases WHERE id = $1 FOR UPDATE",
                case_id,
            )
            if locked is None:
                raise EditorialNotFoundError("Processo editorial EPT não encontrado")
        row = await connection.fetchrow(
            """
            SELECT editorial_case.id AS case_id,
                   editorial_case.kind::text AS case_kind,
                   editorial_case.subject_type,
                   editorial_case.subject_id,
                   editorial_case.source_document_id,
                   editorial_case.current_state::text AS case_state,
                   editorial_case.revision AS case_revision,
                   editorial_case.current_version_id AS version_id,
                   version.normalized_json,
                   version.normalized_sha256 AS version_sha256,
                   observation.id AS observation_id,
                   observation.official_declaration_id,
                   observation.public_subject_name,
                   observation.declaration_type,
                   observation.declared_at,
                   observation.period_label,
                   observation.public_access_scope,
                   observation.legal_review_status,
                   observation.identity_link_status,
                   observation.source_record_sha256,
                   observation.official_subject_digest,
                   source.id AS source_id,
                   source.publisher::text AS source_publisher,
                   source.kind::text AS source_kind,
                   source.official_identifier AS source_official_identifier,
                   source.url AS source_url,
                   source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256,
                   archive.id AS archive_id,
                   archive.attestation_sha256 AS archive_attestation_sha256,
                   (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3) AS database_now
            FROM editorial_cases AS editorial_case
            JOIN editorial_versions AS version
              ON version.id = editorial_case.current_version_id
            JOIN ept_public_interest_observations AS observation
              ON observation.id = editorial_case.subject_id
             AND observation.source_document_id = editorial_case.source_document_id
            JOIN source_documents AS source
              ON source.id = observation.source_document_id
            LEFT JOIN LATERAL (
                SELECT candidate.id, candidate.attestation_sha256
                FROM source_archive_attestations AS candidate
                WHERE candidate.source_document_id = source.id
                  AND candidate.content_sha256 = source.content_sha256
                  AND candidate.retrieval_url = source.url
                  AND candidate.retrieved_at = source.retrieved_at
                ORDER BY candidate.archived_at ASC, candidate.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            WHERE editorial_case.id = $1
            """,
            case_id,
        )
        if row is None:
            raise EditorialNotFoundError("Processo editorial EPT não encontrado")
        return dict(row)

    @staticmethod
    def _core_blockers(core: Mapping[str, Any]) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []
        normalized = _json_object(core["normalized_json"])
        if core["case_kind"] != "POLITICIAN_PROFILE" or core["subject_type"] != _SUBJECT_TYPE:
            _block(blockers, "CASE_KIND_INVALID", "O processo não pertence ao circuito EPT.")
        if core["subject_id"] != core["observation_id"]:
            _block(blockers, "OBSERVATION_MISMATCH", "A observação deixou de coincidir.")
        if normalized is None or normalized.get("schema_version") != _PROPOSAL_SCHEMA_VERSION:
            _block(blockers, "PROPOSAL_SCHEMA_INVALID", "A versão editorial é incompatível.")
        elif _sha256_json(normalized) != str(core["version_sha256"]):
            _block(blockers, "VERSION_HASH_MISMATCH", "O SHA-256 editorial deixou de coincidir.")
        else:
            candidate = _json_object(normalized.get("candidate"))
            source_proof = _json_object(normalized.get("source_proof"))
            legal_scope = _json_object(normalized.get("legal_scope"))
            identity = _json_object(normalized.get("identity"))
            publication = _json_object(normalized.get("publication"))
            if any(
                item is None
                for item in (candidate, source_proof, legal_scope, identity, publication)
            ):
                _block(blockers, "PROPOSAL_CONTRACT_INVALID", "A proposta está incompleta.")
            else:
                assert candidate is not None
                assert source_proof is not None
                assert legal_scope is not None
                assert identity is not None
                assert publication is not None
                expected_candidate = {
                    "official_declaration_id": core["official_declaration_id"],
                    "source_record_sha256": core["source_record_sha256"],
                    "declaration_type": "INTEREST_REGISTER",
                }
                if any(candidate.get(key) != value for key, value in expected_candidate.items()):
                    _block(
                        blockers,
                        "OBSERVATION_PROOF_MISMATCH",
                        "A proposta e a observação divergem.",
                    )
                if (
                    source_proof.get("content_sha256") != core["source_sha256"]
                    or source_proof.get("official_identifier") != core["source_official_identifier"]
                    or source_proof.get("url") != core["source_url"]
                ):
                    _block(blockers, "SOURCE_PROOF_MISMATCH", "A prova oficial foi alterada.")
                if (
                    legal_scope.get("scope") != "PUBLIC_INTEREST_REGISTER_ONLY"
                    or legal_scope.get("legal_control_is_not_automated") is not True
                ):
                    _block(blockers, "LEGAL_SCOPE_INVALID", "O âmbito jurídico não está fechado.")
                if (
                    identity.get("status") != "UNLINKED_PRIVATE"
                    or identity.get("name_matching_allowed") is not False
                    or identity.get("fuzzy_matching_allowed") is not False
                ):
                    _block(
                        blockers,
                        "IDENTITY_CONTRACT_INVALID",
                        "O contrato de identidade é inseguro.",
                    )
                if publication.get("public_projection_allowed") is not False:
                    _block(
                        blockers,
                        "GENERIC_PUBLICATION_ENABLED",
                        "A proposta permitiu publicação genérica.",
                    )
        source_url = str(core["source_url"])
        if (
            core["source_publisher"] != "TRANSPARENCY_ENTITY"
            or core["source_kind"] != "DECLARATION"
            or core["source_official_identifier"] != core["official_declaration_id"]
            or not is_individual_ept_source_url(source_url)
        ):
            _block(blockers, "SOURCE_INVALID", "A fonte EPT individual já não é válida.")
        if core["archive_id"] is None:
            _block(blockers, "ARCHIVE_MISSING", "O original EPT não tem arquivo atestado.")
        if (
            core["declaration_type"] != "INTEREST_REGISTER"
            or core["public_access_scope"] != "PUBLIC_INTEREST_REGISTER"
            or core["legal_review_status"] != "REQUIRES_INDEPENDENT_LEGAL_REVIEW"
            or core["identity_link_status"] != "UNLINKED_PRIVATE"
        ):
            _block(blockers, "OBSERVATION_SCOPE_INVALID", "A observação saiu do âmbito permitido.")
        return blockers

    @staticmethod
    def _confirm_base(
        *,
        case_id: str,
        core: Mapping[str, Any],
        expected_case_id: str,
        expected_revision: int,
        expected_version_id: str,
        expected_version_sha256: str,
        expected_observation_id: str,
        expected_source_sha256: str,
        expected_source_record_sha256: str,
    ) -> None:
        checks = (
            (case_id, expected_case_id, "processo"),
            (int(core["case_revision"]), expected_revision, "revisão"),
            (str(core["version_id"]), expected_version_id, "versão"),
            (str(core["version_sha256"]), expected_version_sha256, "SHA-256 editorial"),
            (str(core["observation_id"]), expected_observation_id, "observação"),
            (str(core["source_sha256"]), expected_source_sha256, "SHA-256 da fonte"),
            (
                str(core["source_record_sha256"]),
                expected_source_record_sha256,
                "SHA-256 da observação",
            ),
        )
        for actual, expected, label in checks:
            if actual != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    async def inspect_gate(self, *, case_id: str) -> dict[str, object]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            core = await self._load_core(connection, case_id=case_id, lock=False)
            legal = await self._load_legal_assessment(connection, case_id=case_id)
            identity = await self._load_identity_link(connection, case_id=case_id)
            blockers = self._core_blockers(core)
            return self._gate_view(core=core, legal=legal, identity=identity, blockers=blockers)

    @staticmethod
    def _gate_view(
        *,
        core: Mapping[str, Any],
        legal: Mapping[str, Any] | None,
        identity: Mapping[str, Any] | None,
        blockers: list[dict[str, str]],
    ) -> dict[str, object]:
        return {
            "case_id": str(core["case_id"]),
            "case_state": str(core["case_state"]),
            "case_revision": int(core["case_revision"]),
            "version_id": str(core["version_id"]),
            "version_sha256": str(core["version_sha256"]),
            "observation_id": str(core["observation_id"]),
            "source_record_sha256": str(core["source_record_sha256"]),
            "source": {
                "url": str(core["source_url"]),
                "retrieved_at": _iso(core["source_retrieved_at"]),
                "content_sha256": str(core["source_sha256"]),
                "archive_attestation_sha256": core["archive_attestation_sha256"],
            },
            "legal_assessment": (
                {
                    "id": str(legal["id"]),
                    "outcome": str(legal["outcome"]),
                    "document_sha256": str(legal["assessment_document_sha256"]),
                    "assessed_at": _iso(legal["assessed_at"]),
                    "valid_until": _iso(legal["valid_until"]),
                    "assessment_proof_sha256": _legal_assessment_proof(legal),
                    "document_private_and_encrypted": True,
                    "system_issued_legal_opinion": False,
                }
                if legal is not None
                else None
            ),
            "identity_link": (
                {
                    "id": str(identity["id"]),
                    "person_id": str(identity["person_id"]),
                    "person_source_id": str(identity["person_source_id"]),
                    "evidence_document_id": str(identity["evidence_document_id"]),
                    "evidence_sha256": str(identity["evidence_sha256"]),
                    "link_proof_sha256": str(identity["link_proof_sha256"]),
                    "name_matching_used": False,
                    "fuzzy_matching_used": False,
                    "raw_identifier_persisted": False,
                }
                if identity is not None
                else None
            ),
            "blockers": blockers,
            "publication_performed": False,
            "legal_notice": (
                "O sistema verifica a existência e a integridade do registo documental; "
                "não emite nem substitui um parecer jurídico independente."
            ),
        }

    async def record_legal_assessment(
        self,
        *,
        case_id: str,
        payload: EptLegalAssessmentRecordRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor)
        if payload.expected_case_id != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"ept-publication:{case_id}",
                )
                core = await self._load_core(connection, case_id=case_id, lock=True)
                self._confirm_base(
                    case_id=case_id,
                    core=core,
                    expected_case_id=payload.expected_case_id,
                    expected_revision=payload.expected_revision,
                    expected_version_id=payload.expected_version_id,
                    expected_version_sha256=payload.expected_version_sha256,
                    expected_observation_id=payload.expected_observation_id,
                    expected_source_sha256=payload.expected_source_sha256,
                    expected_source_record_sha256=payload.expected_source_record_sha256,
                )
                if core["case_state"] != EditorialState.APPROVED.value:
                    raise EditorialConflictError(
                        "A avaliação só pode ser registada num processo aprovado"
                    )
                if _database_timestamp(payload.assessed_at) > (
                    core["database_now"] + timedelta(minutes=5)
                ):
                    raise EditorialSourceError("A avaliação jurídica não pode ter uma data futura")
                blockers = self._core_blockers(core)
                if blockers:
                    raise EditorialSourceError("; ".join(item["detail"] for item in blockers))
                assessment_id = (
                    f"ept_legal_{_sha256_json([case_id, payload.assessment_document_sha256])}"
                )
                existing = await connection.fetchrow(
                    """
                    SELECT * FROM ept_independent_legal_assessments
                    WHERE case_id = $1 AND assessment_document_sha256 = $2
                    """,
                    case_id,
                    payload.assessment_document_sha256,
                )
                created = existing is None
                if created:
                    await connection.execute(
                        """
                        INSERT INTO ept_independent_legal_assessments
                            (id, observation_id, case_id, assessment_scope, outcome,
                             assessment_document_sha256,
                             assessment_document_storage_backend,
                             assessment_document_storage_key,
                             assessment_document_byte_size,
                             assessment_document_mime_type,
                             assessor_reference_sha256,
                             qualification_evidence_sha256, conflict_check_sha256,
                             assessed_at, valid_until, recorded_by_id,
                             recorded_by_alias, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                                $11, $12, $13, $14, $15, $16, $17, NOW())
                        """,
                        assessment_id,
                        str(core["observation_id"]),
                        case_id,
                        _LEGAL_SCOPE,
                        payload.outcome.value,
                        payload.assessment_document_sha256,
                        payload.assessment_document_storage_backend,
                        payload.assessment_document_storage_key.get_secret_value(),
                        payload.assessment_document_byte_size,
                        payload.assessment_document_mime_type,
                        payload.assessor_reference_sha256,
                        payload.qualification_evidence_sha256,
                        payload.conflict_check_sha256,
                        _database_timestamp(payload.assessed_at),
                        _database_timestamp(payload.valid_until) if payload.valid_until else None,
                        actor.staff_id,
                        actor.public_alias,
                    )
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'EPT_LEGAL_ASSESSMENT', $2, 'RECORDED_PRIVATE', $3,
                                NULL, $4::jsonb, $5, NOW())
                        """,
                        _new_id("audit"),
                        assessment_id,
                        actor.public_alias,
                        _canonical_json(
                            {
                                "case_reference_sha256": _reference_sha256(case_id),
                                "observation_reference_sha256": _reference_sha256(
                                    core["observation_id"]
                                ),
                                "scope": _LEGAL_SCOPE,
                                "outcome": payload.outcome.value,
                                "document_sha256": payload.assessment_document_sha256,
                                "assessor_reference_sha256": _reference_sha256(
                                    payload.assessor_reference_sha256
                                ),
                                "qualification_evidence_sha256": (
                                    payload.qualification_evidence_sha256
                                ),
                                "conflict_check_sha256": payload.conflict_check_sha256,
                                "document_private_and_encrypted": True,
                                "system_issued_legal_opinion": False,
                            }
                        ),
                        payload.recording_rationale,
                    )
                legal = await self._load_legal_assessment(connection, case_id=case_id)
                assert legal is not None
                return {
                    "created": created,
                    "assessment": self._gate_view(
                        core=core,
                        legal=legal,
                        identity=None,
                        blockers=[],
                    )["legal_assessment"],
                    "publication_performed": False,
                }
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A avaliação jurídica já está registada") from exc

    async def record_identity_link(
        self,
        *,
        case_id: str,
        payload: EptExactIdentityLinkRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor)
        if payload.expected_case_id != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        pepper = self.settings.protected_identifier_pepper
        if pepper is None:
            raise EditorialSourceError(
                "PROTECTED_IDENTIFIER_PEPPER não configurado; a identidade não pode ser ligada"
            )
        subject_digest = hmac_private_reference_identifier(
            payload.official_subject_identifier.get_secret_value(),
            pepper.get_secret_value(),
        )
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"ept-publication:{case_id}",
                )
                core = await self._load_core(connection, case_id=case_id, lock=True)
                self._confirm_base(
                    case_id=case_id,
                    core=core,
                    expected_case_id=payload.expected_case_id,
                    expected_revision=payload.expected_revision,
                    expected_version_id=payload.expected_version_id,
                    expected_version_sha256=payload.expected_version_sha256,
                    expected_observation_id=payload.expected_observation_id,
                    expected_source_sha256=payload.expected_source_sha256,
                    expected_source_record_sha256=payload.expected_source_record_sha256,
                )
                if core["case_state"] != EditorialState.APPROVED.value:
                    raise EditorialConflictError(
                        "A identidade só pode ser ligada num processo aprovado"
                    )
                blockers = self._core_blockers(core)
                if blockers:
                    raise EditorialSourceError("; ".join(item["detail"] for item in blockers))
                if not secrets.compare_digest(subject_digest, str(core["official_subject_digest"])):
                    raise EditorialSourceError(
                        "O identificador oficial não coincide com o HMAC da observação EPT"
                    )
                evidence = await connection.fetchrow(
                    """
                    SELECT person.id AS person_id, person.source_id AS person_source_id,
                           person.active AS person_active,
                           evidence.id AS evidence_document_id,
                           evidence.publisher::text AS evidence_publisher,
                           evidence.kind::text AS evidence_kind,
                           evidence.official_identifier AS evidence_official_identifier,
                           evidence.url AS evidence_url,
                           evidence.content_sha256 AS evidence_sha256,
                           archive.id AS archive_id,
                           person_review.publishable AS person_publishable
                    FROM people AS person
                    JOIN source_documents AS evidence ON evidence.id = $3
                    LEFT JOIN LATERAL (
                        SELECT candidate.id
                        FROM source_archive_attestations AS candidate
                        WHERE candidate.source_document_id = evidence.id
                          AND candidate.content_sha256 = evidence.content_sha256
                          AND candidate.retrieval_url = evidence.url
                          AND candidate.retrieved_at = evidence.retrieved_at
                        ORDER BY candidate.archived_at ASC, candidate.id ASC
                        LIMIT 1
                    ) AS archive ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT candidate.publishable
                        FROM data_publication_reviews AS candidate
                        WHERE candidate.entity_type = 'PERSON'
                          AND candidate.entity_id = person.id
                          AND candidate.source_document_id = evidence.id
                        ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                        LIMIT 1
                    ) AS person_review ON TRUE
                    WHERE person.id = $1 AND person.source_id = $2
                    """,
                    payload.person_id,
                    payload.expected_person_source_id,
                    payload.identity_evidence_document_id,
                )
                if evidence is None:
                    raise EditorialSourceError("A pessoa ou a fonte de identidade exata não existe")
                if (
                    evidence["person_active"] is not True
                    or evidence["person_publishable"] is not True
                    or evidence["evidence_document_id"] == core["source_id"]
                    or evidence["evidence_sha256"] != payload.expected_identity_evidence_sha256
                    or evidence["evidence_official_identifier"] != payload.expected_person_source_id
                    or evidence["archive_id"] is None
                    or evidence["evidence_publisher"] == "MEDIA"
                    or evidence["evidence_kind"] == "NEWS_ARTICLE"
                    or not str(evidence["evidence_url"]).startswith("https://")
                ):
                    raise EditorialSourceError(
                        "A segunda fonte oficial ou a revisão pública da pessoa é insuficiente"
                    )
                link_proof_sha256 = _identity_link_proof(
                    case_id=case_id,
                    observation_id=str(core["observation_id"]),
                    subject_digest=subject_digest,
                    person_id=payload.person_id,
                    person_source_id=payload.expected_person_source_id,
                    evidence_document_id=payload.identity_evidence_document_id,
                    evidence_sha256=payload.expected_identity_evidence_sha256,
                )
                link_id = f"ept_identity_{link_proof_sha256}"
                existing = await connection.fetchrow(
                    "SELECT * FROM ept_exact_identity_links WHERE case_id = $1",
                    case_id,
                )
                created = existing is None
                if existing is not None and str(existing["link_proof_sha256"]) != link_proof_sha256:
                    raise EditorialConflictError(
                        "Já existe uma ligação diferente; não é permitido "
                        "substituí-la silenciosamente"
                    )
                if created:
                    await connection.execute(
                        """
                        INSERT INTO ept_exact_identity_links
                            (id, observation_id, case_id, person_id,
                             evidence_document_id, official_subject_digest,
                             person_source_id, evidence_sha256, link_proof_sha256,
                             recorded_by_id, recorded_by_alias, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                        """,
                        link_id,
                        str(core["observation_id"]),
                        case_id,
                        payload.person_id,
                        payload.identity_evidence_document_id,
                        subject_digest,
                        payload.expected_person_source_id,
                        payload.expected_identity_evidence_sha256,
                        link_proof_sha256,
                        actor.staff_id,
                        actor.public_alias,
                    )
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'EPT_EXACT_IDENTITY_LINK', $2, 'LINKED_PRIVATE', $3,
                                NULL, $4::jsonb, $5, NOW())
                        """,
                        _new_id("audit"),
                        link_id,
                        actor.public_alias,
                        _canonical_json(
                            {
                                "case_reference_sha256": _reference_sha256(case_id),
                                "observation_reference_sha256": _reference_sha256(
                                    core["observation_id"]
                                ),
                                "person_reference_sha256": _reference_sha256(payload.person_id),
                                "person_source_id_reference_sha256": _reference_sha256(
                                    payload.expected_person_source_id
                                ),
                                "evidence_document_reference_sha256": _reference_sha256(
                                    payload.identity_evidence_document_id
                                ),
                                "evidence_sha256": payload.expected_identity_evidence_sha256,
                                "link_proof_sha256": link_proof_sha256,
                                "raw_identifier_persisted": False,
                                "name_matching_used": False,
                                "fuzzy_matching_used": False,
                            }
                        ),
                        payload.recording_rationale,
                    )
                identity = await self._load_identity_link(connection, case_id=case_id)
                assert identity is not None
                return {
                    "created": created,
                    "identity_link": self._gate_view(
                        core=core,
                        legal=None,
                        identity=identity,
                        blockers=[],
                    )["identity_link"],
                    "publication_performed": False,
                    "raw_identifier_persisted": False,
                }
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A ligação de identidade já existe") from exc

    @staticmethod
    async def _load_legal_assessment(
        connection: asyncpg.Connection,
        *,
        case_id: str,
    ) -> dict[str, Any] | None:
        row = await connection.fetchrow(
            """
            SELECT id, observation_id, case_id, assessment_scope, outcome,
                   assessment_document_sha256,
                   assessment_document_storage_backend,
                   assessment_document_byte_size,
                   assessment_document_mime_type,
                   assessor_reference_sha256, qualification_evidence_sha256,
                   conflict_check_sha256, assessed_at, valid_until,
                   recorded_by_id, recorded_by_alias, created_at
            FROM ept_independent_legal_assessments
            WHERE case_id = $1
            ORDER BY assessed_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            case_id,
        )
        return dict(row) if row is not None else None

    @staticmethod
    async def _load_identity_link(
        connection: asyncpg.Connection,
        *,
        case_id: str,
    ) -> dict[str, Any] | None:
        row = await connection.fetchrow(
            """
            SELECT identity_link.id, identity_link.observation_id,
                   identity_link.case_id, identity_link.person_id,
                   identity_link.evidence_document_id,
                   identity_link.official_subject_digest,
                   identity_link.person_source_id,
                   identity_link.evidence_sha256,
                   identity_link.link_proof_sha256,
                   person.source_id AS current_person_source_id,
                   person.active AS person_active,
                   evidence.publisher::text AS evidence_publisher,
                   evidence.kind::text AS evidence_kind,
                   evidence.official_identifier AS evidence_official_identifier,
                   evidence.url AS evidence_url,
                   evidence.content_sha256 AS current_evidence_sha256,
                   archive.id AS archive_id,
                   person_review.publishable AS person_publishable
            FROM ept_exact_identity_links AS identity_link
            JOIN people AS person ON person.id = identity_link.person_id
            JOIN source_documents AS evidence
              ON evidence.id = identity_link.evidence_document_id
            LEFT JOIN LATERAL (
                SELECT candidate.id
                FROM source_archive_attestations AS candidate
                WHERE candidate.source_document_id = evidence.id
                  AND candidate.content_sha256 = evidence.content_sha256
                  AND candidate.retrieval_url = evidence.url
                  AND candidate.retrieved_at = evidence.retrieved_at
                ORDER BY candidate.archived_at ASC, candidate.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT candidate.publishable
                FROM data_publication_reviews AS candidate
                WHERE candidate.entity_type = 'PERSON'
                  AND candidate.entity_id = person.id
                  AND candidate.source_document_id = evidence.id
                ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                LIMIT 1
            ) AS person_review ON TRUE
            WHERE identity_link.case_id = $1
            """,
            case_id,
        )
        return dict(row) if row is not None else None

    async def inspect_publication(self, *, case_id: str) -> dict[str, object]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            preview, _context = await self._publication_context(
                connection,
                case_id=case_id,
                lock=False,
            )
            return preview

    async def _publication_context(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, Any]]:
        core = await self._load_core(connection, case_id=case_id, lock=lock)
        legal = await self._load_legal_assessment(connection, case_id=case_id)
        identity = await self._load_identity_link(connection, case_id=case_id)
        blockers = self._core_blockers(core)
        if core["case_state"] != EditorialState.APPROVED.value:
            _block(blockers, "CASE_NOT_APPROVED", "O processo não está aprovado para este gate.")
        if legal is None:
            _block(blockers, "LEGAL_ASSESSMENT_MISSING", "Falta a avaliação jurídica independente.")
        else:
            if legal["assessment_scope"] != _LEGAL_SCOPE or legal["outcome"] != _LEGAL_PERMISSION:
                _block(
                    blockers, "LEGAL_ASSESSMENT_NOT_PERMISSIVE", "A avaliação não permite publicar."
                )
            valid_until = legal["valid_until"]
            if valid_until is not None and valid_until <= core["database_now"]:
                _block(
                    blockers, "LEGAL_ASSESSMENT_EXPIRED", "A avaliação jurídica já não está válida."
                )
            if legal["observation_id"] != core["observation_id"]:
                _block(
                    blockers,
                    "LEGAL_ASSESSMENT_MISMATCH",
                    "A avaliação pertence a outra observação.",
                )
        if identity is None:
            _block(
                blockers,
                "IDENTITY_LINK_MISSING",
                "Falta a ligação por identificador oficial exato.",
            )
        else:
            expected_link_proof = _identity_link_proof(
                case_id=case_id,
                observation_id=str(core["observation_id"]),
                subject_digest=str(core["official_subject_digest"]),
                person_id=str(identity["person_id"]),
                person_source_id=str(identity["person_source_id"]),
                evidence_document_id=str(identity["evidence_document_id"]),
                evidence_sha256=str(identity["evidence_sha256"]),
            )
            identity_invalid = (
                identity["observation_id"] != core["observation_id"]
                or identity["official_subject_digest"] != core["official_subject_digest"]
                or identity["person_source_id"] != identity["current_person_source_id"]
                or identity["evidence_sha256"] != identity["current_evidence_sha256"]
                or identity["evidence_official_identifier"] != identity["person_source_id"]
                or identity["link_proof_sha256"] != expected_link_proof
                or identity["archive_id"] is None
                or identity["person_active"] is not True
                or identity["person_publishable"] is not True
                or identity["evidence_publisher"] == "MEDIA"
                or identity["evidence_kind"] == "NEWS_ARTICLE"
                or not str(identity["evidence_url"]).startswith("https://")
            )
            if identity_invalid:
                _block(
                    blockers, "IDENTITY_LINK_INVALID", "A ligação exata deixou de ser verificável."
                )

        declaration_id = _declaration_id(case_id)
        publication_proof_sha256: str | None = None
        legal_proof_sha256: str | None = None
        if legal is not None:
            legal_proof_sha256 = _legal_assessment_proof(legal)
        if not blockers and legal is not None and identity is not None:
            publication_proof_sha256 = _publication_proof(
                core=core,
                legal=legal,
                identity=identity,
                declaration_id=declaration_id,
            )
        preview: dict[str, object] = {
            **self._gate_view(
                core=core,
                legal=legal,
                identity=identity,
                blockers=blockers,
            ),
            "declaration_id": declaration_id,
            "legal_assessment_proof_sha256": legal_proof_sha256,
            "publication_proof_sha256": publication_proof_sha256,
            "public_metadata": {
                "declaration_type": "Registo público de interesses",
                "declared_at": _iso(core["declared_at"]),
                "period_label": core["period_label"],
                "public_access_status": "PUBLIC_METADATA",
                "income_or_asset_content_included": False,
                "protected_identifier_included": False,
            },
            "eligible": not blockers,
            "automatic_publication": False,
            "publication_rule": (
                "Apenas ADMIN com MFA pode publicar numa transação que volta a verificar fonte, "
                "arquivo, versão, HMAC, pessoa, segunda fonte e avaliação jurídica documental."
            ),
        }
        return preview, {"core": core, "legal": legal, "identity": identity}

    @staticmethod
    def _confirm_publication(
        *,
        case_id: str,
        preview: Mapping[str, object],
        payload: EptPublicInterestPublicationRequest,
    ) -> None:
        legal = cast(Mapping[str, object] | None, preview["legal_assessment"])
        identity = cast(Mapping[str, object] | None, preview["identity_link"])
        checks: tuple[tuple[object, object, str], ...] = (
            (case_id, payload.expected_case_id, "processo"),
            (preview["case_revision"], payload.expected_revision, "revisão"),
            (preview["version_id"], payload.expected_version_id, "versão"),
            (preview["version_sha256"], payload.expected_version_sha256, "SHA-256 editorial"),
            (preview["observation_id"], payload.expected_observation_id, "observação"),
            (
                cast(Mapping[str, object], preview["source"])["content_sha256"],
                payload.expected_source_sha256,
                "SHA-256 da fonte",
            ),
            (
                preview["source_record_sha256"],
                payload.expected_source_record_sha256,
                "SHA-256 da observação",
            ),
            (preview["declaration_id"], payload.expected_declaration_id, "declaração"),
            (
                identity["person_id"] if identity else None,
                payload.expected_person_id,
                "pessoa",
            ),
            (
                identity["id"] if identity else None,
                payload.expected_identity_link_id,
                "ligação de identidade",
            ),
            (
                identity["link_proof_sha256"] if identity else None,
                payload.expected_identity_proof_sha256,
                "prova de identidade",
            ),
            (
                legal["id"] if legal else None,
                payload.expected_legal_assessment_id,
                "avaliação jurídica",
            ),
            (
                legal["document_sha256"] if legal else None,
                payload.expected_legal_document_sha256,
                "documento jurídico",
            ),
            (
                preview["legal_assessment_proof_sha256"],
                payload.expected_legal_assessment_proof_sha256,
                "prova da avaliação jurídica",
            ),
            (
                preview["publication_proof_sha256"],
                payload.expected_publication_proof_sha256,
                "prova de publicação",
            ),
        )
        for actual, expected, label in checks:
            if actual != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    async def publish(
        self,
        *,
        case_id: str,
        payload: EptPublicInterestPublicationRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor)
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"ept-publication:{case_id}",
                )
                preview, context = await self._publication_context(
                    connection,
                    case_id=case_id,
                    lock=True,
                )
                self._confirm_publication(case_id=case_id, preview=preview, payload=payload)
                blockers = cast(list[dict[str, str]], preview["blockers"])
                if blockers:
                    details = "; ".join(item["detail"] for item in blockers)
                    if preview["case_state"] != EditorialState.APPROVED.value:
                        raise EditorialConflictError(details)
                    raise EditorialSourceError(details)
                core = cast(dict[str, Any], context["core"])
                identity = cast(dict[str, Any], context["identity"])
                legal = cast(dict[str, Any], context["legal"])
                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")
                declaration_id = str(preview["declaration_id"])
                await connection.execute(
                    """
                    INSERT INTO asset_declaration_metadata
                        (id, person_id, declaration_type, declared_at, period_label,
                         public_access_status, source_document_id, notes, created_at)
                    VALUES ($1, $2, 'Registo público de interesses', $3, $4,
                            'PUBLIC_METADATA', $5, NULL, $6)
                    """,
                    declaration_id,
                    str(identity["person_id"]),
                    core["declared_at"],
                    core["period_label"],
                    str(core["source_id"]),
                    created_at,
                )
                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'ASSET_DECLARATION', $2,
                            'Publicação limitada a metadados do registo público de interesses',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'Fonte EPT, identidade exata e avaliação jurídica verificadas.',
                            'Sem conteúdo, património, identificadores ou parecer privado.',
                            TRUE, $3, $4, $5)
                    """,
                    review_id,
                    declaration_id,
                    str(core["source_id"]),
                    actor.public_alias,
                    created_at,
                )
                audit_id = _new_id("audit")
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, 'EPT_PUBLIC_INTEREST_DECLARATION', $2, 'PUBLISHED', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    audit_id,
                    declaration_id,
                    actor.public_alias,
                    _canonical_json(
                        {
                            "publishable": False,
                            "case_reference_sha256": _reference_sha256(case_id),
                            "observation_reference_sha256": _reference_sha256(
                                core["observation_id"]
                            ),
                        }
                    ),
                    _canonical_json(
                        {
                            "publishable": True,
                            "source_sha256": core["source_sha256"],
                            "source_record_sha256": core["source_record_sha256"],
                            "identity_proof_sha256": identity["link_proof_sha256"],
                            "legal_assessment_reference_sha256": _reference_sha256(legal["id"]),
                            "legal_document_sha256": legal["assessment_document_sha256"],
                            "publication_proof_sha256": payload.expected_publication_proof_sha256,
                            "public_review_reference_sha256": _reference_sha256(review_id),
                            "income_or_asset_content_included": False,
                            "protected_identifier_included": False,
                            "automatic_publication": False,
                        }
                    ),
                    payload.public_rationale,
                    created_at,
                )
                version_id = str(core["version_id"])
                next_revision = int(core["case_revision"]) + 1
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
                    target_id=declaration_id,
                    rationale=payload.rationale,
                    actor_id=actor.staff_id,
                    actor_alias=actor.public_alias,
                    created_at=created_at,
                )
                await self._insert_event(
                    connection,
                    event_id=event_id,
                    case_id=case_id,
                    version_id=version_id,
                    action="PUBLISH",
                    target_id=declaration_id,
                    rationale=payload.rationale,
                    actor=actor,
                    event_sha256=event_sha256,
                    created_at=created_at,
                )
                return {
                    "created": True,
                    "case_id": case_id,
                    "state": "PUBLISHED",
                    "revision": next_revision,
                    "declaration_id": declaration_id,
                    "decision_sha256": decision_sha256,
                    "event_sha256": event_sha256,
                    "publication_review_id": review_id,
                    "audit_event_id": audit_id,
                    "publication_proof_sha256": payload.expected_publication_proof_sha256,
                    "automatic_publication": False,
                }
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("Esta declaração ou publicação já existe") from exc

    async def inspect_withdrawal(self, *, case_id: str) -> dict[str, object]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            preview, _context = await self._withdrawal_context(
                connection,
                case_id=case_id,
                lock=False,
            )
            return preview

    async def _withdrawal_context(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, Any]]:
        core = await self._load_core(connection, case_id=case_id, lock=lock)
        declaration_id = _declaration_id(case_id)
        row = await connection.fetchrow(
            """
            SELECT declaration.id AS declaration_id,
                   declaration.person_id,
                   declaration.source_document_id,
                   review.id AS public_review_id,
                   review.publishable,
                   review.reviewed_at,
                   event.id AS publication_event_id,
                   event.version_id AS publication_event_version_id,
                   event.action::text AS publication_event_action,
                   event.rationale AS publication_event_rationale,
                   event.actor_id AS publication_event_actor_id,
                   event.actor_alias AS publication_event_actor_alias,
                   event.event_sha256 AS publication_event_sha256,
                   event.created_at AS publication_event_created_at,
                   audit.id AS publication_audit_event_id,
                   audit.after_json AS publication_audit_after
            FROM asset_declaration_metadata AS declaration
            LEFT JOIN LATERAL (
                SELECT candidate.id, candidate.publishable, candidate.reviewed_at
                FROM data_publication_reviews AS candidate
                WHERE candidate.entity_type = 'ASSET_DECLARATION'
                  AND candidate.entity_id = declaration.id
                  AND candidate.source_document_id = declaration.source_document_id
                ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                LIMIT 1
            ) AS review ON TRUE
            LEFT JOIN LATERAL (
                SELECT candidate.*
                FROM editorial_publication_events AS candidate
                WHERE candidate.case_id = $1
                  AND candidate.target_type = $3
                  AND candidate.target_id = declaration.id
                ORDER BY candidate.created_at DESC, candidate.id DESC
                LIMIT 1
            ) AS event ON TRUE
            LEFT JOIN LATERAL (
                SELECT candidate.id, candidate.after_json
                FROM audit_events AS candidate
                WHERE candidate.entity_type = 'EPT_PUBLIC_INTEREST_DECLARATION'
                  AND candidate.entity_id = declaration.id
                  AND candidate.action = 'PUBLISHED'
                ORDER BY candidate.created_at DESC, candidate.id DESC
                LIMIT 1
            ) AS audit ON TRUE
            WHERE declaration.id = $2
            """,
            case_id,
            declaration_id,
            _TARGET_TYPE,
        )
        blockers: list[dict[str, str]] = []
        if core["case_state"] != EditorialState.PUBLISHED.value:
            _block(blockers, "CASE_NOT_PUBLISHED", "O processo não está publicado.")
        if row is None:
            _block(blockers, "DECLARATION_MISSING", "A projeção publicada não existe.")
        else:
            if row["source_document_id"] != core["source_id"] or row["publishable"] is not True:
                _block(blockers, "PUBLIC_REVIEW_INVALID", "A revisão pública ativa não coincide.")
            if (
                row["publication_event_action"] != "PUBLISH"
                or row["publication_event_version_id"] != core["version_id"]
            ):
                _block(blockers, "PUBLICATION_EVENT_INVALID", "O evento publicado não coincide.")
            elif row["publication_event_id"] is not None:
                expected_event_sha256 = _publication_event_sha256(
                    event_id=str(row["publication_event_id"]),
                    case_id=case_id,
                    version_id=str(row["publication_event_version_id"]),
                    action="PUBLISH",
                    target_id=declaration_id,
                    rationale=str(row["publication_event_rationale"]),
                    actor_id=str(row["publication_event_actor_id"]),
                    actor_alias=str(row["publication_event_actor_alias"]),
                    created_at=row["publication_event_created_at"],
                )
                if row["publication_event_sha256"] != expected_event_sha256:
                    _block(
                        blockers, "PUBLICATION_EVENT_HASH_INVALID", "O evento perdeu integridade."
                    )
            if row["publication_audit_event_id"] is None:
                _block(blockers, "PUBLICATION_AUDIT_MISSING", "Falta a auditoria original.")
        audit_after = _json_object(row["publication_audit_after"]) if row is not None else None
        publication_proof_sha256 = (
            str(audit_after.get("publication_proof_sha256"))
            if audit_after and audit_after.get("publication_proof_sha256")
            else None
        )
        if publication_proof_sha256 is None:
            _block(blockers, "PUBLICATION_PROOF_MISSING", "Falta a prova da publicação original.")
        public_effect = {
            "kind": "DECLARATION_METADATA_HIDDEN_HISTORY_PRESERVED",
            "declaration_reference_sha256": _reference_sha256(declaration_id),
            "active_public_metadata_after_withdrawal": False,
            "declaration_row_preserved": True,
            "identity_link_preserved_private": True,
            "legal_assessment_preserved_private": True,
            "message": (
                "Os metadados deixam de integrar a consulta ativa; fonte, histórico, ligação "
                "privada, avaliação jurídica e publicação original permanecem preservados."
            ),
        }
        withdrawal_proof_sha256 = _sha256_json(
            {
                "schema_version": _WITHDRAWAL_SCHEMA_VERSION,
                "case_reference_sha256": _reference_sha256(case_id),
                "version_sha256": str(core["version_sha256"]),
                "declaration_reference_sha256": _reference_sha256(declaration_id),
                "source_sha256": str(core["source_sha256"]),
                "publication_proof_sha256": publication_proof_sha256,
                "public_effect": public_effect,
            }
        )
        preview: dict[str, object] = {
            "case_id": case_id,
            "case_state": str(core["case_state"]),
            "case_revision": int(core["case_revision"]),
            "version_id": str(core["version_id"]),
            "version_sha256": str(core["version_sha256"]),
            "declaration_id": declaration_id,
            "source_sha256": str(core["source_sha256"]),
            "publication_proof_sha256": publication_proof_sha256,
            "withdrawal_proof_sha256": withdrawal_proof_sha256,
            "public_review_id": str(row["public_review_id"] or "") if row else "",
            "publication_audit_event_id": (
                str(row["publication_audit_event_id"] or "") if row else ""
            ),
            "publication_event_id": str(row["publication_event_id"] or "") if row else "",
            "publication_event_sha256": (str(row["publication_event_sha256"] or "") if row else ""),
            "public_effect": public_effect,
            "public_effect_sha256": _sha256_json(public_effect),
            "eligible": not blockers,
            "blockers": blockers,
            "automatic_withdrawal": False,
            "withdrawal_rule": (
                "A retirada acrescenta revisão, auditoria, decisão e evento; não apaga a linha, "
                "a fonte, a identidade protegida ou a avaliação jurídica."
            ),
        }
        return preview, {"core": core, "published": dict(row) if row else None}

    @staticmethod
    def _confirm_withdrawal(
        *,
        case_id: str,
        preview: Mapping[str, object],
        payload: EptPublicInterestWithdrawalRequest,
    ) -> None:
        checks = (
            (case_id, payload.expected_case_id, "processo"),
            (preview["case_revision"], payload.expected_revision, "revisão"),
            (preview["version_id"], payload.expected_version_id, "versão"),
            (preview["version_sha256"], payload.expected_version_sha256, "SHA-256 editorial"),
            (preview["declaration_id"], payload.expected_declaration_id, "declaração"),
            (preview["source_sha256"], payload.expected_source_sha256, "SHA-256 da fonte"),
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
        for actual, expected, label in checks:
            if actual != expected:
                raise EditorialConflictError(f"A confirmação de {label} já não é atual")

    async def withdraw(
        self,
        *,
        case_id: str,
        payload: EptPublicInterestWithdrawalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor)
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"ept-publication:{case_id}",
                )
                preview, context = await self._withdrawal_context(
                    connection,
                    case_id=case_id,
                    lock=True,
                )
                self._confirm_withdrawal(case_id=case_id, preview=preview, payload=payload)
                blockers = cast(list[dict[str, str]], preview["blockers"])
                if blockers:
                    details = "; ".join(item["detail"] for item in blockers)
                    if preview["case_state"] != EditorialState.PUBLISHED.value:
                        raise EditorialConflictError(details)
                    raise EditorialSourceError(details)
                core = cast(dict[str, Any], context["core"])
                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")
                declaration_id = str(preview["declaration_id"])
                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'ASSET_DECLARATION', $2,
                            'Retirada documentada de metadados EPT da consulta ativa',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'A fonte e o histórico ficam; apenas muda a revisão ativa.',
                            'Identidade, avaliação, decisões e prova não são apagadas.',
                            FALSE, $3, $4, $5)
                    """,
                    review_id,
                    declaration_id,
                    str(core["source_id"]),
                    actor.public_alias,
                    created_at,
                )
                audit_id = _new_id("audit")
                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, 'EPT_PUBLIC_INTEREST_DECLARATION', $2, 'WITHDRAWN', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    audit_id,
                    declaration_id,
                    actor.public_alias,
                    _canonical_json(
                        {
                            "publishable": True,
                            "publication_proof_sha256": preview["publication_proof_sha256"],
                            "publication_event_reference_sha256": _reference_sha256(
                                preview["publication_event_id"]
                            ),
                        }
                    ),
                    _canonical_json(
                        {
                            "publishable": False,
                            "source_sha256": payload.expected_source_sha256,
                            "withdrawal_proof_sha256": payload.expected_withdrawal_proof_sha256,
                            "public_effect": preview["public_effect"],
                            "public_effect_sha256": payload.expected_public_effect_sha256,
                            "reason_category": payload.reason_category.value,
                            "declaration_deleted": False,
                            "identity_link_deleted": False,
                            "legal_assessment_deleted": False,
                        }
                    ),
                    payload.public_rationale,
                    created_at,
                )
                internal_rationale = f"[{payload.reason_category.value}] {payload.rationale}"
                version_id = str(core["version_id"])
                next_revision = int(core["case_revision"]) + 1
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
                    target_id=declaration_id,
                    rationale=internal_rationale,
                    actor_id=actor.staff_id,
                    actor_alias=actor.public_alias,
                    created_at=created_at,
                )
                await self._insert_event(
                    connection,
                    event_id=event_id,
                    case_id=case_id,
                    version_id=version_id,
                    action="WITHDRAW",
                    target_id=declaration_id,
                    rationale=internal_rationale,
                    actor=actor,
                    event_sha256=event_sha256,
                    created_at=created_at,
                )
                return {
                    "created": True,
                    "case_id": case_id,
                    "state": "WITHDRAWN",
                    "revision": next_revision,
                    "declaration_id": declaration_id,
                    "reason_category": payload.reason_category.value,
                    "decision_sha256": decision_sha256,
                    "event_sha256": event_sha256,
                    "publication_review_id": review_id,
                    "audit_event_id": audit_id,
                    "public_effect": preview["public_effect"],
                    "public_effect_sha256": preview["public_effect_sha256"],
                }
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("Esta retirada já existe") from exc

    @staticmethod
    async def _insert_event(
        connection: asyncpg.Connection,
        *,
        event_id: str,
        case_id: str,
        version_id: str,
        action: str,
        target_id: str,
        rationale: str,
        actor: StaffSession,
        event_sha256: str,
        created_at: datetime,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO editorial_publication_events
                (id, case_id, version_id, action, target_type, target_id,
                 rationale, actor_id, actor_alias, event_sha256, created_at)
            VALUES ($1, $2, $3, $4::"EditorialPublicationAction", $5, $6,
                    $7, $8, $9, $10, $11)
            """,
            event_id,
            case_id,
            version_id,
            action,
            _TARGET_TYPE,
            target_id,
            rationale,
            actor.staff_id,
            actor.public_alias,
            event_sha256,
            created_at,
        )


def _identity_link_proof(
    *,
    case_id: str,
    observation_id: str,
    subject_digest: str,
    person_id: str,
    person_source_id: str,
    evidence_document_id: str,
    evidence_sha256: str,
) -> str:
    return _sha256_json(
        {
            "schema_version": "ept-exact-identity-link-v1",
            "case_reference_sha256": _reference_sha256(case_id),
            "observation_reference_sha256": _reference_sha256(observation_id),
            "official_subject_digest": subject_digest,
            "person_reference_sha256": _reference_sha256(person_id),
            "person_source_id_reference_sha256": _reference_sha256(person_source_id),
            "evidence_document_reference_sha256": _reference_sha256(evidence_document_id),
            "evidence_sha256": evidence_sha256,
            "match_method": "EXACT_OFFICIAL_IDENTIFIER_HMAC",
            "name_matching_used": False,
            "fuzzy_matching_used": False,
        }
    )


def _legal_assessment_proof(legal: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "schema_version": "ept-independent-legal-assessment-v1",
            "assessment_reference_sha256": _reference_sha256(legal["id"]),
            "case_reference_sha256": _reference_sha256(legal["case_id"]),
            "observation_reference_sha256": _reference_sha256(legal["observation_id"]),
            "scope": legal["assessment_scope"],
            "outcome": legal["outcome"],
            "document_sha256": legal["assessment_document_sha256"],
            "document_byte_size": legal["assessment_document_byte_size"],
            "document_mime_type": legal["assessment_document_mime_type"],
            "assessor_reference_sha256": legal["assessor_reference_sha256"],
            "qualification_evidence_sha256": legal["qualification_evidence_sha256"],
            "conflict_check_sha256": legal["conflict_check_sha256"],
            "assessed_at": _iso(legal["assessed_at"]),
            "valid_until": _iso(legal["valid_until"]),
            "system_issued_legal_opinion": False,
        }
    )


def _publication_proof(
    *,
    core: Mapping[str, Any],
    legal: Mapping[str, Any],
    identity: Mapping[str, Any],
    declaration_id: str,
) -> str:
    return _sha256_json(
        {
            "schema_version": _PUBLICATION_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(core["case_id"]),
            "version_sha256": core["version_sha256"],
            "observation_reference_sha256": _reference_sha256(core["observation_id"]),
            "source_sha256": core["source_sha256"],
            "source_record_sha256": core["source_record_sha256"],
            "person_reference_sha256": _reference_sha256(identity["person_id"]),
            "identity_link_proof_sha256": identity["link_proof_sha256"],
            "legal_assessment_proof_sha256": _legal_assessment_proof(legal),
            "declaration_reference_sha256": _reference_sha256(declaration_id),
            "declared_at": _iso(core["declared_at"]),
            "period_label": core["period_label"],
            "public_access_status": "PUBLIC_METADATA",
            "income_or_asset_content_included": False,
            "protected_identifier_included": False,
            "automatic_publication": False,
        }
    )
