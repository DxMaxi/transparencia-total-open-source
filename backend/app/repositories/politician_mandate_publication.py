"""Publicação transacional de um mandato parlamentar revisto por intervalo oficial."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialState,
    PoliticianMandatePublicationRequest,
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
from app.repositories.politician_mandate_editorial import (
    PoliticianMandateEditorialRepository,
    _reference_sha256,
)

_SUBJECT_TYPE = "PARLIAMENT_MANDATE_SITUATION"
_PROPOSAL_SCHEMA_VERSION = "politician-mandate-editorial-v1"
_PUBLICATION_SCHEMA_VERSION = "politician-mandate-publication-v1"
_OFFICE_TITLE = "Deputado à Assembleia da República"
_SUBJECT_PATTERN = re.compile(r"^(?P<observation>[A-Za-z0-9_-]{1,180}):(?P<ordinal>[1-9][0-9]*)$")


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


def _database_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise EditorialSourceError("A data oficial do mandato deixou de ser textual")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EditorialSourceError("A data oficial do mandato deixou de ser ISO-8601") from exc
    aware = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return aware.replace(tzinfo=None)


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


def _subject_parts(subject_id: object) -> tuple[str, int]:
    match = _SUBJECT_PATTERN.fullmatch(str(subject_id))
    if match is None:
        raise EditorialSourceError("A referência editorial do intervalo deixou de ser válida")
    ordinal = int(match.group("ordinal"))
    if ordinal > 10_000:
        raise EditorialSourceError("A posição do intervalo excede o limite editorial")
    return match.group("observation"), ordinal


def _integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EditorialSourceError(f"{label} deixou de ser um número inteiro")
    return value


def _publication_event_sha256(
    *,
    event_id: str,
    case_id: str,
    version_id: str,
    target_id: str,
    rationale: str,
    actor: StaffSession,
    created_at: datetime,
) -> str:
    return _sha256_json(
        {
            "id": event_id,
            "case_id": case_id,
            "version_id": version_id,
            "action": "PUBLISH",
            "target_type": "MANDATE",
            "target_id": target_id,
            "rationale": rationale,
            "actor_id": actor.staff_id,
            "actor_alias": actor.public_alias,
            "created_at": _iso_timestamp(created_at),
        }
    )


class PoliticianMandatePublicationRepository:
    """Publica um mandato ou reverte tudo, sem inferir pessoa, partido ou datas."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.candidates = PoliticianMandateEditorialRepository(pool)

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
            SELECT editorial_case.id,
                   editorial_case.subject_id,
                   editorial_case.source_document_id,
                   editorial_case.current_state::text AS current_state,
                   editorial_case.revision,
                   editorial_case.current_version_id,
                   version.normalized_data,
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
            raise EditorialNotFoundError("Processo editorial de mandato não encontrado")
        return cast(Mapping[str, Any], row)

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
                raise EditorialNotFoundError("Processo editorial de mandato não encontrado")
        case = await self._load_case(case_id=case_id, connection=connection, lock=lock)
        observation_id, period_ordinal = _subject_parts(case["subject_id"])
        normalized = _json_object(case["normalized_data"])
        mandate_candidate = normalized.get("mandate_candidate")
        if not isinstance(mandate_candidate, dict):
            raise EditorialSourceError("A versão aprovada perdeu o candidato a mandato")
        period_sha256 = mandate_candidate.get("source_period_sha256")
        if not isinstance(period_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", period_sha256):
            raise EditorialSourceError("A versão aprovada perdeu o SHA-256 do intervalo")

        candidate = await self.candidates.get_exact_candidate(
            observation_id=observation_id,
            source_period_sha256=period_sha256,
            connection=connection,
        )
        if candidate is None:
            raise EditorialSourceError(
                "O intervalo aprovado deixou de corresponder à fonte oficial atestada"
            )
        if (
            _integer(candidate["source_period_ordinal"], label="A posição do intervalo")
            != period_ordinal
        ):
            raise EditorialSourceError("A posição do intervalo deixou de coincidir com o processo")

        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        identity_lock_clause = "FOR UPDATE OF person, membership" if lock else ""
        identity = await database.fetchrow(
            f"""
            SELECT person.id AS person_id, person.role::text AS person_role,
                   person.active AS person_active,
                   membership.id AS membership_id,
                   membership.constituency AS membership_constituency,
                   membership.party_id AS membership_party_id
            FROM parliament_deputy_observations AS observation
            JOIN parliament_deputy_snapshots AS snapshot
              ON snapshot.id = observation.snapshot_id
            JOIN people AS person ON person.source_id = observation.source_id
            JOIN parliamentary_membership_snapshots AS membership
              ON membership.person_id = person.id
             AND membership.source_document_id = snapshot.source_document_id
             AND membership.legislature = snapshot.legislature
            WHERE observation.id = $1
              AND snapshot.source_document_id = $2
            {identity_lock_clause}
            """,
            observation_id,
            str(case["source_document_id"]),
        )
        if identity is None:
            raise EditorialSourceError("A identidade pública exata deixou de estar disponível")
        source_period = candidate["source_period"]
        source = candidate["source"]
        archive = candidate["archive"]
        assert isinstance(source_period, dict)
        assert isinstance(source, dict)
        assert isinstance(archive, dict)
        started_at = _database_timestamp(source_period["starts_at"])
        ended_at = (
            _database_timestamp(source_period["ends_at"])
            if source_period["ends_at"] is not None
            else None
        )
        person_id = str(identity["person_id"])
        existing = await database.fetchrow(
            """
            SELECT mandate.id, mandate.source_observation_id,
                   mandate.source_period_ordinal, mandate.source_period_sha256
            FROM mandates AS mandate
            WHERE (
                    mandate.source_observation_id = $1
                    AND mandate.source_period_ordinal = $2
                  )
               OR (
                    mandate.person_id = $3
                    AND mandate.office_title = $4
                    AND mandate.started_at = $5
                  )
            ORDER BY mandate.id
            LIMIT 1
            """,
            observation_id,
            period_ordinal,
            person_id,
            _OFFICE_TITLE,
            started_at,
        )
        if lock and connection is not None and existing is not None:
            await connection.fetch(
                "SELECT mandate.id FROM mandates AS mandate WHERE mandate.id = $1 FOR UPDATE",
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
            block(
                "LATEST_APPROVAL_INVALID",
                "A decisão atual não confirma esta versão e esta fonte.",
            )
        if normalized.get("schema_version") != _PROPOSAL_SCHEMA_VERSION:
            block("PROPOSAL_SCHEMA_INVALID", "A versão aprovada usa outro contrato editorial.")
        expected_normalized = self.candidates._normalized_proposal(candidate)
        if normalized != expected_normalized:
            block(
                "APPROVED_VERSION_DRIFT",
                "A versão aprovada diverge da prova oficial reconstruída no servidor.",
            )
        candidate_blockers = candidate["blocked_reasons"]
        assert isinstance(candidate_blockers, list)
        for detail in candidate_blockers:
            block("SOURCE_CANDIDATE_BLOCKED", str(detail))
        if str(case["source_document_id"]) != str(candidate["source_document_id"]):
            block("SOURCE_DOCUMENT_CHANGED", "O documento do processo deixou de coincidir.")
        if str(identity["person_role"]) != "DEPUTY" or identity["person_active"] is not True:
            block("PERSON_NOT_ACTIVE_DEPUTY", "O DepId está ligado a uma identidade incompatível.")
        constituency = candidate["constituency"]
        assert isinstance(constituency, dict)
        if str(identity["membership_constituency"] or "") != str(constituency["label"] or ""):
            block("CONSTITUENCY_CHANGED", "O círculo publicado diverge da observação oficial.")
        if identity["membership_party_id"] is not None:
            block(
                "PARTY_LINK_OUT_OF_SCOPE",
                "A fotografia contém uma filiação fora desta porta de mandato.",
            )
        if existing is not None:
            block(
                "MANDATE_ALREADY_EXISTS",
                "Já existe um mandato para este intervalo ou para o mesmo início oficial.",
            )

        public_effect = {
            "mandates_to_create": 1,
            "mandate_reviews_to_append": 1,
            "mandate_audits_to_append": 1,
            "editorial_decisions_to_append": 1,
            "publication_events_to_append": 1,
            "people_to_create": 0,
            "party_links_to_create": 0,
        }
        proof_payload = {
            "schema_version": _PUBLICATION_SCHEMA_VERSION,
            "case_reference_sha256": _reference_sha256(case_id),
            "version_reference_sha256": _reference_sha256(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "source_sha256": str(source["content_sha256"]),
            "observation_reference_sha256": _reference_sha256(observation_id),
            "person_reference_sha256": _reference_sha256(person_id),
            "source_period_ordinal": period_ordinal,
            "source_period_sha256": period_sha256,
            "office_title": _OFFICE_TITLE,
            "legislature": candidate["legislature"],
            "constituency": constituency["label"],
            "started_at": source_period["starts_at"],
            "ended_at": source_period["ends_at"],
            "public_effect": public_effect,
            "identity_rule": "EXACT_AR_DEP_ID_ONLY",
            "party_inference_allowed": False,
            "automatic_publication": False,
        }
        eligible = not blockers
        preview: dict[str, object] = {
            "case_id": case_id,
            "case_state": str(case["current_state"]),
            "case_revision": int(case["revision"]),
            "version_id": str(case["current_version_id"]),
            "version_sha256": str(case["normalized_sha256"]),
            "source_period_sha256": period_sha256,
            "source": source,
            "archive": archive,
            "proposed_mandate": {
                "office_title": _OFFICE_TITLE,
                "legislature": candidate["legislature"],
                "constituency": constituency["label"],
                "started_at": source_period["starts_at"],
                "ended_at": source_period["ends_at"],
                "party": "dados indisponíveis",
            },
            "identity": {
                "parliamentary_name": candidate["parliamentary_name"],
                "official_deputy_id": candidate["official_deputy_id"],
                "person_reference_sha256": _reference_sha256(person_id),
                "exact_match": True,
            },
            "source_observation_reference_sha256": _reference_sha256(observation_id),
            "source_period_ordinal": period_ordinal,
            "public_effect": public_effect,
            "publication_proof_sha256": _sha256_json(proof_payload) if eligible else None,
            "eligible": eligible,
            "blockers": blockers,
            "automatic_publication": False,
            "human_review_required": True,
            "party_inference_allowed": False,
            "withdrawal_required_before_real_activation": True,
            "publication_rule": (
                "A ação ADMIN volta a provar versão, fonte, arquivo, DepId e intervalo; "
                "mandato, revisão, auditoria, decisão e evento são acrescentados "
                "na mesma transação."
            ),
        }
        context: dict[str, object] = {
            "case": dict(case),
            "candidate": candidate,
            "normalized": normalized,
            "person_id": person_id,
            "observation_id": observation_id,
            "period_ordinal": period_ordinal,
            "started_at": started_at,
            "ended_at": ended_at,
        }
        return preview, context

    @staticmethod
    def _confirm_payload(
        *,
        case_id: str,
        preview: dict[str, object],
        payload: PoliticianMandatePublicationRequest,
    ) -> None:
        source = preview["source"]
        assert isinstance(source, dict)
        if case_id != payload.expected_case_id or str(preview["case_id"]) != case_id:
            raise EditorialConflictError("O pedido não confirma o processo indicado no URL")
        if str(preview["version_id"]) != payload.expected_version_id:
            raise EditorialConflictError("A versão editorial mudou antes da publicação")
        if str(preview["version_sha256"]) != payload.expected_version_sha256:
            raise EditorialConflictError("O SHA-256 da versão mudou antes da publicação")
        if str(source["content_sha256"]) != payload.expected_source_sha256:
            raise EditorialConflictError("O SHA-256 da fonte mudou antes da publicação")
        if str(preview["source_period_sha256"]) != payload.expected_period_sha256:
            raise EditorialConflictError("O SHA-256 do intervalo mudou antes da publicação")
        if str(preview["publication_proof_sha256"]) != payload.expected_publication_proof_sha256:
            raise EditorialConflictError("A prova de publicação deixou de coincidir")

    async def publish(
        self,
        *,
        case_id: str,
        payload: PoliticianMandatePublicationRequest,
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
                    f"politician-mandate-publication:{case_id}",
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
                assert isinstance(case, dict)
                assert isinstance(candidate, dict)
                constituency = candidate["constituency"]
                source = candidate["source"]
                assert isinstance(constituency, dict)
                assert isinstance(source, dict)

                mandate_id = _new_id("mandate")
                await connection.execute(
                    """
                    INSERT INTO mandates
                        (id, person_id, party_id, legislature, office_title,
                         constituency, started_at, ended_at, source_document_id,
                         source_observation_id, source_period_ordinal,
                         source_period_sha256, created_at, updated_at)
                    VALUES ($1, $2, NULL, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $12)
                    """,
                    mandate_id,
                    str(context["person_id"]),
                    str(candidate["legislature"]),
                    _OFFICE_TITLE,
                    str(constituency["label"]),
                    context["started_at"],
                    context["ended_at"],
                    str(candidate["source_document_id"]),
                    str(context["observation_id"]),
                    _integer(context["period_ordinal"], label="A posição do intervalo"),
                    str(candidate["source_period_sha256"]),
                    created_at,
                )

                review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'MANDATE', $2,
                            'Mandato parlamentar factual para fiscalização democrática',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'DepId, período, círculo, fonte e arquivo foram revistos por pessoa.',
                            'Publica só o mandato provado; não infere filiação ou outros cargos.',
                            TRUE, $3, $4, $5)
                    """,
                    review_id,
                    mandate_id,
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
                    VALUES ($1, 'MANDATE', $2, 'PUBLISHED', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    audit_id,
                    mandate_id,
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
                            "source_period_sha256": payload.expected_period_sha256,
                            "observation_reference_sha256": _reference_sha256(
                                context["observation_id"]
                            ),
                            "official_deputy_id_reference_sha256": _reference_sha256(
                                candidate["official_deputy_id"]
                            ),
                            "party_link_created": False,
                            "publication_proof_sha256": payload.expected_publication_proof_sha256,
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
                    target_id=mandate_id,
                    rationale=payload.public_rationale,
                    actor=actor,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    INSERT INTO editorial_publication_events
                        (id, case_id, version_id, action, target_type, target_id,
                         rationale, actor_id, actor_alias, event_sha256, created_at)
                    VALUES ($1, $2, $3, 'PUBLISH'::"EditorialPublicationAction",
                            'MANDATE', $4, $5, $6, $7, $8, $9)
                    """,
                    event_id,
                    case_id,
                    version_id,
                    mandate_id,
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
                        FROM mandates AS mandate
                        JOIN source_documents AS source
                          ON source.id = mandate.source_document_id
                        JOIN parliament_deputy_observations AS observation
                          ON observation.id = mandate.source_observation_id
                        JOIN parliament_deputy_snapshots AS snapshot
                          ON snapshot.id = observation.snapshot_id
                         AND snapshot.source_document_id = source.id
                         AND snapshot.legislature = mandate.legislature
                        JOIN people AS person
                          ON person.id = mandate.person_id
                         AND person.source_id = observation.source_id
                         AND person.role = 'DEPUTY'
                         AND person.active = TRUE
                        JOIN parliamentary_membership_snapshots AS membership
                          ON membership.person_id = person.id
                         AND membership.source_document_id = source.id
                         AND membership.legislature = mandate.legislature
                         AND membership.constituency = mandate.constituency
                        JOIN LATERAL (
                            SELECT review.publishable
                            FROM data_publication_reviews AS review
                            WHERE review.entity_type = 'PERSON'
                              AND review.entity_id = person.id
                              AND review.source_document_id = source.id
                            ORDER BY review.reviewed_at DESC, review.id DESC
                            LIMIT 1
                        ) AS latest_person_review
                          ON latest_person_review.publishable = TRUE
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
                          AND mandate.source_observation_id = $2
                          AND mandate.source_period_ordinal = $3
                          AND mandate.source_period_sha256 = $4
                          AND source.publisher = 'PARLIAMENT'
                          AND source.kind <> 'NEWS_ARTICLE'
                          AND EXISTS (
                              SELECT 1
                              FROM source_archive_attestations AS attestation
                              WHERE attestation.source_document_id = source.id
                                AND attestation.content_sha256 = source.content_sha256
                                AND attestation.retrieval_url = source.url
                                AND attestation.retrieved_at = source.retrieved_at
                          )
                    )
                    """,
                    mandate_id,
                    str(context["observation_id"]),
                    _integer(context["period_ordinal"], label="A posição do intervalo"),
                    str(candidate["source_period_sha256"]),
                )
                if public_gate is not True:
                    raise EditorialSourceError(
                        "A projeção pública não satisfez a prova exata e foi revertida"
                    )
        except asyncpg.IntegrityConstraintViolationError as exc:
            raise EditorialConflictError(
                "O processo, a identidade ou o intervalo mudou; nada foi publicado"
            ) from exc

        return {
            "created": True,
            "case_id": case_id,
            "version_id": payload.expected_version_id,
            "state": EditorialState.PUBLISHED.value,
            "mandate_id": mandate_id,
            "mandate_review_id": review_id,
            "audit_event_id": audit_id,
            "editorial_decision_id": decision_id,
            "publication_event_id": event_id,
            "source_sha256": payload.expected_source_sha256,
            "source_period_sha256": payload.expected_period_sha256,
            "publication_proof_sha256": payload.expected_publication_proof_sha256,
            "party_link_created": False,
            "automatic_publication": False,
            "publication_rule": (
                "O mandato e toda a prova foram acrescentados numa transação ADMIN com MFA; "
                "a fonte, as versões e o histórico anterior permanecem imutáveis."
            ),
        }
