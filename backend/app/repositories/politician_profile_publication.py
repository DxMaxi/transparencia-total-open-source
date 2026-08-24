"""Porta privada e read-only de prontidão para publicar perfis políticos."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import asyncpg

from app.repositories.editorial import EditorialNotFoundError, EditorialSourceError
from app.repositories.politician_profile_editorial import (
    PoliticianProfileEditorialRepository,
    _canonical_json,
    _reference_sha256,
)

_READINESS_SCHEMA_VERSION = "politician-profile-publication-readiness-v2"
_SUBJECT_TYPE = "PARLIAMENT_DEPUTY_OBSERVATION"
_PROFILE_SCHEMA_VERSION = "politician-profile-editorial-v1"
_EDITORIAL_STATES = (
    "MISSING",
    "PENDING",
    "IN_REVIEW",
    "APPROVED",
    "REJECTED",
    "PUBLISHED",
    "WITHDRAWN",
)


@asynccontextmanager
async def _read_connection(
    pool: asyncpg.Pool,
    connection: asyncpg.Connection | None,
) -> AsyncIterator[asyncpg.Connection]:
    if connection is not None:
        yield connection
        return
    async with pool.acquire() as acquired:
        yield acquired


def _json_object(value: object) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise ValueError("A versão editorial deixou de ser um objeto JSON")
    return dict(decoded)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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


class PoliticianProfilePublicationReadinessRepository:
    """Só inspeciona; nunca cria pessoas, revisões ou eventos de publicação."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.profile_editorial = PoliticianProfileEditorialRepository(pool)

    async def list_snapshots(
        self,
        *,
        legislature: str | None,
        limit: int,
    ) -> dict[str, object]:
        conditions: list[str] = []
        arguments: list[object] = []
        normalised_legislature = legislature.strip() if legislature else ""
        if normalised_legislature:
            arguments.append(normalised_legislature)
            conditions.append(f"snapshot.legislature = ${len(arguments)}")
        arguments.append(limit)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await self.pool.fetch(
            f"""
            SELECT snapshot.id
            FROM parliament_deputy_snapshots AS snapshot
            {where_clause}
            ORDER BY snapshot.collected_at DESC, snapshot.created_at DESC, snapshot.id DESC
            LIMIT ${len(arguments)}
            """,
            *arguments,
        )
        items = [await self.inspect(snapshot_id=str(row["id"])) for row in rows]
        return {
            "items": items,
            "limit": limit,
            "publication_performed": False,
            "readiness_rule": (
                "A lista é uma inspeção privada: só uma fotografia inteira, aprovada e "
                "reconstruída sem divergências pode ficar pronta para uma futura publicação."
            ),
        }

    async def inspect(
        self,
        *,
        snapshot_id: str,
        connection: asyncpg.Connection | None = None,
    ) -> dict[str, object]:
        async with _read_connection(self.pool, connection) as read_connection:
            snapshot = await read_connection.fetchrow(
                """
                SELECT
                    snapshot.id,
                    snapshot.source_document_id,
                    snapshot.legislature,
                    snapshot.parser_version,
                    snapshot.normalised_sha256,
                    snapshot.collected_at,
                    snapshot.deputy_count,
                    snapshot.group_period_count,
                    snapshot.situation_period_count,
                    snapshot.office_period_count,
                    source.publisher::text AS source_publisher,
                    source.kind::text AS source_kind,
                    source.title AS source_title,
                    source.official_identifier,
                    source.url AS source_url,
                    source.retrieved_at AS source_retrieved_at,
                    source.content_sha256 AS source_sha256,
                    source.mime_type AS source_mime_type,
                    archive.id AS archive_id,
                    archive.storage_backend,
                    archive.byte_size,
                    archive.archived_at,
                    archive.attestation_sha256,
                    materialised.deputy_count AS materialised_deputy_count,
                    materialised.group_period_count AS materialised_group_period_count,
                    materialised.situation_period_count AS materialised_situation_period_count,
                    materialised.office_period_count AS materialised_office_period_count
                FROM parliament_deputy_snapshots AS snapshot
                JOIN source_documents AS source ON source.id = snapshot.source_document_id
                LEFT JOIN LATERAL (
                    SELECT attestation.id, attestation.storage_backend,
                           attestation.byte_size, attestation.archived_at,
                           attestation.attestation_sha256
                    FROM source_archive_attestations AS attestation
                    WHERE attestation.source_document_id = source.id
                      AND attestation.content_sha256 = source.content_sha256
                      AND attestation.retrieval_url = source.url
                      AND attestation.retrieved_at = source.retrieved_at
                    ORDER BY attestation.archived_at ASC, attestation.id ASC
                    LIMIT 1
                ) AS archive ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS deputy_count,
                           COALESCE(
                               SUM(jsonb_array_length(observation.parliamentary_groups)), 0
                           )::int
                               AS group_period_count,
                           COALESCE(SUM(jsonb_array_length(observation.mandate_situations)), 0)::int
                               AS situation_period_count,
                           COALESCE(SUM(jsonb_array_length(observation.offices)), 0)::int
                               AS office_period_count
                    FROM parliament_deputy_observations AS observation
                    WHERE observation.snapshot_id = snapshot.id
                ) AS materialised ON TRUE
                WHERE snapshot.id = $1
                """,
                snapshot_id,
            )
            if snapshot is None:
                raise EditorialNotFoundError("Fotografia privada de deputados não encontrada")

            rows = await read_connection.fetch(
                """
                SELECT
                    observation.id AS observation_id,
                    observation.source_id,
                    person.id AS person_id,
                    person.role::text AS person_role,
                    person.active AS person_active,
                    membership.id AS membership_id,
                    membership.party_id AS membership_party_id,
                    latest_person_review.publishable AS latest_person_publishable,
                    editorial_case.id AS case_id,
                    editorial_case.current_state::text AS case_state,
                    editorial_case.revision AS case_revision,
                    editorial_case.origin::text AS case_origin,
                    editorial_case.current_version_id,
                    version.normalized_json,
                    version.normalized_sha256,
                    latest_decision.action::text AS latest_decision_action,
                    latest_decision.resulting_state::text AS latest_decision_state,
                    latest_decision.source_confirmed AS latest_source_confirmed,
                    latest_decision.version_id AS latest_decision_version_id,
                    latest_decision.case_revision AS latest_decision_revision,
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
                LEFT JOIN LATERAL (
                    SELECT review.publishable
                    FROM data_publication_reviews AS review
                    WHERE review.entity_type = 'PERSON'
                      AND review.entity_id = person.id
                      AND review.source_document_id = snapshot.source_document_id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) AS latest_person_review ON TRUE
                LEFT JOIN editorial_cases AS editorial_case
                  ON editorial_case.kind = 'POLITICIAN_PROFILE'::"EditorialCaseKind"
                 AND editorial_case.subject_type = 'PARLIAMENT_DEPUTY_OBSERVATION'
                 AND editorial_case.subject_id = observation.id
                 AND editorial_case.source_document_id = snapshot.source_document_id
                LEFT JOIN editorial_versions AS version
                  ON version.id = editorial_case.current_version_id
                LEFT JOIN LATERAL (
                    SELECT decision.action, decision.resulting_state,
                           decision.source_confirmed, decision.version_id,
                           decision.case_revision
                    FROM editorial_decisions AS decision
                    WHERE decision.case_id = editorial_case.id
                    ORDER BY decision.case_revision DESC, decision.created_at DESC,
                             decision.id DESC
                    LIMIT 1
                ) AS latest_decision ON TRUE
                WHERE observation.snapshot_id = $1
                ORDER BY observation.source_id COLLATE "C", observation.id
                """,
                snapshot_id,
            )

        blocker_counts: dict[str, dict[str, object]] = {}

        def block(code: str, detail: str, count: int = 1) -> None:
            current = blocker_counts.get(code)
            if current is None:
                blocker_counts[code] = {"code": code, "detail": detail, "count": count}
            else:
                current["count"] = int(str(current["count"])) + count

        source_sha256 = str(snapshot["source_sha256"])
        normalised_sha256 = str(snapshot["normalised_sha256"])
        if str(snapshot["source_publisher"]) != "PARLIAMENT":
            block("SOURCE_NOT_PARLIAMENT", "A fonte deixou de estar identificada como Parlamento.")
        if str(snapshot["source_kind"]) == "NEWS_ARTICLE":
            block("SOURCE_KIND_NOT_ALLOWED", "Uma notícia não pode provar um perfil político.")
        if not _https_url(snapshot["source_url"]):
            block("SOURCE_URL_INVALID", "A fonte oficial não possui um URL HTTPS público válido.")
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
            block("SOURCE_SHA256_INVALID", "O SHA-256 dos bytes oficiais é inválido.")
        if not re.fullmatch(r"[0-9a-f]{64}", normalised_sha256):
            block("SNAPSHOT_SHA256_INVALID", "O SHA-256 normalizado é inválido.")
        archive_attested = snapshot["archive_id"] is not None
        if not archive_attested:
            block(
                "ARCHIVE_ATTESTATION_MISSING",
                "O documento não tem uma atestação que coincida em URL, data e SHA-256.",
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
        manifest_matches = manifest_counts == materialised_counts
        if not manifest_matches:
            block(
                "MANIFEST_MISMATCH",
                "As contagens materializadas divergem do manifesto imutável da fotografia.",
            )
        if manifest_counts["deputies"] == 0:
            block("EMPTY_SNAPSHOT", "Uma fotografia vazia nunca pode ficar pronta para publicação.")
        if len(rows) != materialised_counts["deputies"]:
            block(
                "OBSERVATION_SET_INCOMPLETE",
                "A inspeção não recuperou exatamente todas as observações materializadas.",
            )
        source_ids = [str(row["source_id"] or "").strip() for row in rows]
        if not all(source_ids) or len(set(source_ids)) != len(source_ids):
            block(
                "EXACT_IDENTIFIER_SET_INVALID",
                "Existem DepId oficiais ausentes ou repetidos na fotografia.",
            )

        candidates: list[dict[str, object]] = []
        if archive_attested and manifest_matches:
            try:
                candidates = await self.profile_editorial.snapshot_candidates(
                    snapshot_id=snapshot_id,
                    connection=connection,
                )
            except EditorialSourceError:
                block(
                    "CANDIDATE_RECONSTRUCTION_FAILED",
                    "A fotografia inteira não pôde ser reconstruída pelo adaptador editorial.",
                )
        candidate_by_observation = {
            str(candidate["observation_id"]): candidate for candidate in candidates
        }
        if len(candidate_by_observation) != len(rows):
            block(
                "CANDIDATE_SET_INCOMPLETE",
                "Nem todas as observações têm uma reconstrução editorial exata.",
            )

        state_counter: Counter[str] = Counter()
        proof_entries: list[dict[str, str]] = []
        exact_people = 0
        new_people = 0
        existing_memberships = 0
        existing_party_links = 0
        legacy_review_decisions = 0
        legacy_positive_reviews = 0

        for row in rows:
            observation_id = str(row["observation_id"])
            case_id = row["case_id"]
            state = str(row["case_state"]) if case_id is not None else "MISSING"
            state_counter[state] += 1

            if row["person_id"] is None:
                new_people += 1
            else:
                exact_people += 1
                if str(row["person_role"]) != "DEPUTY":
                    block(
                        "EXACT_PERSON_ROLE_CONFLICT",
                        "Um DepId exato já está ligado a uma pessoa com função incompatível.",
                    )
                if row["person_active"] is not True:
                    block(
                        "EXACT_PERSON_INACTIVE",
                        "Um DepId exato já está ligado a uma identidade inativa.",
                    )
            if row["membership_id"] is not None:
                existing_memberships += 1
            if row["membership_party_id"] is not None:
                existing_party_links += 1
                block(
                    "UNVERIFIED_EXISTING_PARTY_LINK",
                    "Uma pertença antiga contém uma ligação partidária sem GpId verificável.",
                )
            if row["latest_person_publishable"] is not None:
                legacy_review_decisions += 1
            if row["latest_person_publishable"] is True:
                legacy_positive_reviews += 1

            if case_id is None:
                block(
                    "EDITORIAL_CASE_MISSING",
                    "Há observações que ainda não entraram no circuito editorial privado.",
                )
                continue
            if str(row["case_origin"]) != "INGESTION":
                block(
                    "EDITORIAL_ORIGIN_INVALID",
                    "Um processo não conserva a origem de ingestão esperada.",
                )
            if state != "APPROVED":
                block(
                    "EDITORIAL_STATE_NOT_APPROVED",
                    "Há processos que ainda não têm aprovação humana privada.",
                )

            current_version_id = row["current_version_id"]
            if current_version_id is None or row["normalized_json"] is None:
                block(
                    "EDITORIAL_VERSION_MISSING",
                    "Um processo não tem uma versão editorial atual verificável.",
                )
                continue
            try:
                normalized = _json_object(row["normalized_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                block(
                    "EDITORIAL_VERSION_INVALID",
                    "Uma versão editorial atual deixou de ser JSON válido.",
                )
                continue
            stored_version_sha256 = str(row["normalized_sha256"] or "")
            if (
                not re.fullmatch(r"[0-9a-f]{64}", stored_version_sha256)
                or _sha256_json(normalized) != stored_version_sha256
            ):
                block(
                    "EDITORIAL_VERSION_HASH_MISMATCH",
                    "O conteúdo editorial atual não coincide com o respetivo SHA-256.",
                )

            candidate = candidate_by_observation.get(observation_id)
            if candidate is None or candidate.get("proposal_eligible") is not True:
                block(
                    "EDITORIAL_PROOF_UNAVAILABLE",
                    "Uma versão não pode ser comparada com a observação oficial exata.",
                )
            else:
                expected_normalized = self.profile_editorial._normalized_proposal(candidate)
                if normalized != expected_normalized:
                    block(
                        "EDITORIAL_PROOF_DIVERGED",
                        "Uma versão aprovada diverge da reconstrução determinística da fonte.",
                    )
                if normalized.get("schema_version") != _PROFILE_SCHEMA_VERSION:
                    block(
                        "EDITORIAL_SCHEMA_INVALID",
                        "Uma versão não usa o contrato editorial de perfil esperado.",
                    )
                if normalized.get("identity_rule") != "EXACT_AR_DEP_ID_ONLY":
                    block(
                        "IDENTITY_RULE_INVALID",
                        "Uma versão deixou de exigir o DepId oficial exato.",
                    )
                if normalized.get("mandate_inference_allowed") is not False:
                    block(
                        "MANDATE_INFERENCE_NOT_BLOCKED",
                        "Uma versão deixou de proibir inferências de mandato.",
                    )

            if not (
                str(row["latest_decision_action"] or "") == "APPROVE"
                and str(row["latest_decision_state"] or "") == "APPROVED"
                and row["latest_source_confirmed"] is True
                and str(row["latest_decision_version_id"] or "") == str(current_version_id)
                and int(row["latest_decision_revision"] or -1) == int(row["case_revision"])
            ):
                block(
                    "APPROVAL_PROOF_INVALID",
                    "A última decisão não prova aprovação da versão atual e confirmação da fonte.",
                )
            if int(row["publication_event_count"] or 0) != 0:
                block(
                    "UNEXPECTED_PUBLICATION_HISTORY",
                    "Um processo de perfil já contém publicação fora desta nova porta.",
                )

            proof_entries.append(
                {
                    "observation_reference_sha256": _reference_sha256(observation_id),
                    "case_reference_sha256": _reference_sha256(case_id),
                    "version_sha256": stored_version_sha256,
                }
            )

        if legacy_review_decisions:
            block(
                "LEGACY_PUBLICATION_REQUIRES_RECONCILIATION",
                "Existem decisões públicas antigas que exigem reconciliação explícita.",
                legacy_review_decisions,
            )

        blockers = list(blocker_counts.values())
        editorial_counts = {state: state_counter.get(state, 0) for state in _EDITORIAL_STATES}
        proof_payload = {
            "schema_version": _READINESS_SCHEMA_VERSION,
            "snapshot_reference_sha256": _reference_sha256(snapshot_id),
            "source_sha256": source_sha256,
            "snapshot_sha256": normalised_sha256,
            "manifest_counts": manifest_counts,
            "materialised_counts": materialised_counts,
            "approved_versions": proof_entries,
            "identity_projection": {
                "exact_existing_people": exact_people,
                "new_people_required": new_people,
                "existing_memberships": existing_memberships,
                "existing_party_links": existing_party_links,
                "legacy_review_decisions": legacy_review_decisions,
                "legacy_positive_reviews": legacy_positive_reviews,
            },
        }
        eligible = not blockers
        return {
            "snapshot_id": snapshot_id,
            "source_document_id": str(snapshot["source_document_id"]),
            "legislature": str(snapshot["legislature"]),
            "parser_version": str(snapshot["parser_version"]),
            "normalised_sha256": normalised_sha256,
            "collected_at": snapshot["collected_at"],
            "source": {
                "publisher": str(snapshot["source_publisher"]),
                "kind": str(snapshot["source_kind"]),
                "title": str(snapshot["source_title"]),
                "official_identifier": snapshot["official_identifier"],
                "url": str(snapshot["source_url"]),
                "retrieved_at": snapshot["source_retrieved_at"],
                "content_sha256": source_sha256,
                "mime_type": snapshot["source_mime_type"],
            },
            "archive": (
                {
                    "storage_backend": str(snapshot["storage_backend"]),
                    "byte_size": int(snapshot["byte_size"]),
                    "archived_at": snapshot["archived_at"],
                    "attestation_sha256": str(snapshot["attestation_sha256"]),
                }
                if archive_attested
                else None
            ),
            "archive_attested": archive_attested,
            "manifest_counts": manifest_counts,
            "materialised_counts": materialised_counts,
            "manifest_matches": manifest_matches,
            "editorial_counts": editorial_counts,
            "identity_projection": proof_payload["identity_projection"],
            "readiness_proof_sha256": _sha256_json(proof_payload) if eligible else None,
            "eligible": eligible,
            "blockers": blockers,
            "publication_performed": False,
            "public_write_performed": False,
            "mandate_inference_allowed": False,
            "publication_state": "PRIVATE_READINESS_ONLY",
            "publication_rule": (
                "Esta inspeção não publica. Uma futura ação ADMIN com MFA terá de repetir "
                "todas as provas e confirmar a fotografia completa pelo hash de prontidão."
            ),
        }
