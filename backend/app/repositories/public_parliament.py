from __future__ import annotations

import re
from typing import Any, Literal

import asyncpg

_NUMERIC_VOTE_TITLE = re.compile(r"^\s*\d+(?:/[A-Z0-9.ª-]+)*\s*$", re.IGNORECASE)


def _source(row: Any) -> dict[str, Any]:
    return {
        "publisher": "AR",
        "label": "Assembleia da República — fonte oficial",
        "url": row["source_url"],
        "retrieved_at": row["source_retrieved_at"],
        "content_sha256": row["source_sha256"],
    }


def _vote_title(row: Any) -> str:
    """Substitui um identificador nu apenas quando há uma iniciativa única na fotografia."""

    title = str(row["title"])
    initiative_title = row["initiative_title"]
    if not _NUMERIC_VOTE_TITLE.fullmatch(title) or not initiative_title:
        return title
    initiative_type = row["initiative_type"] or "Iniciativa"
    initiative_number = row["initiative_number"] or title.strip()
    return f"{initiative_type} n.º {initiative_number} — {initiative_title}"


class PublicParliamentRepository:
    """Leitura pública fail-closed da última fotografia revista por âmbito."""

    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self.pool = pool

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        return self.pool

    @staticmethod
    def _latest_snapshot_cte(
        entity_type: Literal[
            "PARLIAMENT_ACTIVITY_SNAPSHOT",
            "PARLIAMENT_VOTES_SNAPSHOT",
        ],
    ) -> str:
        return f"""
            WITH published_snapshot AS (
                SELECT snapshot.id, snapshot.source_document_id,
                       snapshot.legislature, review.reviewed_at AS verified_at,
                       source.url AS source_url,
                       source.retrieved_at AS source_retrieved_at,
                       source.content_sha256 AS source_sha256
                FROM parliament_activity_snapshots snapshot
                JOIN source_documents source
                  ON source.id = snapshot.source_document_id
                JOIN LATERAL (
                    SELECT candidate.publishable, candidate.reviewed_at
                    FROM data_publication_reviews candidate
                    WHERE candidate.entity_type = '{entity_type}'
                      AND candidate.entity_id = snapshot.id
                      AND candidate.source_document_id = source.id
                    ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                    LIMIT 1
                ) review ON review.publishable = TRUE
                WHERE snapshot.legislature = $1
                  AND source.publisher = 'PARLIAMENT'
                  AND EXISTS (
                      SELECT 1 FROM source_archive_attestations attestation
                      WHERE attestation.source_document_id = source.id
                        AND attestation.content_sha256 = source.content_sha256
                        AND attestation.retrieval_url = source.url
                  )
                ORDER BY review.reviewed_at DESC, snapshot.collected_at DESC,
                         snapshot.created_at DESC, snapshot.id DESC
                LIMIT 1
            )
        """

    async def list_sessions(
        self,
        *,
        legislature: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                self._latest_snapshot_cte("PARLIAMENT_ACTIVITY_SNAPSHOT")
                + """
                SELECT session.id, session.source_id, session.legislature,
                       session.session_number, session.title, session.starts_at,
                       session.ends_at, published.verified_at,
                       published.source_url, published.source_retrieved_at,
                       published.source_sha256
                FROM parliamentary_sessions session
                JOIN published_snapshot published
                  ON published.id = session.snapshot_id
                 AND published.source_document_id = session.source_document_id
                ORDER BY session.starts_at DESC, session.id
                LIMIT $2 OFFSET $3
                """,
                legislature,
                limit,
                offset,
            )
        return [
            {
                "id": row["id"],
                "source_id": row["source_id"],
                "legislature": row["legislature"],
                "session_number": row["session_number"],
                "title": row["title"],
                "starts_at": row["starts_at"],
                "ends_at": row["ends_at"],
                "verified_at": row["verified_at"],
                "source": _source(row),
            }
            for row in rows
        ]

    async def list_initiatives(
        self,
        *,
        legislature: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                self._latest_snapshot_cte("PARLIAMENT_ACTIVITY_SNAPSHOT")
                + """
                SELECT initiative.id, initiative.source_id, initiative.legislature,
                       initiative.number, initiative.type AS initiative_type,
                       initiative.title, initiative.description,
                       initiative.introduced_at, initiative.status,
                       initiative.official_url, published.verified_at,
                       published.source_url, published.source_retrieved_at,
                       published.source_sha256
                FROM parliamentary_initiatives initiative
                JOIN published_snapshot published
                  ON published.id = initiative.snapshot_id
                 AND published.source_document_id = initiative.source_document_id
                ORDER BY initiative.introduced_at DESC NULLS LAST,
                         initiative.number, initiative.id
                LIMIT $2 OFFSET $3
                """,
                legislature,
                limit,
                offset,
            )
        return [
            {
                "id": row["id"],
                "source_id": row["source_id"],
                "legislature": row["legislature"],
                "number": row["number"],
                "initiative_type": row["initiative_type"],
                "title": row["title"],
                "description": row["description"],
                "introduced_at": row["introduced_at"],
                "status": row["status"],
                "official_url": row["official_url"],
                "verified_at": row["verified_at"],
                "source": _source(row),
            }
            for row in rows
        ]

    async def list_votes(
        self,
        *,
        legislature: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                self._latest_snapshot_cte("PARLIAMENT_VOTES_SNAPSHOT")
                + """
                SELECT event.id, event.source_id, event.legislature,
                       event.title, event.initiative_number, event.voted_at,
                       event.result, event.is_nominal, published.verified_at,
                       published.source_url, published.source_retrieved_at,
                       published.source_sha256, published.source_document_id,
                       linked_initiative.initiative_type,
                       linked_initiative.initiative_title
                FROM vote_events event
                JOIN published_snapshot published
                  ON published.id = event.snapshot_id
                 AND published.source_document_id = event.source_document_id
                LEFT JOIN LATERAL (
                    SELECT MIN(candidate.type) AS initiative_type,
                           MIN(candidate.title) AS initiative_title
                    FROM parliamentary_initiatives candidate
                    WHERE candidate.snapshot_id = event.snapshot_id
                      AND candidate.source_document_id = event.source_document_id
                      AND candidate.number = event.initiative_number
                    HAVING COUNT(*) = 1
                ) linked_initiative ON TRUE
                ORDER BY event.voted_at DESC NULLS LAST, event.id
                LIMIT $2 OFFSET $3
                """,
                legislature,
                limit,
                offset,
            )
            vote_ids = [str(row["id"]) for row in rows]
            record_rows = (
                await connection.fetch(
                    """
                    SELECT record.vote_event_id, record.actor_label,
                           record.actor_type::text, record.choice::text,
                           record.person_id, record.party_id
                    FROM vote_records record
                    JOIN vote_events event ON event.id = record.vote_event_id
                    WHERE record.vote_event_id = ANY($1::text[])
                      AND record.source_document_id = event.source_document_id
                    ORDER BY record.vote_event_id, record.actor_type, record.actor_label
                    """,
                    vote_ids,
                )
                if vote_ids
                else []
            )
        grouped: dict[str, list[dict[str, Any]]] = {vote_id: [] for vote_id in vote_ids}
        for row in record_rows:
            grouped[str(row["vote_event_id"])].append(
                {
                    "actor_label": row["actor_label"],
                    "actor_type": row["actor_type"],
                    "choice": row["choice"],
                    "person_id": row["person_id"],
                    "party_id": row["party_id"],
                }
            )
        return [
            {
                "id": row["id"],
                "source_id": row["source_id"],
                "legislature": row["legislature"],
                "title": _vote_title(row),
                "initiative_number": row["initiative_number"],
                "voted_at": row["voted_at"],
                "result": row["result"],
                "is_nominal": row["is_nominal"],
                "records": grouped.get(str(row["id"]), []),
                "verified_at": row["verified_at"],
                "source": _source(row),
            }
            for row in rows
        ]
