"""Publicação organizacional específica; a prova de identidade permanece privada."""

from __future__ import annotations

import hmac
import json
import re
import uuid
from typing import Any

import asyncpg

from app.models.base_organisation import (
    OrganisationProofRequest,
    OrganisationPublicationProposalRequest,
    OrganisationPublicationRequest,
    OrganisationWithdrawalRequest,
    safe_registry_record_id,
    safe_registry_text,
)
from app.models.editorial import EditorialAction, EditorialCaseKind, EditorialState, StaffSession
from app.repositories.base_organisation_editorial import BaseOrganisationEditorialRepository
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.services.base_organisation_identity import canonical_json, iso, sha256

SCHEMA = "v5.53-organisation-publication/v1"
PUBLIC_SCHEMA = "v5.53-public-organisation/v1"
SUBJECT = "BASE_ORGANISATION_IDENTITY_VERSION"
TARGET = "BASE_PUBLIC_ORGANISATION"
CONSTRAINTS = {"identity_remains_private": True, "zero_graph": True}


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> dict[str, Any]:
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict):
        raise EditorialSourceError("A prova editorial não é válida")
    return result


def validate_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Contrato fechado sem NIPC, HMAC ou hash da observação privada."""
    if (
        set(value)
        != {
            "schema_version",
            "identity",
            "public_fields",
            "evidence",
            "source",
            "archive",
            "constraints",
        }
        or value["schema_version"] != SCHEMA
        or value["constraints"] != CONSTRAINTS
    ):
        raise ValueError("Âmbito de publicação organizacional inválido")
    identity, fields, evidence = value["identity"], value["public_fields"], value["evidence"]
    if (
        not isinstance(identity, dict)
        or set(identity) != {"case_id", "version_id", "decision_id", "observation_id"}
        or not isinstance(fields, dict)
        or set(fields) != {"id", "legal_name", "kind", "registry_record_id", "official_url"}
        or not isinstance(evidence, dict)
        or set(evidence) != {"source_record_sha256", "identity_proposal_sha256"}
    ):
        raise ValueError("A projeção contém campos não autorizados")
    for key, prefix in (
        ("case_id", "editorial_case"),
        ("version_id", "editorial_version"),
        ("decision_id", "editorial_decision"),
        ("observation_id", "base_org_identity"),
    ):
        if not re.fullmatch(rf"{prefix}_[0-9a-f]{{32}}", str(identity[key])):
            raise ValueError("Referência privada inválida")
    if not re.fullmatch(r"base_public_org_[0-9a-f]{32}", str(fields["id"])):
        raise ValueError("Identificador público independente inválido")
    safe_registry_text(fields["legal_name"])
    safe_registry_record_id(fields["registry_record_id"])
    if fields["kind"] not in {"PUBLIC_BODY", "COMPANY", "NON_PROFIT", "EUROPEAN_BODY", "OTHER"}:
        raise ValueError("Categoria organizacional inválida")
    for digest in evidence.values():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Hash de prova inválido")
    # Os metadados da fonte/arquivo reutilizam o contrato restrito e testado da V5.52.
    from app.repositories.base_organisation_editorial import (
        _REVIEW_CONSTRAINTS,
        _validate_projection,
    )
    from app.services.base_organisation_identity import PROPOSAL_SCHEMA

    _validate_projection(
        {
            "schema_version": PROPOSAL_SCHEMA,
            "candidate": {
                "registry_record_id": fields["registry_record_id"],
                "legal_name": fields["legal_name"],
                "kind": fields["kind"],
                "observed_at": value["source"]["retrieved_at"],
                "source_record_sha256": evidence["source_record_sha256"],
            },
            "source": value["source"],
            "archive": value["archive"],
            "review_constraints": _REVIEW_CONSTRAINTS,
        }
    )
    if fields["official_url"] != value["source"]["url"]:
        raise ValueError("A ligação pública não coincide com a fonte")
    return value


class BaseOrganisationPublicationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.identities = BaseOrganisationEditorialRepository(pool)

    @staticmethod
    async def _case(
        connection: asyncpg.Connection, case_id: str, kind: str, *, lock: bool = False
    ) -> dict[str, Any]:
        if lock:
            await connection.fetchval(
                "SELECT id FROM editorial_cases WHERE id = $1 FOR UPDATE", case_id
            )
        row = await connection.fetchrow(
            """SELECT c.id, c.subject_id, c.subject_type, c.source_document_id,
                      c.current_version_id, c.current_state::text, c.revision, c.origin::text,
                      v.normalized_json, v.normalized_sha256,
                      d.id AS decision_id, d.action::text AS decision_action,
                      d.version_id AS decision_version_id, d.source_confirmed
               FROM editorial_cases c
               JOIN editorial_versions v ON v.id = c.current_version_id AND v.case_id = c.id
               JOIN editorial_decisions d ON d.case_id = c.id AND d.case_revision = c.revision
               WHERE c.id = $1 AND c.kind::text = $2""",
            case_id,
            kind,
        )
        if row is None:
            raise EditorialNotFoundError("Processo organizacional não encontrado")
        result = dict(row)
        result["normalized_json"] = _json(row["normalized_json"])
        if sha256(result["normalized_json"]) != row["normalized_sha256"]:
            raise EditorialSourceError("A versão editorial perdeu a integridade")
        return result

    async def _identity(
        self, connection: asyncpg.Connection, identity_case_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        case = await self._case(connection, identity_case_id, "ORGANISATION_IDENTITY")
        normalized = case["normalized_json"]
        candidate = await self.identities.get_exact_candidate(
            observation_id=case["subject_id"],
            source_record_sha256=str(
                normalized.get("candidate", {}).get("source_record_sha256", "")
            ),
            connection=connection,
        )
        if (
            candidate is None
            or not candidate["proposal_eligible"]
            or self.identities._normalized_proposal(candidate) != normalized
            or case["source_document_id"] != candidate["source_document_id"]
        ):
            raise EditorialSourceError("A fonte e a identidade privada deixaram de coincidir")
        return case, candidate

    @staticmethod
    async def _lock_identity(connection: asyncpg.Connection, identity_case_id: str) -> None:
        # O digest serve só para serialização interna; nunca regressa ao chamador.
        digest = await connection.fetchval(
            """SELECT o.protected_identifier_digest FROM editorial_cases c
               JOIN base_organisation_identity_observations o ON o.id = c.subject_id
               WHERE c.id = $1 AND c.kind = 'ORGANISATION_IDENTITY'""",
            identity_case_id,
        )
        if digest is None:
            raise EditorialNotFoundError("Prova privada não encontrada")
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"base-organisation-publication:{digest}",
        )
        await connection.fetchrow(
            """SELECT c.id FROM editorial_cases c
               JOIN source_documents s ON s.id = c.source_document_id
               WHERE c.id = $1 FOR UPDATE OF c FOR SHARE OF s""",
            identity_case_id,
        )

    @staticmethod
    async def _reserved_id(connection: asyncpg.Connection, observation_id: str) -> str | None:
        rows = await connection.fetch(
            """SELECT DISTINCT v.normalized_json->'public_fields'->>'id' AS public_id
               FROM editorial_cases c JOIN editorial_versions v ON v.id = c.current_version_id
               JOIN base_organisation_identity_observations prior
                 ON prior.id = v.normalized_json->'identity'->>'observation_id'
               JOIN base_organisation_identity_observations selected
                 ON selected.id = $1
                AND selected.protected_identifier_digest = prior.protected_identifier_digest
               WHERE c.kind = 'ORGANISATION_PUBLICATION'""",
            observation_id,
        )
        if len(rows) > 1:
            raise EditorialConflictError(
                "Existem referências incompatíveis para a mesma identidade"
            )
        return str(rows[0]["public_id"]) if rows else None

    @staticmethod
    def _approved(case: dict[str, Any]) -> bool:
        return (
            case["origin"] == "INGESTION"
            and case["current_state"] == "APPROVED"
            and case["decision_action"] == "APPROVE"
            and case["source_confirmed"] is True
            and case["decision_version_id"] == case["current_version_id"]
        )

    @staticmethod
    def _normalized(
        case: dict[str, Any], candidate: dict[str, Any], public_id: str
    ) -> dict[str, Any]:
        source = candidate["source"]
        return validate_projection(
            {
                "schema_version": SCHEMA,
                "identity": {
                    "case_id": case["id"],
                    "version_id": case["current_version_id"],
                    "decision_id": case["decision_id"],
                    "observation_id": candidate["observation_id"],
                },
                "public_fields": {
                    "id": public_id,
                    "legal_name": candidate["legal_name"],
                    "kind": candidate["kind"],
                    "registry_record_id": candidate["registry_record_id"],
                    "official_url": source["url"],
                },
                "evidence": {
                    "source_record_sha256": candidate["source_record_sha256"],
                    "identity_proposal_sha256": case["normalized_sha256"],
                },
                "source": source,
                "archive": candidate["archive"],
                "constraints": dict(CONSTRAINTS),
            }
        )

    @staticmethod
    async def _organisation(
        connection: asyncpg.Connection, public_id: str | None
    ) -> dict[str, Any] | None:
        row = await connection.fetchrow(
            """SELECT id, publication_status::text, current_publication_snapshot_id,
                      verification_status::text FROM organisations WHERE id = $1""",
            public_id,
        )
        return dict(row) if row else None

    async def _proposal_context(
        self, connection: asyncpg.Connection, identity_case_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        identity, candidate = await self._identity(connection, identity_case_id)
        public_id = await self._reserved_id(connection, str(candidate["observation_id"]))
        existing = await self._organisation(connection, public_id)
        blockers = []
        if not self._approved(identity):
            blockers.append("A identidade exige aprovação humana atual e confirmação da fonte.")
        if existing and existing["publication_status"] != "WITHDRAWN":
            blockers.append("Já existe uma publicação ativa para esta identidade exata.")
        child = await connection.fetchval(
            """SELECT id FROM editorial_cases WHERE kind = 'ORGANISATION_PUBLICATION'
               AND subject_type = $1 AND subject_id = $2 AND source_document_id = $3""",
            SUBJECT,
            identity["current_version_id"],
            identity["source_document_id"],
        )
        if child:
            blockers.append("Esta versão de identidade já tem um processo de publicação separado.")
        proof = {
            "schema_version": SCHEMA,
            "action": "PROPOSE",
            "case_id": identity["id"],
            "version_id": identity["current_version_id"],
            "revision": identity["revision"],
            "decision_id": identity["decision_id"],
            "identity_proposal_sha256": identity["normalized_sha256"],
            "candidate_proof": candidate["proposal_confirmation_sha256"],
            "reserved_public_id": public_id,
            "existing": existing,
            "existing_case_id": child,
        }
        preview = {
            "case_id": identity["id"],
            "version_id": identity["current_version_id"],
            "revision": identity["revision"],
            "proof_sha256": sha256(proof),
            "public_fields": {
                key: candidate[key] for key in ("legal_name", "kind", "registry_record_id")
            },
            "source": candidate["source"],
            "archive": candidate["archive"],
            "existing_case_id": child,
            "eligible": not blockers,
            "blockers": blockers,
            **CONSTRAINTS,
            "publication_performed": False,
        }
        return preview, identity, candidate

    async def inspect_proposal(self, *, identity_case_id: str) -> dict[str, Any]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            preview, _, _ = await self._proposal_context(connection, identity_case_id)
            return preview

    @staticmethod
    def _confirm(case_id: str, preview: dict[str, Any], payload: OrganisationProofRequest) -> None:
        if (
            case_id != payload.expected_case_id
            or preview["case_id"] != case_id
            or preview["version_id"] != payload.expected_version_id
            or preview["revision"] != payload.expected_revision
            or not hmac.compare_digest(preview["proof_sha256"], payload.expected_proof_sha256)
        ):
            raise EditorialConflictError(
                "A prova mudou; atualize a pré-visualização antes de decidir"
            )
        if not preview["eligible"]:
            raise EditorialSourceError(" ".join(preview["blockers"]))

    async def create_proposal(
        self, *, payload: OrganisationPublicationProposalRequest, actor: StaffSession
    ) -> dict[str, Any]:
        safe_registry_text(actor.public_alias, max_length=80)
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await self._lock_identity(connection, payload.expected_case_id)
                preview, identity, candidate = await self._proposal_context(
                    connection, payload.expected_case_id
                )
                self._confirm(payload.expected_case_id, preview, payload)
                public_id = await self._reserved_id(
                    connection, str(candidate["observation_id"])
                ) or _id("base_public_org")
                case, created = await self.editorial.create_ingestion_case(
                    kind=EditorialCaseKind.ORGANISATION_PUBLICATION,
                    subject_type=SUBJECT,
                    subject_id=identity["current_version_id"],
                    source_document_id=identity["source_document_id"],
                    normalized_data=self._normalized(identity, candidate, public_id),
                    origin_alias="organisation-publication-proposal",
                    submission_rationale=(
                        "Projeção mínima da organização enviada para revisão humana própria; "
                        "a identidade permanece privada e nenhuma publicação foi efetuada."
                    ),
                    actor=actor,
                    connection=connection,
                    normalized_data_validator=validate_projection,
                )
                return {
                    "case": case,
                    "created": created,
                    "publication_performed": False,
                    **CONSTRAINTS,
                }
        except asyncpg.PostgresError:
            raise EditorialConflictError(
                "A proposta foi recusada sem concluir alterações"
            ) from None

    async def _publication_context(
        self, connection: asyncpg.Connection, case_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        case = await self._case(connection, case_id, "ORGANISATION_PUBLICATION")
        normalized = validate_projection(case["normalized_json"])
        identity, candidate = await self._identity(connection, normalized["identity"]["case_id"])
        public_id = normalized["public_fields"]["id"]
        existing = await self._organisation(connection, public_id)
        blockers = []
        if not self._approved(case) or not self._approved(identity):
            blockers.append(
                "A publicação e a identidade exigem aprovações humanas próprias e atuais."
            )
        if (
            case["subject_type"] != SUBJECT
            or case["subject_id"] != identity["current_version_id"]
            or case["source_document_id"] != identity["source_document_id"]
            or normalized != self._normalized(identity, candidate, public_id)
        ):
            blockers.append(
                "A versão aprovada deixou de coincidir com a prova exata da identidade."
            )
        if existing and (
            existing["publication_status"] != "WITHDRAWN"
            or not existing["current_publication_snapshot_id"]
        ):
            blockers.append("É necessária retirada explícita antes de publicar uma nova versão.")
        if await connection.fetchval(
            """SELECT EXISTS(
                   SELECT 1 FROM base_public_organisation_publication_snapshots
                   WHERE editorial_version_id = $1
               )""",
            case["current_version_id"],
        ):
            blockers.append(
                "Esta versão já foi publicada; uma correção exige uma nova prova oficial."
            )
        proof = {
            "schema_version": SCHEMA,
            "action": "PUBLISH",
            "case_id": case_id,
            "version_id": case["current_version_id"],
            "revision": case["revision"],
            "decision_id": case["decision_id"],
            "normalized_sha256": case["normalized_sha256"],
            "identity_revision": identity["revision"],
            "existing": existing,
        }
        return {
            "case_id": case_id,
            "version_id": case["current_version_id"],
            "revision": case["revision"],
            "proof_sha256": sha256(proof),
            "public_fields": normalized["public_fields"],
            "source": normalized["source"],
            "archive": normalized["archive"],
            "eligible": not blockers,
            "blockers": blockers,
            **CONSTRAINTS,
        }, case

    async def inspect_publication(self, *, case_id: str) -> dict[str, Any]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            preview, _ = await self._publication_context(connection, case_id)
            return preview

    async def _withdrawal_context(
        self, connection: asyncpg.Connection, case_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        case = await self._case(connection, case_id, "ORGANISATION_PUBLICATION")
        row = await connection.fetchrow(
            """SELECT s.id, s.organisation_id, s.publication_proof_sha256, s.public_record_sha256,
                      o.current_publication_snapshot_id, o.publication_status::text, e.event_sha256
               FROM base_public_organisation_publication_snapshots s
               JOIN organisations o ON o.id = s.organisation_id
               JOIN editorial_publication_events e ON e.case_id = s.editorial_case_id
                 AND e.version_id = s.editorial_version_id AND e.action = 'PUBLISH'
                 AND e.target_type = $2 AND e.target_id = s.organisation_id
               WHERE s.editorial_case_id = $1 AND s.editorial_version_id = $3""",
            case_id,
            TARGET,
            case["current_version_id"],
        )
        if row is None:
            raise EditorialNotFoundError("Não existe publicação para retirar neste processo")
        snapshot = dict(row)
        blockers = []
        if (
            case["current_state"] != "PUBLISHED"
            or case["decision_action"] != "PUBLISH"
            or snapshot["publication_status"] != "PUBLISHED"
            or snapshot["current_publication_snapshot_id"] != snapshot["id"]
        ):
            blockers.append("Este processo não corresponde à publicação ativa da organização.")
        proof = {
            "schema_version": SCHEMA,
            "action": "WITHDRAW",
            "case_id": case_id,
            "version_id": case["current_version_id"],
            "revision": case["revision"],
            "decision_id": case["decision_id"],
            "snapshot": snapshot,
        }
        return (
            {
                "case_id": case_id,
                "version_id": case["current_version_id"],
                "revision": case["revision"],
                "proof_sha256": sha256(proof),
                "public_id": snapshot["organisation_id"],
                "public_record_sha256": snapshot["public_record_sha256"],
                "eligible": not blockers,
                "blockers": blockers,
                "history_preserved": True,
                **CONSTRAINTS,
            },
            case,
            snapshot,
        )

    async def inspect_withdrawal(self, *, case_id: str) -> dict[str, Any]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            preview, _, _ = await self._withdrawal_context(connection, case_id)
            return preview

    @staticmethod
    def _admin(actor: StaffSession) -> None:
        if actor.role.value != "ADMIN" or actor.assurance_level != "aal2":
            raise EditorialConflictError("Esta decisão exige administrador autenticado com MFA")
        safe_registry_text(actor.public_alias, max_length=80)

    async def _decision(
        self,
        connection: asyncpg.Connection,
        case: dict[str, Any],
        actor: StaffSession,
        *,
        action: str,
        rationale: str,
        public_rationale: str,
        public_id: str,
        created_at: Any,
    ) -> str:
        previous = EditorialState.APPROVED if action == "PUBLISH" else EditorialState.PUBLISHED
        resulting = EditorialState.PUBLISHED if action == "PUBLISH" else EditorialState.WITHDRAWN
        decision_id, event_id = _id("editorial_decision"), _id("editorial_publication")
        args = dict(
            decision_id=decision_id,
            case_id=case["id"],
            version_id=case["current_version_id"],
            action=EditorialAction(action),
            previous_state=previous,
            resulting_state=resulting,
            case_revision=case["revision"] + 1,
            rationale=rationale,
            source_confirmed=action == "PUBLISH",
            actor=actor,
            created_at=created_at,
        )
        digest = self.editorial._decision_sha256(**args)
        await self.editorial._insert_decision(connection, **args, decision_sha256=digest)
        await connection.execute(
            """UPDATE editorial_cases
               SET current_state = $2::"EditorialState", revision = revision + 1,
                   updated_at = $3
               WHERE id = $1""",
            case["id"],
            resulting.value,
            created_at,
        )
        event = {
            "id": event_id,
            "case_id": case["id"],
            "version_id": case["current_version_id"],
            "action": action,
            "target_type": TARGET,
            "target_id": public_id,
            "rationale": public_rationale,
            "actor_id": actor.staff_id,
            "actor_alias": actor.public_alias,
            "created_at": iso(created_at),
        }
        await connection.execute(
            """INSERT INTO editorial_publication_events
               (id, case_id, version_id, action, target_type, target_id, rationale,
                actor_id, actor_alias, event_sha256, created_at)
               VALUES ($1,$2,$3,$4::"EditorialPublicationAction",$5,$6,$7,$8,$9,$10,$11)""",
            event_id,
            case["id"],
            case["current_version_id"],
            action,
            TARGET,
            public_id,
            public_rationale,
            actor.staff_id,
            actor.public_alias,
            sha256(event),
            created_at,
        )
        return event_id

    @staticmethod
    async def _review_audit(
        connection: asyncpg.Connection,
        *,
        public_id: str,
        source_id: str,
        actor: StaffSession,
        publishable: bool,
        rationale: str,
        proof: dict[str, Any],
        created_at: Any,
    ) -> None:
        await connection.execute(
            """INSERT INTO data_publication_reviews
               (id,entity_type,entity_id,purpose,legal_basis,sensitivity,necessity_assessment,
                proportionality_test,publishable,source_document_id,reviewed_by,reviewed_at)
               VALUES ($1,$2,$3,'Identificação factual mínima de organização com fonte oficial',
                'PUBLIC_INTEREST','PUBLIC_OFFICIAL',$4,
                'Sem NIPC, HMAC, moradas, pessoas, partes de contratos ou relações.',
                $5,$6,$7,$8)""",
            _id("publication_review"),
            TARGET,
            public_id,
            rationale,
            publishable,
            source_id,
            actor.public_alias,
            created_at,
        )
        await connection.execute(
            """INSERT INTO audit_events
               (id,entity_type,entity_id,action,actor_alias,after_json,reason,created_at)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8)""",
            _id("audit"),
            TARGET,
            public_id,
            "PUBLISHED" if publishable else "WITHDRAWN",
            actor.public_alias,
            canonical_json({"publishable": publishable, **proof, **CONSTRAINTS}),
            rationale,
            created_at,
        )

    async def publish(
        self, *, case_id: str, payload: OrganisationPublicationRequest, actor: StaffSession
    ) -> dict[str, Any]:
        self._admin(actor)
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                initial = await self._case(connection, case_id, "ORGANISATION_PUBLICATION")
                await self._lock_identity(
                    connection, initial["normalized_json"]["identity"]["case_id"]
                )
                await self._case(connection, case_id, "ORGANISATION_PUBLICATION", lock=True)
                preview, case = await self._publication_context(connection, case_id)
                self._confirm(case_id, preview, payload)
                normalized = case["normalized_json"]
                identity, fields = normalized["identity"], normalized["public_fields"]
                public_id, source_id = fields["id"], case["source_document_id"]
                now = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                public_record_hash = sha256(
                    {"schema_version": PUBLIC_SCHEMA, **fields, "source": normalized["source"]}
                )
                await connection.execute(
                    """INSERT INTO organisations
                       (id,legal_name,normalised_name,kind,official_url,source_document_id,
                        verification_status,publication_status,created_at,updated_at)
                       VALUES ($1,$2,$2,$3::"InterestEntityKind",$4,$5,
                        'PENDING_REVIEW','DRAFT',$6,$6)
                       ON CONFLICT (id) DO NOTHING""",
                    public_id,
                    fields["legal_name"],
                    fields["kind"],
                    fields["official_url"],
                    source_id,
                    now,
                )
                snapshot_id = _id("base_org_publication")
                await connection.execute(
                    """INSERT INTO base_public_organisation_publication_snapshots
                       (id,organisation_id,identity_observation_id,identity_case_id,identity_version_id,
                        identity_decision_id,editorial_case_id,editorial_version_id,source_document_id,
                        legal_name,kind,registry_record_id,official_url,source_record_sha256,
                        publication_proof_sha256,public_record_sha256,created_by_alias,created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::"InterestEntityKind",
                        $12,$13,$14,$15,$16,$17,$18)""",
                    snapshot_id,
                    public_id,
                    identity["observation_id"],
                    identity["case_id"],
                    identity["version_id"],
                    identity["decision_id"],
                    case_id,
                    case["current_version_id"],
                    source_id,
                    fields["legal_name"],
                    fields["kind"],
                    fields["registry_record_id"],
                    fields["official_url"],
                    normalized["evidence"]["source_record_sha256"],
                    preview["proof_sha256"],
                    public_record_hash,
                    actor.public_alias,
                    now,
                )
                await connection.execute(
                    """UPDATE organisations
                       SET legal_name=$2,normalised_name=$2,
                           kind=$3::"InterestEntityKind",official_url=$4,
                           source_document_id=$5,current_publication_snapshot_id=$6,
                           verification_status='VERIFIED',publication_status='PUBLISHED',
                           updated_at=$7
                       WHERE id=$1""",
                    public_id,
                    fields["legal_name"],
                    fields["kind"],
                    fields["official_url"],
                    source_id,
                    snapshot_id,
                    now,
                )
                await self._review_audit(
                    connection,
                    public_id=public_id,
                    source_id=source_id,
                    actor=actor,
                    publishable=True,
                    rationale=payload.public_rationale,
                    proof={
                        "public_record_sha256": public_record_hash,
                        "publication_proof_sha256": preview["proof_sha256"],
                    },
                    created_at=now,
                )
                event_id = await self._decision(
                    connection,
                    case,
                    actor,
                    action="PUBLISH",
                    rationale=payload.rationale,
                    public_rationale=payload.public_rationale,
                    public_id=public_id,
                    created_at=now,
                )
                await connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            return {
                "case_id": case_id,
                "state": "PUBLISHED",
                "public_id": public_id,
                "public_record_sha256": public_record_hash,
                "event_id": event_id,
                **CONSTRAINTS,
            }
        except asyncpg.PostgresError:
            raise EditorialConflictError(
                "A publicação foi recusada sem concluir alterações"
            ) from None

    async def withdraw(
        self, *, case_id: str, payload: OrganisationWithdrawalRequest, actor: StaffSession
    ) -> dict[str, Any]:
        self._admin(actor)
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                initial = await self._case(connection, case_id, "ORGANISATION_PUBLICATION")
                await self._lock_identity(
                    connection, initial["normalized_json"]["identity"]["case_id"]
                )
                await self._case(connection, case_id, "ORGANISATION_PUBLICATION", lock=True)
                preview, case, snapshot = await self._withdrawal_context(connection, case_id)
                self._confirm(case_id, preview, payload)
                public_id = snapshot["organisation_id"]
                now = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                public_rationale = f"{payload.reason.value}: {payload.public_rationale}"
                await connection.execute(
                    """UPDATE organisations SET publication_status='WITHDRAWN',updated_at=$2
                       WHERE id=$1""",
                    public_id,
                    now,
                )
                await self._review_audit(
                    connection,
                    public_id=public_id,
                    source_id=case["source_document_id"],
                    actor=actor,
                    publishable=False,
                    rationale=public_rationale,
                    proof={
                        "public_record_sha256": snapshot["public_record_sha256"],
                        "publication_proof_sha256": snapshot["publication_proof_sha256"],
                    },
                    created_at=now,
                )
                event_id = await self._decision(
                    connection,
                    case,
                    actor,
                    action="WITHDRAW",
                    rationale=payload.rationale,
                    public_rationale=public_rationale,
                    public_id=public_id,
                    created_at=now,
                )
                await connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            return {
                "case_id": case_id,
                "state": "WITHDRAWN",
                "public_id": public_id,
                "event_id": event_id,
                "history_preserved": True,
                **CONSTRAINTS,
            }
        except asyncpg.PostgresError:
            raise EditorialConflictError(
                "A retirada foi recusada sem concluir alterações"
            ) from None
