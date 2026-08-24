"""Publicação transacional de uma fotografia completa de perfis políticos."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialState,
    PoliticianProfileSnapshotPublicationRequest,
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
from app.repositories.politician_profile_publication import (
    PoliticianProfilePublicationReadinessRepository,
)

_PUBLICATION_SCHEMA_VERSION = "politician-profile-snapshot-publication-v1"


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
    return value.isoformat(timespec="milliseconds") + "Z"


def _profile_slug(source_id: str) -> str:
    return f"deputado-{hashlib.sha256(source_id.encode('utf-8')).hexdigest()[:20]}"


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
            "target_type": "PERSON",
            "target_id": target_id,
            "rationale": rationale,
            "actor_id": actor.staff_id,
            "actor_alias": actor.public_alias,
            "created_at": _iso_timestamp(created_at),
        }
    )


class PoliticianProfileSnapshotPublicationRepository:
    """Publica todos os perfis aprovados ou nenhum, sempre por ``DepId`` exato."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)
        self.readiness = PoliticianProfilePublicationReadinessRepository(pool)

    async def inspect(self, *, snapshot_id: str) -> dict[str, object]:
        readiness = await self.readiness.inspect(snapshot_id=snapshot_id)
        return self._preview(readiness)

    @staticmethod
    def _preview(readiness: dict[str, object]) -> dict[str, object]:
        manifest_counts = readiness["manifest_counts"]
        identity_projection = readiness["identity_projection"]
        source = readiness["source"]
        raw_blockers = readiness["blockers"]
        assert isinstance(manifest_counts, dict)
        assert isinstance(identity_projection, dict)
        assert isinstance(source, dict)
        assert isinstance(raw_blockers, list)
        blockers = list(raw_blockers)
        readiness_proof = readiness["readiness_proof_sha256"]
        deputy_count = int(manifest_counts["deputies"])
        existing_memberships = int(identity_projection["existing_memberships"])
        public_effect = {
            "people_to_create": int(identity_projection["new_people_required"]),
            "people_to_reuse_by_exact_depid": int(identity_projection["exact_existing_people"]),
            "memberships_to_create": deputy_count - existing_memberships,
            "memberships_to_reuse": existing_memberships,
            "person_reviews_to_append": deputy_count,
            "cases_to_publish": deputy_count,
            "mandates_to_create": 0,
            "party_links_to_create": 0,
        }
        proof_payload = {
            "schema_version": _PUBLICATION_SCHEMA_VERSION,
            "snapshot_reference_sha256": _reference_sha256(readiness["snapshot_id"]),
            "readiness_proof_sha256": readiness_proof,
            "source_sha256": source["content_sha256"],
            "snapshot_sha256": readiness["normalised_sha256"],
            "deputy_count": deputy_count,
            "public_effect": public_effect,
            "identity_rule": "EXACT_AR_DEP_ID_ONLY",
            "mandate_inference_allowed": False,
            "party_inference_allowed": False,
        }
        eligible = readiness["eligible"] is True and readiness_proof is not None and not blockers
        return {
            "snapshot_id": readiness["snapshot_id"],
            "legislature": readiness["legislature"],
            "parser_version": readiness["parser_version"],
            "normalised_sha256": readiness["normalised_sha256"],
            "collected_at": readiness["collected_at"],
            "source": source,
            "archive": readiness["archive"],
            "manifest_counts": manifest_counts,
            "materialised_counts": readiness["materialised_counts"],
            "editorial_counts": readiness["editorial_counts"],
            "identity_projection": identity_projection,
            "readiness_proof_sha256": readiness_proof,
            "publication_proof_sha256": _sha256_json(proof_payload) if eligible else None,
            "public_effect": public_effect,
            "eligible": eligible,
            "blockers": blockers,
            "automatic_publication": False,
            "mandate_inference_allowed": False,
            "party_inference_allowed": False,
            "publication_rule": (
                "A ação ADMIN volta a provar e bloqueia a fotografia inteira; pessoas, pertenças, "
                "revisões, auditoria, decisões e eventos são acrescentados numa só transação."
            ),
        }

    @staticmethod
    def _confirm_payload(
        *,
        preview: dict[str, object],
        payload: PoliticianProfileSnapshotPublicationRequest,
    ) -> None:
        source = preview["source"]
        manifest_counts = preview["manifest_counts"]
        assert isinstance(source, dict)
        assert isinstance(manifest_counts, dict)
        if str(preview["snapshot_id"]) != payload.expected_snapshot_id:
            raise EditorialConflictError("A fotografia confirmada já não é a fotografia atual")
        if str(source["content_sha256"]) != payload.expected_source_sha256:
            raise EditorialConflictError("O SHA-256 da fonte mudou antes da publicação")
        if str(preview["normalised_sha256"]) != payload.expected_snapshot_sha256:
            raise EditorialConflictError("O SHA-256 normalizado mudou antes da publicação")
        if (
            str(preview["readiness_proof_sha256"]) != payload.expected_readiness_proof_sha256
            or str(preview["publication_proof_sha256"]) != payload.expected_publication_proof_sha256
            or int(manifest_counts["deputies"]) != payload.expected_deputy_count
        ):
            raise EditorialConflictError("A prova ou a contagem da fotografia deixou de coincidir")

    async def publish(
        self,
        *,
        snapshot_id: str,
        payload: PoliticianProfileSnapshotPublicationRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError("Esta publicação exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError("A publicação exige autenticação multifator")
        if snapshot_id != payload.expected_snapshot_id:
            raise EditorialConflictError("O pedido não confirma a fotografia indicada no URL")

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"politician-profile-snapshot-publication:{snapshot_id}",
                )
                locked_snapshot = await connection.fetchrow(
                    """
                    SELECT snapshot.id, snapshot.source_document_id,
                           snapshot.legislature, snapshot.collected_at
                    FROM parliament_deputy_snapshots AS snapshot
                    JOIN source_documents AS source
                      ON source.id = snapshot.source_document_id
                    WHERE snapshot.id = $1
                    FOR UPDATE OF snapshot, source
                    """,
                    snapshot_id,
                )
                if locked_snapshot is None:
                    raise EditorialNotFoundError("Fotografia privada de deputados não encontrada")
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"parliament-people-publication:{locked_snapshot['legislature']}",
                )

                locked_cases = await connection.fetch(
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

                readiness = await self.readiness.inspect(
                    snapshot_id=snapshot_id,
                    connection=connection,
                )
                preview = self._preview(readiness)
                self._confirm_payload(preview=preview, payload=payload)
                blockers = preview["blockers"]
                assert isinstance(blockers, list)
                if blockers:
                    details = "; ".join(str(item["detail"]) for item in blockers)
                    raise EditorialSourceError(details)
                manifest_counts = preview["manifest_counts"]
                assert isinstance(manifest_counts, dict)
                deputy_count = int(manifest_counts["deputies"])
                if len(locked_cases) != deputy_count:
                    raise EditorialConflictError(
                        "O conjunto completo de processos mudou durante a confirmação"
                    )

                rows = await connection.fetch(
                    """
                    SELECT observation.id AS observation_id,
                           observation.source_id,
                           observation.parliamentary_name,
                           observation.full_name,
                           observation.constituency_label,
                           editorial_case.id AS case_id,
                           editorial_case.current_state::text AS case_state,
                           editorial_case.revision AS case_revision,
                           editorial_case.current_version_id,
                           person.id AS person_id,
                           person.role::text AS person_role,
                           person.active AS person_active,
                           person.slug AS person_slug,
                           membership.id AS membership_id,
                           membership.parliamentary_name AS membership_parliamentary_name,
                           membership.full_name AS membership_full_name,
                           membership.party_id AS membership_party_id,
                           membership.constituency AS membership_constituency,
                           membership.observed_at AS membership_observed_at
                    FROM parliament_deputy_observations AS observation
                    JOIN parliament_deputy_snapshots AS snapshot
                      ON snapshot.id = observation.snapshot_id
                    JOIN editorial_cases AS editorial_case
                      ON editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
                     AND editorial_case.subject_type = 'PARLIAMENT_DEPUTY_OBSERVATION'
                     AND editorial_case.subject_id = observation.id
                     AND editorial_case.source_document_id = snapshot.source_document_id
                    LEFT JOIN people AS person ON person.source_id = observation.source_id
                    LEFT JOIN parliamentary_membership_snapshots AS membership
                      ON membership.person_id = person.id
                     AND membership.legislature = snapshot.legislature
                     AND membership.source_document_id = snapshot.source_document_id
                    WHERE observation.snapshot_id = $1
                    ORDER BY observation.source_id COLLATE "C", observation.id
                    """,
                    snapshot_id,
                )
                if len(rows) != deputy_count:
                    raise EditorialConflictError(
                        "A fotografia deixou de conter o número confirmado de perfis"
                    )

                created_at = await connection.fetchval(
                    "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
                )
                if not isinstance(created_at, datetime):
                    raise RuntimeError("Não foi possível obter o relógio transacional")

                source_document_id = str(locked_snapshot["source_document_id"])
                legislature = str(locked_snapshot["legislature"])
                observed_at = locked_snapshot["collected_at"]
                people_created = 0
                memberships_created = 0
                person_review_ids: list[str] = []
                person_audit_ids: list[str] = []
                decision_ids: list[str] = []
                publication_event_ids: list[str] = []

                for row in rows:
                    if str(row["case_state"]) != EditorialState.APPROVED.value:
                        raise EditorialConflictError(
                            "Um perfil deixou de estar aprovado durante a publicação"
                        )
                    version_id = str(row["current_version_id"] or "")
                    if not version_id:
                        raise EditorialSourceError("Um perfil aprovado perdeu a versão atual")

                    person_id = str(row["person_id"] or "")
                    person_existed = bool(person_id)
                    if person_existed:
                        if str(row["person_role"]) != "DEPUTY" or row["person_active"] is not True:
                            raise EditorialSourceError(
                                "Um DepId exato está ligado a uma identidade incompatível"
                            )
                    else:
                        person_id = _new_id("person")
                        await connection.execute(
                            """
                            INSERT INTO people
                                (id, source_id, full_name, parliamentary_name, slug,
                                 role, active, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5, 'DEPUTY', TRUE, $6, $6)
                            """,
                            person_id,
                            str(row["source_id"]),
                            str(row["full_name"] or row["parliamentary_name"]),
                            str(row["parliamentary_name"]),
                            _profile_slug(str(row["source_id"])),
                            created_at,
                        )
                        people_created += 1

                    membership_id = str(row["membership_id"] or "")
                    membership_existed = bool(membership_id)
                    if membership_existed:
                        expected_membership = (
                            str(row["parliamentary_name"]),
                            row["full_name"],
                            row["constituency_label"],
                            observed_at,
                        )
                        current_membership = (
                            str(row["membership_parliamentary_name"] or ""),
                            row["membership_full_name"],
                            row["membership_constituency"],
                            row["membership_observed_at"],
                        )
                        if row["membership_party_id"] is not None:
                            raise EditorialSourceError(
                                "Uma pertença antiga contém filiação não provada por GpId"
                            )
                        if current_membership != expected_membership:
                            raise EditorialSourceError(
                                "Uma pertença existente diverge da fotografia oficial exata"
                            )
                    else:
                        membership_id = _new_id("membership")
                        await connection.execute(
                            """
                            INSERT INTO parliamentary_membership_snapshots
                                (id, person_id, parliamentary_name, full_name, party_id,
                                 legislature, constituency, observed_at, source_document_id)
                            VALUES ($1, $2, $3, $4, NULL, $5, $6, $7, $8)
                            """,
                            membership_id,
                            person_id,
                            str(row["parliamentary_name"]),
                            row["full_name"],
                            legislature,
                            row["constituency_label"],
                            observed_at,
                            source_document_id,
                        )
                        memberships_created += 1

                    review_id = _new_id("publication_review")
                    await connection.execute(
                        """
                        INSERT INTO data_publication_reviews
                            (id, entity_type, entity_id, purpose, legal_basis,
                             sensitivity, necessity_assessment, proportionality_test,
                             publishable, source_document_id, reviewed_by, reviewed_at)
                        VALUES ($1, 'PERSON', $2,
                                'Identidade parlamentar factual para fiscalização democrática',
                                'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                                'DepId, nome observado, fonte, arquivo e fotografia foram '
                                'revistos.',
                                'Publica apenas identidade e observação; não cria mandato ou '
                                'filiação.',
                                TRUE, $3, $4, $5)
                        """,
                        review_id,
                        person_id,
                        source_document_id,
                        actor.public_alias,
                        created_at,
                    )
                    person_review_ids.append(review_id)

                    person_audit_id = _new_id("audit")
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'PERSON', $2, 'PUBLISHED', $3,
                                $4::jsonb, $5::jsonb, $6, $7)
                        """,
                        person_audit_id,
                        person_id,
                        actor.public_alias,
                        _canonical_json(
                            {
                                "person_existed": person_existed,
                                "membership_existed": membership_existed,
                            }
                        ),
                        _canonical_json(
                            {
                                "publishable": True,
                                "snapshot_reference_sha256": _reference_sha256(snapshot_id),
                                "source_sha256": payload.expected_source_sha256,
                                "official_deputy_id_reference_sha256": _reference_sha256(
                                    row["source_id"]
                                ),
                                "mandate_created": False,
                                "party_link_created": False,
                            }
                        ),
                        payload.public_rationale,
                        created_at,
                    )
                    person_audit_ids.append(person_audit_id)

                    case_id = str(row["case_id"])
                    next_revision = int(row["case_revision"]) + 1
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
                    decision_ids.append(decision_id)

                    event_id = _new_id("editorial_publication")
                    event_sha256 = _publication_event_sha256(
                        event_id=event_id,
                        case_id=case_id,
                        version_id=version_id,
                        target_id=person_id,
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
                                'PERSON', $4, $5, $6, $7, $8, $9)
                        """,
                        event_id,
                        case_id,
                        version_id,
                        person_id,
                        payload.public_rationale,
                        actor.staff_id,
                        actor.public_alias,
                        event_sha256,
                        created_at,
                    )
                    publication_event_ids.append(event_id)

                public_shape = await connection.fetchrow(
                    """
                    SELECT COUNT(*)::int AS memberships,
                           COUNT(DISTINCT membership.person_id)::int AS people,
                           COUNT(*) FILTER (WHERE membership.party_id IS NOT NULL)::int
                               AS party_links
                    FROM parliamentary_membership_snapshots AS membership
                    WHERE membership.source_document_id = $1
                      AND membership.legislature = $2
                    """,
                    source_document_id,
                    legislature,
                )
                if public_shape is None or (
                    int(public_shape["memberships"]) != deputy_count
                    or int(public_shape["people"]) != deputy_count
                    or int(public_shape["party_links"]) != 0
                ):
                    raise EditorialSourceError(
                        "A projeção pública não coincide com a fotografia inteira e foi revertida"
                    )

                snapshot_review_id = _new_id("publication_review")
                await connection.execute(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis,
                         sensitivity, necessity_assessment, proportionality_test,
                         publishable, source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'PARLIAMENT_DEPUTY_SNAPSHOT', $2,
                            'Fotografia integral de identidade parlamentar revista',
                            'PUBLIC_INTEREST', 'PUBLIC_OFFICIAL',
                            'Manifesto, arquivo e todos os perfis foram revistos em conjunto.',
                            'A projeção exclui mandatos, filiações e relações não demonstradas.',
                            TRUE, $3, $4, $5)
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
                    VALUES ($1, 'PARLIAMENT_DEPUTY_SNAPSHOT', $2, 'PUBLISHED', $3,
                            $4::jsonb, $5::jsonb, $6, $7)
                    """,
                    snapshot_audit_id,
                    snapshot_id,
                    actor.public_alias,
                    _canonical_json(
                        {
                            "readiness_proof_sha256": payload.expected_readiness_proof_sha256,
                            "publishable": False,
                        }
                    ),
                    _canonical_json(
                        {
                            "publication_proof_sha256": (payload.expected_publication_proof_sha256),
                            "publishable": True,
                            "deputy_count": deputy_count,
                            "people_created": people_created,
                            "memberships_created": memberships_created,
                            "mandates_created": 0,
                            "party_links_created": 0,
                        }
                    ),
                    payload.public_rationale,
                    created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError(
                "A fotografia ou uma identidade mudou durante a publicação; nada foi publicado"
            ) from exc

        return {
            "created": True,
            "snapshot_id": snapshot_id,
            "legislature": legislature,
            "state": EditorialState.PUBLISHED.value,
            "deputy_count": deputy_count,
            "people_created": people_created,
            "people_reused": deputy_count - people_created,
            "memberships_created": memberships_created,
            "memberships_reused": deputy_count - memberships_created,
            "person_reviews_created": len(person_review_ids),
            "person_audits_created": len(person_audit_ids),
            "editorial_decisions_created": len(decision_ids),
            "publication_events_created": len(publication_event_ids),
            "snapshot_review_id": snapshot_review_id,
            "snapshot_audit_id": snapshot_audit_id,
            "readiness_proof_sha256": payload.expected_readiness_proof_sha256,
            "publication_proof_sha256": payload.expected_publication_proof_sha256,
            "mandates_created": 0,
            "party_links_created": 0,
            "publication_rule": (
                "A fotografia inteira foi publicada numa só transação por DepId exato; "
                "nenhum mandato ou vínculo partidário foi inferido."
            ),
        }
