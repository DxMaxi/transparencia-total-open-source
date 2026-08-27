"""Publicação transacional de uma autoria parlamentar por identificadores oficiais."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal, cast

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialState,
    PoliticianInitiativeAuthorshipPublicationRequest,
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
from app.repositories.politician_initiative_authorship_editorial import (
    PoliticianInitiativeAuthorshipEditorialRepository,
    _reference_sha256,
)

_SUBJECT_TYPE = "PARLIAMENT_INITIATIVE_AUTHORSHIP"
_PROPOSAL_SCHEMA_VERSION = "politician-initiative-authorship-editorial-v1"
_PUBLICATION_SCHEMA_VERSION = "politician-initiative-authorship-publication-v1"
_TARGET_TYPE = "POLITICIAN_INITIATIVE_AUTHORSHIP"


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


def _required_object(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EditorialSourceError(f"{label} deixou de estar disponível na versão aprovada")
    return value


def _publication_event_sha256(
    *,
    event_id: str,
    case_id: str,
    version_id: str,
    action: Literal["PUBLISH", "WITHDRAW"],
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


def _publication_proof_sha256(
    *,
    case_id: str,
    version_id: object,
    version_sha256: object,
    source_sha256: object,
    source_record_sha256: object,
    observation_id: object,
    person_id: object,
    official_deputy_id: object,
    initiative_id: object,
    initiative_source_id: object,
    activity_source_sha256: object,
    activity_snapshot_sha256: object,
    relation: object,
    public_effect: dict[str, int],
) -> str:
    return _sha256_json(
        {
            "schema_version": _PUBLICATION_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case_id),
            "version_reference_sha256": _reference_sha256(version_id),
            "version_sha256": str(version_sha256),
            "authorship_source_sha256": str(source_sha256),
            "source_record_sha256": str(source_record_sha256),
            "observation_reference_sha256": _reference_sha256(observation_id),
            "person_reference_sha256": _reference_sha256(person_id),
            "official_deputy_id_reference_sha256": _reference_sha256(official_deputy_id),
            "initiative_reference_sha256": _reference_sha256(initiative_id),
            "initiative_source_id_reference_sha256": _reference_sha256(initiative_source_id),
            "activity_source_sha256": str(activity_source_sha256),
            "activity_snapshot_sha256": str(activity_snapshot_sha256),
            "relation": str(relation),
            "public_effect": public_effect,
            "identity_rule": "EXACT_AR_IDCADASTRO_ONLY",
            "initiative_rule": "EXACT_AR_INIID_ONLY",
            "relation_rule": "SOURCE_DECLARED_AUTHOR_ONLY",
            "name_matching_allowed": False,
            "party_matching_allowed": False,
            "collective_position_inference_allowed": False,
            "automatic_publication": False,
        }
    )


class PoliticianInitiativeAuthorshipPublicationRepository:
    """Publica uma relação AUTHOR ou reverte toda a transação."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.candidates = PoliticianInitiativeAuthorshipEditorialRepository(pool)

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
        lock: bool,
    ) -> Mapping[str, Any]:
        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        lock_clause = "FOR UPDATE OF editorial_case" if lock else ""
        row = await database.fetchrow(
            f"""
            SELECT editorial_case.id, editorial_case.subject_id,
                   editorial_case.source_document_id,
                   editorial_case.current_state::text AS current_state,
                   editorial_case.revision, editorial_case.current_version_id,
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
            {lock_clause}
            """,
            case_id,
        )
        if row is None:
            raise EditorialNotFoundError("Processo editorial de autoria não encontrado")
        return cast(Mapping[str, Any], row)

    @staticmethod
    def _proposal_matches_candidate(
        normalized: dict[str, Any],
        candidate: dict[str, object],
    ) -> bool:
        if normalized.get("schema_version") != _PROPOSAL_SCHEMA_VERSION:
            return False
        authorship = normalized.get("authorship")
        initiative = normalized.get("initiative")
        source_proof = normalized.get("source_proof")
        if not all(isinstance(item, dict) for item in (authorship, initiative, source_proof)):
            return False
        assert isinstance(authorship, dict)
        assert isinstance(initiative, dict)
        assert isinstance(source_proof, dict)
        source = candidate["source"]
        archive = candidate["archive"]
        snapshot = candidate["snapshot"]
        exact_initiative = candidate["initiative"]
        if not all(
            isinstance(item, dict) for item in (source, archive, snapshot, exact_initiative)
        ):
            return False
        assert isinstance(source, dict)
        assert isinstance(archive, dict)
        assert isinstance(snapshot, dict)
        assert isinstance(exact_initiative, dict)
        return (
            authorship.get("observation_reference_sha256")
            == _reference_sha256(candidate["observation_id"])
            and authorship.get("initiative_source_id_reference_sha256")
            == _reference_sha256(candidate["initiative_source_id"])
            and authorship.get("official_deputy_id_reference_sha256")
            == _reference_sha256(candidate["official_deputy_id"])
            and authorship.get("parliamentary_name") == candidate["parliamentary_name"]
            and authorship.get("parliamentary_group_label")
            == candidate["parliamentary_group_label"]
            and authorship.get("relation") == candidate["relation"]
            and authorship.get("source_record_sha256") == candidate["source_record_sha256"]
            and initiative.get("number") == exact_initiative.get("number")
            and initiative.get("type") == exact_initiative.get("type")
            and initiative.get("title") == exact_initiative.get("title")
            and initiative.get("status") == exact_initiative.get("status")
            and initiative.get("official_url") == exact_initiative.get("official_url")
            and initiative.get("exact_match_count") == 1
            and source_proof.get("source_document_reference_sha256")
            == _reference_sha256(candidate["source_document_id"])
            and source_proof.get("url") == source.get("url")
            and source_proof.get("retrieved_at") == source.get("retrieved_at")
            and source_proof.get("content_sha256") == source.get("content_sha256")
            and source_proof.get("archive_attestation_sha256") == archive.get("attestation_sha256")
            and source_proof.get("archive_byte_size") == archive.get("byte_size")
            and source_proof.get("normalised_sha256") == snapshot.get("normalised_sha256")
            and source_proof.get("parser_version") == snapshot.get("parser_version")
            and source_proof.get("collected_at") == snapshot.get("collected_at")
            and normalized.get("identity_rule") == "EXACT_AR_IDCADASTRO_ONLY"
            and normalized.get("initiative_rule") == "EXACT_AR_INIID_ONLY"
            and normalized.get("relation_rule") == "SOURCE_DECLARED_AUTHOR_ONLY"
            and normalized.get("name_matching_allowed") is False
            and normalized.get("party_matching_allowed") is False
            and normalized.get("collective_position_inference_allowed") is False
        )

    async def _published_initiative(
        self,
        *,
        legislature: str,
        initiative_source_id: str,
        connection: asyncpg.Connection | None,
        lock: bool,
    ) -> Mapping[str, Any] | None:
        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        lock_clause = "FOR UPDATE OF initiative, snapshot" if lock else ""
        row = await database.fetchrow(
            f"""
            SELECT initiative.id, initiative.source_id, initiative.number,
                   initiative.type, initiative.title, initiative.status,
                   initiative.introduced_at, initiative.official_url,
                   initiative.source_document_id,
                   snapshot.id AS snapshot_id,
                   snapshot.normalised_sha256 AS snapshot_sha256,
                   snapshot.collected_at,
                   review.reviewed_at AS activity_reviewed_at,
                   source.url AS source_url,
                   source.retrieved_at AS source_retrieved_at,
                   source.content_sha256 AS source_sha256
            FROM parliamentary_initiatives AS initiative
            JOIN parliament_activity_snapshots AS snapshot
              ON snapshot.id = initiative.snapshot_id
             AND snapshot.source_document_id = initiative.source_document_id
             AND snapshot.legislature = initiative.legislature
            JOIN source_documents AS source
              ON source.id = initiative.source_document_id
            JOIN LATERAL (
                SELECT candidate.publishable, candidate.reviewed_at
                FROM data_publication_reviews AS candidate
                WHERE candidate.entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                  AND candidate.entity_id = snapshot.id
                  AND candidate.source_document_id = source.id
                ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                LIMIT 1
            ) AS review ON review.publishable = TRUE
            WHERE initiative.legislature = $1
              AND initiative.source_id = $2
              AND source.publisher = 'PARLIAMENT'
              AND source.kind <> 'NEWS_ARTICLE'
              AND EXISTS (
                  SELECT 1
                  FROM source_archive_attestations AS archive
                  WHERE archive.source_document_id = source.id
                    AND archive.content_sha256 = source.content_sha256
                    AND archive.retrieval_url = source.url
                    AND archive.retrieved_at = source.retrieved_at
              )
            ORDER BY review.reviewed_at DESC, snapshot.collected_at DESC,
                     snapshot.id DESC, initiative.id DESC
            LIMIT 1
            {lock_clause}
            """,
            legislature,
            initiative_source_id,
        )
        return cast(Mapping[str, Any] | None, row)

    async def _inspect_context(
        self,
        *,
        case_id: str,
        connection: asyncpg.Connection | None,
        lock: bool,
    ) -> tuple[dict[str, object], dict[str, object]]:
        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        if lock and connection is not None:
            locked_case_id = await connection.fetchval(
                "SELECT id FROM editorial_cases WHERE id = $1 FOR UPDATE",
                case_id,
            )
            if locked_case_id is None:
                raise EditorialNotFoundError("Processo editorial de autoria não encontrado")

        case = await self._load_case(case_id=case_id, connection=connection, lock=lock)
        observation_id = str(case["subject_id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", observation_id):
            raise EditorialSourceError("A referência editorial da autoria deixou de ser válida")
        if lock and connection is not None:
            locked_observation = await connection.fetchval(
                "SELECT id FROM parliament_initiative_author_observations WHERE id = $1 FOR UPDATE",
                observation_id,
            )
            if locked_observation is None:
                raise EditorialSourceError("A observação oficial deixou de existir")

        candidate = await self.candidates.get_exact_candidate(
            observation_id=observation_id,
            connection=connection,
        )
        if candidate is None:
            raise EditorialSourceError(
                "A autoria aprovada deixou de corresponder ao arquivo oficial atestado"
            )
        normalized = _json_object(case["normalized_data"])
        source = _required_object(candidate["source"], label="A fonte oficial")
        archive = _required_object(candidate["archive"], label="O arquivo oficial")

        identity_lock_clause = "FOR UPDATE OF person" if lock else ""
        identity = await database.fetchrow(
            f"""
            SELECT person.id AS person_id, person.role::text AS person_role,
                   person.active AS person_active,
                   latest_review.publishable AS identity_publishable,
                   latest_review.reviewed_at AS identity_reviewed_at
            FROM people AS person
            LEFT JOIN LATERAL (
                SELECT review.publishable, review.reviewed_at
                FROM data_publication_reviews AS review
                WHERE review.entity_type = 'PERSON'
                  AND review.entity_id = person.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) AS latest_review ON TRUE
            WHERE person.source_id = $1
            {identity_lock_clause}
            """,
            str(candidate["official_deputy_id"]),
        )
        published_initiative = await self._published_initiative(
            legislature=str(candidate["legislature"]),
            initiative_source_id=str(candidate["initiative_source_id"]),
            connection=connection,
            lock=lock,
        )
        existing = await database.fetchrow(
            """
            SELECT id, person_id, initiative_id, source_observation_id,
                   source_record_sha256
            FROM politician_initiative_authorships
            WHERE source_observation_id = $1
               OR ($2::text IS NOT NULL AND person_id = $2
                   AND initiative_id = $3 AND relation = 'AUTHOR')
            ORDER BY id
            LIMIT 1
            """,
            observation_id,
            str(identity["person_id"]) if identity is not None else None,
            str(published_initiative["id"]) if published_initiative is not None else "",
        )
        if lock and connection is not None and existing is not None:
            await connection.fetchval(
                "SELECT id FROM politician_initiative_authorships WHERE id = $1 FOR UPDATE",
                str(existing["id"]),
            )

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
            block("LATEST_APPROVAL_INVALID", "A decisão atual não confirma esta versão e fonte.")
        if not self._proposal_matches_candidate(normalized, candidate):
            block(
                "APPROVED_VERSION_DRIFT",
                "A versão aprovada diverge da relação oficial reconstruída no servidor.",
            )
        candidate_blockers = candidate["blocked_reasons"]
        assert isinstance(candidate_blockers, list)
        for detail in candidate_blockers:
            block("SOURCE_CANDIDATE_BLOCKED", str(detail))
        if str(case["source_document_id"]) != str(candidate["source_document_id"]):
            block("SOURCE_DOCUMENT_CHANGED", "O documento do processo deixou de coincidir.")
        if str(candidate["relation"]) != "AUTHOR":
            block("RELATION_NOT_AUTHOR", "A fonte já não declara a relação literal AUTHOR.")
        if identity is None:
            block("EXACT_IDENTITY_MISSING", "O idCadastro não tem uma identidade pública exata.")
        else:
            if str(identity["person_role"]) != "DEPUTY" or identity["person_active"] is not True:
                block(
                    "PERSON_NOT_ACTIVE_DEPUTY",
                    "O idCadastro está ligado a uma pessoa incompatível.",
                )
            if identity["identity_publishable"] is not True:
                block(
                    "PERSON_NOT_PUBLISHED",
                    "A identidade exata não tem revisão pública positiva atual.",
                )
        if published_initiative is None:
            block(
                "INITIATIVE_NOT_PUBLIC",
                "O IniId não existe numa fotografia de atividade com revisão pública positiva.",
            )
        if existing is not None:
            block(
                "AUTHORSHIP_ALREADY_EXISTS",
                "Já existe uma autoria pública para esta observação ou para a mesma ligação exata.",
            )

        public_effect = {
            "authorships_to_create": 1,
            "authorship_reviews_to_append": 1,
            "authorship_audits_to_append": 1,
            "editorial_decisions_to_append": 1,
            "publication_events_to_append": 1,
            "people_to_create": 0,
            "initiatives_to_create": 0,
            "party_links_to_create": 0,
        }
        publication_proof_sha256: str | None = None
        if identity is not None and published_initiative is not None:
            publication_proof_sha256 = _publication_proof_sha256(
                case_id=case_id,
                version_id=case["current_version_id"],
                version_sha256=case["normalized_sha256"],
                source_sha256=source["content_sha256"],
                source_record_sha256=candidate["source_record_sha256"],
                observation_id=observation_id,
                person_id=identity["person_id"],
                official_deputy_id=candidate["official_deputy_id"],
                initiative_id=published_initiative["id"],
                initiative_source_id=candidate["initiative_source_id"],
                activity_source_sha256=published_initiative["source_sha256"],
                activity_snapshot_sha256=published_initiative["snapshot_sha256"],
                relation=candidate["relation"],
                public_effect=public_effect,
            )
        eligible = not blockers and publication_proof_sha256 is not None
        preview: dict[str, object] = {
            "case_id": case_id,
            "case_state": str(case["current_state"]),
            "case_revision": int(case["revision"]),
            "version_id": str(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "source_record_sha256": str(candidate["source_record_sha256"]),
            "source": source,
            "archive": archive,
            "authorship": {
                "observation_reference_sha256": _reference_sha256(observation_id),
                "official_deputy_id": str(candidate["official_deputy_id"]),
                "initiative_source_id": str(candidate["initiative_source_id"]),
                "parliamentary_name": str(candidate["parliamentary_name"]),
                "relation": str(candidate["relation"]),
            },
            "identity": (
                {
                    "person_reference_sha256": _reference_sha256(identity["person_id"]),
                    "exact_match": True,
                    "reviewed": identity["identity_publishable"] is True,
                }
                if identity is not None
                else None
            ),
            "initiative": (
                {
                    "initiative_reference_sha256": _reference_sha256(published_initiative["id"]),
                    "number": str(published_initiative["number"]),
                    "type": str(published_initiative["type"]),
                    "title": str(published_initiative["title"]),
                    "status": published_initiative["status"],
                    "introduced_at": published_initiative["introduced_at"],
                    "official_url": str(published_initiative["official_url"]),
                    "activity_snapshot_sha256": str(published_initiative["snapshot_sha256"]),
                    "activity_source": {
                        "url": str(published_initiative["source_url"]),
                        "retrieved_at": published_initiative["source_retrieved_at"],
                        "content_sha256": str(published_initiative["source_sha256"]),
                    },
                }
                if published_initiative is not None
                else None
            ),
            "public_effect": public_effect,
            "publication_proof_sha256": publication_proof_sha256 if eligible else None,
            "eligible": eligible,
            "blockers": blockers,
            "automatic_publication": False,
            "human_review_required": True,
            "name_matching_allowed": False,
            "party_matching_allowed": False,
            "collective_position_inference_allowed": False,
            "withdrawal_required_before_real_activation": True,
            "publication_rule": (
                "A ação ADMIN volta a provar a versão, os dois arquivos, IniId, idCadastro, "
                "relação AUTHOR e revisões públicas atuais; a ligação e todo o histórico são "
                "acrescentados na mesma transação."
            ),
        }
        return preview, {
            "case": dict(case),
            "candidate": candidate,
            "identity": dict(identity) if identity is not None else None,
            "published_initiative": (
                dict(published_initiative) if published_initiative is not None else None
            ),
            "observation_id": observation_id,
        }

    @staticmethod
    def _confirm_payload(
        *,
        case_id: str,
        preview: dict[str, object],
        payload: PoliticianInitiativeAuthorshipPublicationRequest,
    ) -> None:
        source = _required_object(preview["source"], label="A fonte oficial")
        initiative = _required_object(preview["initiative"], label="A iniciativa pública")
        if case_id != payload.expected_case_id or str(preview["case_id"]) != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        if str(preview["version_id"]) != payload.expected_version_id:
            raise EditorialConflictError("A versão editorial mudou antes da publicação")
        if str(preview["version_sha256"]) != payload.expected_version_sha256:
            raise EditorialConflictError("O SHA-256 da versão mudou antes da publicação")
        if str(source["content_sha256"]) != payload.expected_source_sha256:
            raise EditorialConflictError("O SHA-256 da fonte de autoria mudou")
        if str(preview["source_record_sha256"]) != payload.expected_source_record_sha256:
            raise EditorialConflictError("O SHA-256 da relação de autoria mudou")
        if str(initiative["activity_snapshot_sha256"]) != payload.expected_activity_snapshot_sha256:
            raise EditorialConflictError("O SHA-256 da fotografia pública mudou")
        if str(preview["publication_proof_sha256"]) != payload.expected_publication_proof_sha256:
            raise EditorialConflictError("A prova de publicação deixou de coincidir")

    async def publish(
        self,
        *,
        case_id: str,
        payload: PoliticianInitiativeAuthorshipPublicationRequest,
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
                    f"politician-initiative-authorship-publication:{case_id}",
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
                identity = context["identity"]
                initiative = context["published_initiative"]
                assert isinstance(case, dict)
                assert isinstance(candidate, dict)
                assert isinstance(identity, dict)
                assert isinstance(initiative, dict)

                authorship_id = _new_id("politician_initiative_authorship")
                await connection.execute(
                    """
                    INSERT INTO politician_initiative_authorships
                        (id, person_id, initiative_id, source_observation_id,
                         relation, source_document_id, source_record_sha256, created_at)
                    VALUES ($1, $2, $3, $4, 'AUTHOR', $5, $6, $7)
                    """,
                    authorship_id,
                    str(identity["person_id"]),
                    str(initiative["id"]),
                    str(context["observation_id"]),
                    str(candidate["source_document_id"]),
                    str(candidate["source_record_sha256"]),
                    created_at,
                )

                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'POLITICIAN_INITIATIVE_AUTHORSHIP', $2,
                            'Autoria parlamentar factual para fiscalização democrática',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'IniId, idCadastro, relação AUTHOR, arquivos e revisões confirmados.',
                            'Não infere voto, apoio ou posição partidária.',
                            TRUE, $3, $4, $5)
                    """,
                    review_id,
                    authorship_id,
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
                    VALUES ($1, 'POLITICIAN_INITIATIVE_AUTHORSHIP', $2, 'PUBLISHED', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    audit_id,
                    authorship_id,
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
                            "authorship_source_sha256": payload.expected_source_sha256,
                            "source_record_sha256": payload.expected_source_record_sha256,
                            "activity_snapshot_sha256": (payload.expected_activity_snapshot_sha256),
                            "observation_reference_sha256": _reference_sha256(
                                context["observation_id"]
                            ),
                            "official_deputy_id_reference_sha256": _reference_sha256(
                                candidate["official_deputy_id"]
                            ),
                            "initiative_source_id_reference_sha256": _reference_sha256(
                                candidate["initiative_source_id"]
                            ),
                            "relation": "AUTHOR",
                            "people_created": 0,
                            "initiatives_created": 0,
                            "party_links_created": 0,
                            "publication_proof_sha256": (payload.expected_publication_proof_sha256),
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
                    target_id=authorship_id,
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
                            'POLITICIAN_INITIATIVE_AUTHORSHIP', $4, $5, $6, $7, $8, $9)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    authorship_id,
                    payload.public_rationale,
                    actor.staff_id,
                    actor.public_alias,
                    event_sha256,
                    created_at,
                )

                public_gate = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM politician_initiative_authorships AS authorship
                        JOIN parliament_initiative_author_observations AS observation
                          ON observation.id = authorship.source_observation_id
                         AND observation.official_deputy_id = $3
                         AND observation.initiative_source_id = $4
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
                        WHERE authorship.id = $1
                          AND authorship.source_observation_id = $2
                          AND authorship.relation = 'AUTHOR'
                          AND authorship.source_record_sha256 = $5
                          AND activity_snapshot.normalised_sha256 = $6
                          AND author_source.publisher = 'PARLIAMENT'
                          AND activity_source.publisher = 'PARLIAMENT'
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
                    )
                    """,
                    authorship_id,
                    str(context["observation_id"]),
                    str(candidate["official_deputy_id"]),
                    str(candidate["initiative_source_id"]),
                    str(candidate["source_record_sha256"]),
                    str(initiative["snapshot_sha256"]),
                )
                if public_gate is not True:
                    raise EditorialSourceError(
                        "A projeção pública não satisfez a prova exata e foi revertida"
                    )
        except asyncpg.IntegrityConstraintViolationError as exc:
            raise EditorialConflictError(
                "O processo, a identidade ou a iniciativa mudou; nada foi publicado"
            ) from exc

        return {
            "created": True,
            "case_id": case_id,
            "version_id": payload.expected_version_id,
            "state": EditorialState.PUBLISHED.value,
            "authorship_id": authorship_id,
            "authorship_review_id": review_id,
            "audit_event_id": audit_id,
            "editorial_decision_id": decision_id,
            "publication_event_id": event_id,
            "source_sha256": payload.expected_source_sha256,
            "source_record_sha256": payload.expected_source_record_sha256,
            "activity_snapshot_sha256": payload.expected_activity_snapshot_sha256,
            "publication_proof_sha256": payload.expected_publication_proof_sha256,
            "people_created": 0,
            "initiatives_created": 0,
            "party_links_created": 0,
            "automatic_publication": False,
            "publication_rule": (
                "A autoria e todas as provas foram acrescentadas numa transação ADMIN com MFA; "
                "as fontes, versões e observações anteriores permanecem imutáveis."
            ),
        }
