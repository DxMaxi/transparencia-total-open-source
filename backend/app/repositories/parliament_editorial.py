"""Adaptador privado entre snapshots parlamentares e o circuito editorial V5."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.models.editorial import (
    EditorialCaseKind,
    ParliamentEditorialProposalRequest,
    ParliamentEditorialScope,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialRepository,
    EditorialSourceError,
)

_INGESTION_ALIAS = "parliament-ingestion"
_SUBJECTS = {
    ParliamentEditorialScope.ACTIVITY: (
        EditorialCaseKind.PARLIAMENT_ACTIVITY,
        "PARLIAMENT_ACTIVITY_SNAPSHOT",
    ),
    ParliamentEditorialScope.VOTES: (
        EditorialCaseKind.PARLIAMENT_VOTE,
        "PARLIAMENT_VOTES_SNAPSHOT",
    ),
}


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def _reference_sha256(value: object) -> str:
    """Preserva a ligação auditável sem duplicar identificadores na proposta JSON."""

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _case_reference(row: asyncpg.Record, prefix: str) -> dict[str, object] | None:
    case_id = row[f"{prefix}_case_id"]
    if case_id is None:
        return None
    return {
        "id": str(case_id),
        "state": str(row[f"{prefix}_case_state"]),
        "revision": int(row[f"{prefix}_case_revision"]),
        "origin": str(row[f"{prefix}_case_origin"]),
    }


class ParliamentEditorialRepository:
    """Lê apenas prova imutável e gera propostas ``INGESTION`` sem publicar."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    async def list_snapshot_candidates(
        self,
        *,
        legislature: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        normalised_legislature = legislature.strip() if legislature else None
        if normalised_legislature == "":
            normalised_legislature = None
        return await self._load_candidates(
            legislature=normalised_legislature,
            snapshot_id=None,
            limit=limit,
        )

    async def create_proposal(
        self,
        *,
        payload: ParliamentEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        candidates = await self._load_candidates(
            legislature=None,
            snapshot_id=payload.snapshot_id,
            limit=1,
        )
        if not candidates:
            raise EditorialSourceError(
                "A fotografia parlamentar não existe ou não possui arquivo oficial atestado"
            )
        candidate = candidates[0]
        existing_cases = candidate["editorial_cases"]
        assert isinstance(existing_cases, dict)
        existing = existing_cases[payload.scope.value]
        if isinstance(existing, dict):
            if existing.get("origin") != "INGESTION":
                raise EditorialConflictError(
                    "Já existe um processo editorial de outra origem para esta fotografia e âmbito"
                )
            return {
                "created": False,
                "case": await self.editorial.get_case(str(existing["id"])),
            }

        if candidate["manifest_matches"] is not True:
            raise EditorialSourceError(
                "A fotografia parlamentar diverge do manifesto imutável e não pode entrar na fila"
            )

        kind, subject_type = _SUBJECTS[payload.scope]
        normalized_data = self._normalized_proposal(candidate, payload.scope)
        case, created = await self.editorial.create_ingestion_case(
            kind=kind,
            subject_type=subject_type,
            subject_id=payload.snapshot_id,
            source_document_id=str(candidate["source_document_id"]),
            normalized_data=normalized_data,
            origin_alias=_INGESTION_ALIAS,
            submission_rationale=(
                "Fotografia oficial parlamentar importada para revisão privada por âmbito; "
                "não existe publicação automática nem inferência de votos individuais."
            ),
            actor=actor,
        )
        return {"created": created, "case": case}

    async def _load_candidates(
        self,
        *,
        legislature: str | None,
        snapshot_id: str | None,
        limit: int,
        connection: asyncpg.Connection | None = None,
        lock_snapshots: bool = False,
    ) -> list[dict[str, object]]:
        if connection is None:
            async with self.pool.acquire() as acquired:
                return await self._load_candidates(
                    legislature=legislature,
                    snapshot_id=snapshot_id,
                    limit=limit,
                    connection=acquired,
                    lock_snapshots=lock_snapshots,
                )

        conditions = [
            "source.publisher = 'PARLIAMENT'",
            "source.url LIKE 'https://%'",
            "source.kind <> 'NEWS_ARTICLE'",
        ]
        arguments: list[object] = []
        if legislature is not None:
            arguments.append(legislature)
            conditions.append(f"snapshot.legislature = ${len(arguments)}")
        if snapshot_id is not None:
            arguments.append(snapshot_id)
            conditions.append(f"snapshot.id = ${len(arguments)}")
        arguments.append(limit)

        lock_clause = "FOR UPDATE OF snapshot" if lock_snapshots else ""
        query = f"""
            SELECT
                snapshot.id,
                snapshot.source_document_id,
                snapshot.legislature,
                snapshot.parser_version,
                snapshot.normalised_sha256,
                snapshot.collected_at,
                snapshot.created_at,
                snapshot.session_count,
                snapshot.initiative_count,
                snapshot.vote_count,
                snapshot.vote_record_count,
                source.title AS source_title,
                source.official_identifier,
                source.url AS source_url,
                source.retrieved_at AS source_retrieved_at,
                source.content_sha256 AS source_sha256,
                source.mime_type AS source_mime_type,
                archive.storage_backend,
                archive.byte_size,
                archive.archived_at,
                archive.attestation_sha256,
                previous.id AS previous_snapshot_id,
                previous.normalised_sha256 AS previous_normalised_sha256,
                previous.collected_at AS previous_collected_at,
                activity_case.id AS activity_case_id,
                activity_case.current_state AS activity_case_state,
                activity_case.revision AS activity_case_revision,
                activity_case.origin AS activity_case_origin,
                votes_case.id AS votes_case_id,
                votes_case.current_state AS votes_case_state,
                votes_case.revision AS votes_case_revision,
                votes_case.origin AS votes_case_origin
            FROM parliament_activity_snapshots AS snapshot
            JOIN source_documents AS source ON source.id = snapshot.source_document_id
            JOIN LATERAL (
                SELECT attestation.storage_backend, attestation.byte_size,
                       attestation.archived_at, attestation.attestation_sha256
                FROM source_archive_attestations AS attestation
                WHERE attestation.source_document_id = source.id
                  AND attestation.content_sha256 = source.content_sha256
                  AND attestation.retrieval_url = source.url
                  AND attestation.retrieved_at = source.retrieved_at
                ORDER BY attestation.archived_at ASC, attestation.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT candidate.id, candidate.normalised_sha256, candidate.collected_at
                FROM parliament_activity_snapshots AS candidate
                JOIN source_documents AS candidate_source
                  ON candidate_source.id = candidate.source_document_id
                WHERE candidate.legislature = snapshot.legislature
                  AND candidate_source.publisher = 'PARLIAMENT'
                  AND candidate_source.url LIKE 'https://%'
                  AND candidate_source.kind <> 'NEWS_ARTICLE'
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations AS candidate_archive
                      WHERE candidate_archive.source_document_id = candidate_source.id
                        AND candidate_archive.content_sha256 = candidate_source.content_sha256
                        AND candidate_archive.retrieval_url = candidate_source.url
                        AND candidate_archive.retrieved_at = candidate_source.retrieved_at
                  )
                  AND (candidate.collected_at, candidate.created_at, candidate.id)
                      < (snapshot.collected_at, snapshot.created_at, snapshot.id)
                ORDER BY candidate.collected_at DESC, candidate.created_at DESC,
                         candidate.id DESC
                LIMIT 1
            ) AS previous ON TRUE
            LEFT JOIN editorial_cases AS activity_case
              ON activity_case.kind = 'PARLIAMENT_ACTIVITY'::"EditorialCaseKind"
             AND activity_case.subject_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
             AND activity_case.subject_id = snapshot.id
             AND activity_case.source_document_id = snapshot.source_document_id
            LEFT JOIN editorial_cases AS votes_case
              ON votes_case.kind = 'PARLIAMENT_VOTE'::"EditorialCaseKind"
             AND votes_case.subject_type = 'PARLIAMENT_VOTES_SNAPSHOT'
             AND votes_case.subject_id = snapshot.id
             AND votes_case.source_document_id = snapshot.source_document_id
            WHERE {" AND ".join(conditions)}
            ORDER BY snapshot.collected_at DESC, snapshot.created_at DESC, snapshot.id DESC
            LIMIT ${len(arguments)}
            {lock_clause}
        """

        rows = await connection.fetch(query, *arguments)
        if not rows:
            return []
        snapshot_ids = [str(row["id"]) for row in rows]
        previous_ids = [
            str(row["previous_snapshot_id"]) if row["previous_snapshot_id"] is not None else None
            for row in rows
        ]
        metrics = await self._snapshot_metrics(connection, snapshot_ids)
        diffs = await self._snapshot_diffs(connection, snapshot_ids, previous_ids)

        return [
            self._candidate(row, metrics[str(row["id"])], diffs[str(row["id"])]) for row in rows
        ]

    async def load_snapshot_candidate_for_publication(
        self,
        connection: asyncpg.Connection,
        *,
        snapshot_id: str,
        lock_snapshot: bool,
    ) -> dict[str, object]:
        """Reconstrói a prova V5.2 na mesma ligação usada pela publicação."""

        candidates = await self._load_candidates(
            legislature=None,
            snapshot_id=snapshot_id,
            limit=1,
            connection=connection,
            lock_snapshots=lock_snapshot,
        )
        if not candidates:
            raise EditorialSourceError(
                "A fotografia parlamentar não existe ou perdeu a prova oficial atestada"
            )
        return candidates[0]

    @classmethod
    def normalized_proposal_for_publication(
        cls,
        candidate: dict[str, object],
        scope: ParliamentEditorialScope,
    ) -> dict[str, Any]:
        return cls._normalized_proposal(candidate, scope)

    @staticmethod
    async def _snapshot_metrics(
        connection: asyncpg.Connection,
        snapshot_ids: list[str],
    ) -> dict[str, dict[str, int]]:
        rows = await connection.fetch(
            """
            WITH requested AS (
                SELECT unnest($1::text[]) AS snapshot_id
            ),
            session_metrics AS (
                SELECT session.snapshot_id, count(*)::int AS total
                FROM parliamentary_sessions AS session
                WHERE session.snapshot_id = ANY($1::text[])
                GROUP BY session.snapshot_id
            ),
            initiative_metrics AS (
                SELECT initiative.snapshot_id, count(*)::int AS total
                FROM parliamentary_initiatives AS initiative
                WHERE initiative.snapshot_id = ANY($1::text[])
                GROUP BY initiative.snapshot_id
            ),
            vote_metrics AS (
                SELECT
                    event.snapshot_id,
                    count(DISTINCT event.id)::int AS votes,
                    count(record.id)::int AS vote_records,
                    count(DISTINCT event.id) FILTER (WHERE event.is_nominal)::int
                        AS nominal_votes,
                    count(DISTINCT event.id) FILTER (WHERE record.id IS NULL)::int
                        AS votes_without_records,
                    count(record.id) FILTER (WHERE record.actor_type = 'PERSON')::int
                        AS person_records,
                    count(record.id) FILTER (
                        WHERE record.actor_type = 'PERSON'
                          AND record.actor_source_id IS NOT NULL
                    )::int AS exact_person_records,
                    count(record.id) FILTER (
                        WHERE record.actor_type = 'PERSON'
                          AND record.actor_source_id IS NULL
                    )::int AS unproven_person_records,
                    count(record.id) FILTER (
                        WHERE record.actor_type = 'PERSON'
                          AND record.person_id IS NOT NULL
                          AND record.actor_source_id = linked_person.source_id
                    )::int AS linked_person_records,
                    count(record.id) FILTER (
                        WHERE record.actor_type = 'PERSON'
                          AND record.actor_source_id IS NOT NULL
                          AND record.person_id IS NULL
                    )::int AS unlinked_person_records,
                    count(record.id) FILTER (
                        WHERE record.actor_type = 'PERSON'
                          AND record.person_id IS NOT NULL
                          AND record.actor_source_id IS DISTINCT FROM linked_person.source_id
                    )::int AS mismatched_person_links,
                    count(record.id) FILTER (WHERE record.actor_type = 'PARTY')::int
                        AS party_records,
                    count(record.id) FILTER (
                        WHERE record.actor_type = 'PARTY' AND record.party_id IS NOT NULL
                    )::int AS linked_party_records,
                    count(record.id) FILTER (
                        WHERE record.actor_type = 'PARTY' AND record.party_id IS NULL
                    )::int AS unlinked_party_records,
                    count(record.id) FILTER (WHERE record.actor_type = 'UNKNOWN')::int
                        AS unknown_actor_records,
                    count(record.id) FILTER (WHERE record.choice = 'UNKNOWN')::int
                        AS unknown_choice_records,
                    count(record.id) FILTER (
                        WHERE (record.actor_type = 'UNKNOWN'
                               AND (record.person_id IS NOT NULL OR record.party_id IS NOT NULL))
                           OR (record.actor_type = 'PERSON' AND record.party_id IS NOT NULL)
                           OR (record.actor_type = 'PARTY' AND record.person_id IS NOT NULL)
                           OR (record.actor_type = 'PERSON'
                               AND record.person_id IS NOT NULL
                               AND record.actor_source_id IS DISTINCT FROM linked_person.source_id)
                    )::int AS inconsistent_actor_links
                FROM vote_events AS event
                LEFT JOIN vote_records AS record
                 ON record.vote_event_id = event.id
                 AND record.source_document_id = event.source_document_id
                LEFT JOIN people AS linked_person ON linked_person.id = record.person_id
                WHERE event.snapshot_id = ANY($1::text[])
                GROUP BY event.snapshot_id
            )
            SELECT
                requested.snapshot_id,
                COALESCE(session_metrics.total, 0)::int AS sessions,
                COALESCE(initiative_metrics.total, 0)::int AS initiatives,
                COALESCE(vote_metrics.votes, 0)::int AS votes,
                COALESCE(vote_metrics.vote_records, 0)::int AS vote_records,
                COALESCE(vote_metrics.nominal_votes, 0)::int AS nominal_votes,
                COALESCE(vote_metrics.votes_without_records, 0)::int AS votes_without_records,
                COALESCE(vote_metrics.person_records, 0)::int AS person_records,
                COALESCE(vote_metrics.exact_person_records, 0)::int AS exact_person_records,
                COALESCE(vote_metrics.unproven_person_records, 0)::int
                    AS unproven_person_records,
                COALESCE(vote_metrics.linked_person_records, 0)::int
                    AS linked_person_records,
                COALESCE(vote_metrics.unlinked_person_records, 0)::int
                    AS unlinked_person_records,
                COALESCE(vote_metrics.mismatched_person_links, 0)::int
                    AS mismatched_person_links,
                COALESCE(vote_metrics.party_records, 0)::int AS party_records,
                COALESCE(vote_metrics.linked_party_records, 0)::int AS linked_party_records,
                COALESCE(vote_metrics.unlinked_party_records, 0)::int
                    AS unlinked_party_records,
                COALESCE(vote_metrics.unknown_actor_records, 0)::int
                    AS unknown_actor_records,
                COALESCE(vote_metrics.unknown_choice_records, 0)::int
                    AS unknown_choice_records,
                COALESCE(vote_metrics.inconsistent_actor_links, 0)::int
                    AS inconsistent_actor_links
            FROM requested
            LEFT JOIN session_metrics ON session_metrics.snapshot_id = requested.snapshot_id
            LEFT JOIN initiative_metrics
              ON initiative_metrics.snapshot_id = requested.snapshot_id
            LEFT JOIN vote_metrics ON vote_metrics.snapshot_id = requested.snapshot_id
            """,
            snapshot_ids,
        )
        return {
            str(row["snapshot_id"]): {
                key: int(row[key])
                for key in (
                    "sessions",
                    "initiatives",
                    "votes",
                    "vote_records",
                    "nominal_votes",
                    "votes_without_records",
                    "person_records",
                    "exact_person_records",
                    "unproven_person_records",
                    "linked_person_records",
                    "unlinked_person_records",
                    "mismatched_person_links",
                    "party_records",
                    "linked_party_records",
                    "unlinked_party_records",
                    "unknown_actor_records",
                    "unknown_choice_records",
                    "inconsistent_actor_links",
                )
            }
            for row in rows
        }

    @staticmethod
    async def _snapshot_diffs(
        connection: asyncpg.Connection,
        snapshot_ids: list[str],
        previous_ids: list[str | None],
    ) -> dict[str, dict[str, object]]:
        rows = await connection.fetch(
            """
            WITH pairs AS (
                SELECT *
                FROM unnest($1::text[], $2::text[])
                    AS pair(snapshot_id, previous_snapshot_id)
            )
            SELECT
                pair.snapshot_id,
                pair.previous_snapshot_id,
                session_diff.added::int AS sessions_added,
                session_diff.removed::int AS sessions_removed,
                session_diff.changed::int AS sessions_changed,
                session_diff.unchanged::int AS sessions_unchanged,
                initiative_diff.added::int AS initiatives_added,
                initiative_diff.removed::int AS initiatives_removed,
                initiative_diff.changed::int AS initiatives_changed,
                initiative_diff.unchanged::int AS initiatives_unchanged,
                vote_diff.added::int AS votes_added,
                vote_diff.removed::int AS votes_removed,
                vote_diff.changed::int AS votes_changed,
                vote_diff.unchanged::int AS votes_unchanged
            FROM pairs AS pair
            LEFT JOIN LATERAL (
                SELECT
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NULL
                    ) AS added,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NULL
                          AND previous_item.source_id IS NOT NULL
                    ) AS removed,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NOT NULL
                          AND current_item.payload IS DISTINCT FROM previous_item.payload
                    ) AS changed,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NOT NULL
                          AND current_item.payload IS NOT DISTINCT FROM previous_item.payload
                    ) AS unchanged
                FROM (
                    SELECT session.source_id,
                           jsonb_build_array(session.session_number, session.title,
                                             session.starts_at, session.ends_at) AS payload
                    FROM parliamentary_sessions AS session
                    WHERE session.snapshot_id = pair.snapshot_id
                ) AS current_item
                FULL OUTER JOIN (
                    SELECT session.source_id,
                           jsonb_build_array(session.session_number, session.title,
                                             session.starts_at, session.ends_at) AS payload
                    FROM parliamentary_sessions AS session
                    WHERE session.snapshot_id = pair.previous_snapshot_id
                ) AS previous_item USING (source_id)
            ) AS session_diff ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NULL
                    ) AS added,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NULL
                          AND previous_item.source_id IS NOT NULL
                    ) AS removed,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NOT NULL
                          AND current_item.payload IS DISTINCT FROM previous_item.payload
                    ) AS changed,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NOT NULL
                          AND current_item.payload IS NOT DISTINCT FROM previous_item.payload
                    ) AS unchanged
                FROM (
                    SELECT initiative.source_id,
                           jsonb_build_array(
                               initiative.number, initiative.type, initiative.title,
                               initiative.description, initiative.introduced_at,
                               initiative.status, initiative.official_url
                           ) AS payload
                    FROM parliamentary_initiatives AS initiative
                    WHERE initiative.snapshot_id = pair.snapshot_id
                ) AS current_item
                FULL OUTER JOIN (
                    SELECT initiative.source_id,
                           jsonb_build_array(
                               initiative.number, initiative.type, initiative.title,
                               initiative.description, initiative.introduced_at,
                               initiative.status, initiative.official_url
                           ) AS payload
                    FROM parliamentary_initiatives AS initiative
                    WHERE initiative.snapshot_id = pair.previous_snapshot_id
                ) AS previous_item USING (source_id)
            ) AS initiative_diff ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NULL
                    ) AS added,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NULL
                          AND previous_item.source_id IS NOT NULL
                    ) AS removed,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NOT NULL
                          AND current_item.payload IS DISTINCT FROM previous_item.payload
                    ) AS changed,
                    count(*) FILTER (
                        WHERE current_item.source_id IS NOT NULL
                          AND previous_item.source_id IS NOT NULL
                          AND current_item.payload IS NOT DISTINCT FROM previous_item.payload
                    ) AS unchanged
                FROM (
                    SELECT event.source_id,
                           jsonb_build_array(
                               event.title, event.initiative_number, event.voted_at,
                               event.result, event.is_nominal,
                               COALESCE(
                                   jsonb_agg(
                                       jsonb_build_array(
                                           record.actor_type::text, record.actor_label,
                                           record.choice::text, record.person_id, record.party_id
                                       )
                                       ORDER BY record.actor_type, record.actor_label
                                   ) FILTER (WHERE record.id IS NOT NULL),
                                   '[]'::jsonb
                               )
                           ) AS payload
                    FROM vote_events AS event
                    LEFT JOIN vote_records AS record
                      ON record.vote_event_id = event.id
                     AND record.source_document_id = event.source_document_id
                    WHERE event.snapshot_id = pair.snapshot_id
                    GROUP BY event.id
                ) AS current_item
                FULL OUTER JOIN (
                    SELECT event.source_id,
                           jsonb_build_array(
                               event.title, event.initiative_number, event.voted_at,
                               event.result, event.is_nominal,
                               COALESCE(
                                   jsonb_agg(
                                       jsonb_build_array(
                                           record.actor_type::text, record.actor_label,
                                           record.choice::text, record.person_id, record.party_id
                                       )
                                       ORDER BY record.actor_type, record.actor_label
                                   ) FILTER (WHERE record.id IS NOT NULL),
                                   '[]'::jsonb
                               )
                           ) AS payload
                    FROM vote_events AS event
                    LEFT JOIN vote_records AS record
                      ON record.vote_event_id = event.id
                     AND record.source_document_id = event.source_document_id
                    WHERE event.snapshot_id = pair.previous_snapshot_id
                    GROUP BY event.id
                ) AS previous_item USING (source_id)
            ) AS vote_diff ON TRUE
            """,
            snapshot_ids,
            previous_ids,
        )
        result: dict[str, dict[str, object]] = {}
        for row in rows:
            snapshot_id = str(row["snapshot_id"])
            if row["previous_snapshot_id"] is None:
                result[snapshot_id] = {
                    "status": "NO_PREVIOUS_SNAPSHOT",
                    "sessions": None,
                    "initiatives": None,
                    "votes": None,
                }
                continue
            result[snapshot_id] = {
                "status": "COMPARED_BY_EXACT_SOURCE_ID",
                "sessions": {
                    "added": int(row["sessions_added"]),
                    "removed": int(row["sessions_removed"]),
                    "changed": int(row["sessions_changed"]),
                    "unchanged": int(row["sessions_unchanged"]),
                },
                "initiatives": {
                    "added": int(row["initiatives_added"]),
                    "removed": int(row["initiatives_removed"]),
                    "changed": int(row["initiatives_changed"]),
                    "unchanged": int(row["initiatives_unchanged"]),
                },
                "votes": {
                    "added": int(row["votes_added"]),
                    "removed": int(row["votes_removed"]),
                    "changed": int(row["votes_changed"]),
                    "unchanged": int(row["votes_unchanged"]),
                },
            }
        return result

    @staticmethod
    def _candidate(
        row: asyncpg.Record,
        metrics: dict[str, int],
        differences: dict[str, object],
    ) -> dict[str, object]:
        expected_counts = {
            "sessions": int(row["session_count"]),
            "initiatives": int(row["initiative_count"]),
            "votes": int(row["vote_count"]),
            "vote_records": int(row["vote_record_count"]),
        }
        actual_counts = {key: metrics[key] for key in expected_counts}
        manifest_matches = expected_counts == actual_counts
        limitations = [
            (
                "As reuniões são apenas as observadas nos eventos da fonte; não representam "
                "necessariamente a agenda parlamentar completa."
            ),
            (
                "As diferenças usam exclusivamente identificadores oficiais exatos; não existe "
                "correspondência aproximada de nomes."
            ),
            (
                "Posições coletivas não são convertidas em votos individuais e campos ausentes "
                "permanecem como dados indisponíveis."
            ),
        ]
        if metrics["unknown_actor_records"]:
            limitations.append(
                f"{metrics['unknown_actor_records']} posição(ões) mantêm o ator como UNKNOWN."
            )
        if metrics["unknown_choice_records"]:
            limitations.append(
                f"{metrics['unknown_choice_records']} posição(ões) mantêm o sentido como UNKNOWN."
            )
        if metrics["votes_without_records"]:
            limitations.append(
                f"{metrics['votes_without_records']} votação(ões) não têm posições normalizadas."
            )
        if metrics["unproven_person_records"]:
            limitations.append(
                f"{metrics['unproven_person_records']} posição(ões) PERSON não preservam o "
                "identificador oficial e ficam bloqueadas para publicação."
            )
        if metrics["mismatched_person_links"]:
            limitations.append(
                f"{metrics['mismatched_person_links']} ligação(ões) de pessoa divergem do "
                "identificador oficial e ficam bloqueadas para publicação."
            )
        if differences["status"] == "NO_PREVIOUS_SNAPSHOT":
            limitations.append("Não existe fotografia anterior comparável nesta legislatura.")
        if not manifest_matches:
            limitations.append(
                "As contagens materializadas divergem do manifesto; a criação da proposta está "
                "bloqueada."
            )

        previous = None
        if row["previous_snapshot_id"] is not None:
            previous = {
                "id": str(row["previous_snapshot_id"]),
                "normalised_sha256": str(row["previous_normalised_sha256"]),
                "collected_at": _iso(row["previous_collected_at"]),
            }

        return {
            "snapshot_id": str(row["id"]),
            "source_document_id": str(row["source_document_id"]),
            "legislature": str(row["legislature"]),
            "parser_version": str(row["parser_version"]),
            "normalised_sha256": str(row["normalised_sha256"]),
            "collected_at": _iso(row["collected_at"]),
            "source": {
                "title": str(row["source_title"]),
                "official_identifier": row["official_identifier"],
                "url": str(row["source_url"]),
                "retrieved_at": _iso(row["source_retrieved_at"]),
                "content_sha256": str(row["source_sha256"]),
                "mime_type": row["source_mime_type"],
            },
            "archive": {
                "storage_backend": str(row["storage_backend"]),
                "byte_size": int(row["byte_size"]),
                "archived_at": _iso(row["archived_at"]),
                "attestation_sha256": str(row["attestation_sha256"]),
            },
            "manifest_counts": expected_counts,
            "materialised_counts": actual_counts,
            "manifest_matches": manifest_matches,
            "coverage": {
                key: metrics[key]
                for key in (
                    "nominal_votes",
                    "votes_without_records",
                    "person_records",
                    "exact_person_records",
                    "unproven_person_records",
                    "linked_person_records",
                    "unlinked_person_records",
                    "mismatched_person_links",
                    "party_records",
                    "linked_party_records",
                    "unlinked_party_records",
                    "unknown_actor_records",
                    "unknown_choice_records",
                    "inconsistent_actor_links",
                )
            },
            "previous_snapshot": previous,
            "differences": differences,
            "limitations": limitations,
            "editorial_cases": {
                "activity": _case_reference(row, "activity"),
                "votes": _case_reference(row, "votes"),
            },
            "proposal_eligible": manifest_matches,
            "publication_state": "PRIVATE_ONLY",
        }

    @staticmethod
    def _normalized_proposal(
        candidate: dict[str, object],
        scope: ParliamentEditorialScope,
    ) -> dict[str, Any]:
        source = candidate["source"]
        archive = candidate["archive"]
        differences = candidate["differences"]
        assert isinstance(source, dict)
        assert isinstance(archive, dict)
        assert isinstance(differences, dict)

        previous_snapshot = candidate["previous_snapshot"]
        normalized_previous_snapshot = None
        if isinstance(previous_snapshot, dict):
            normalized_previous_snapshot = {
                "reference_sha256": _reference_sha256(previous_snapshot["id"]),
                "normalised_sha256": previous_snapshot["normalised_sha256"],
                "collected_at": previous_snapshot["collected_at"],
            }

        if scope is ParliamentEditorialScope.ACTIVITY:
            scoped_differences = {
                "status": differences["status"],
                "sessions": differences["sessions"],
                "initiatives": differences["initiatives"],
            }
        else:
            scoped_differences = {
                "status": differences["status"],
                "votes": differences["votes"],
            }

        return {
            "schema_version": "parliament-editorial-v1",
            "scope": scope.value,
            "legislature": candidate["legislature"],
            "snapshot": {
                "reference_sha256": _reference_sha256(candidate["snapshot_id"]),
                "parser_version": candidate["parser_version"],
                "normalised_sha256": candidate["normalised_sha256"],
                "collected_at": candidate["collected_at"],
                "previous_snapshot": normalized_previous_snapshot,
            },
            "source_proof": {
                "source_document_reference_sha256": _reference_sha256(
                    candidate["source_document_id"]
                ),
                "url": source["url"],
                "retrieved_at": source["retrieved_at"],
                "content_sha256": source["content_sha256"],
                "archive_attestation_sha256": archive["attestation_sha256"],
                "archive_byte_size": archive["byte_size"],
            },
            "manifest_counts": candidate["manifest_counts"],
            "coverage": candidate["coverage"],
            "differences_from_previous_snapshot": scoped_differences,
            "limitations": candidate["limitations"],
            "publication": {
                "state": "PRIVATE_PENDING_REVIEW",
                "automatic_publication": False,
                "human_review_required": True,
            },
        }
