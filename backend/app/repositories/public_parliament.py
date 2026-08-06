from __future__ import annotations

from typing import Any

import asyncpg


_SOURCE_COLUMNS = """
sd.publisher::text AS source_publisher,
sd.url AS source_url,
sd.retrieved_at AS source_retrieved_at,
sd.content_sha256 AS source_sha256,
review.reviewed_at AS verified_at
"""


def _source(row: Any) -> dict[str, Any]:
    return {
        "publisher": "AR",
        "label": "Assembleia da República — fonte oficial",
        "url": row["source_url"],
        "retrieved_at": row["source_retrieved_at"],
        "content_sha256": row["source_sha256"],
    }


class PublicParliamentRepository:
    """Leitura pública fail-closed da atividade parlamentar revista."""

    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self.pool = pool

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        return self.pool

    async def list_sessions(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT ps.id, ps.source_id, ps.legislature, ps.session_number,
                       ps.title, ps.starts_at, ps.ends_at, {_SOURCE_COLUMNS}
                FROM parliamentary_sessions ps
                JOIN source_documents sd ON sd.id = ps.source_document_id
                JOIN LATERAL (
                    SELECT r.publishable, r.reviewed_at
                    FROM data_publication_reviews r
                    WHERE r.entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                      AND r.entity_id = ps.source_document_id
                      AND r.source_document_id = ps.source_document_id
                    ORDER BY r.reviewed_at DESC, r.id DESC
                    LIMIT 1
                ) review ON review.publishable = TRUE
                WHERE sd.publisher = 'PARLIAMENT'
                  AND EXISTS (
                      SELECT 1 FROM source_archive_attestations a
                      WHERE a.source_document_id = sd.id
                        AND a.content_sha256 = sd.content_sha256
                        AND a.retrieval_url = sd.url
                  )
                ORDER BY ps.starts_at DESC, ps.id
                LIMIT $1 OFFSET $2
                """,
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

    async def list_initiatives(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT pi.id, pi.source_id, pi.legislature, pi.number,
                       pi.type AS initiative_type, pi.title, pi.description,
                       pi.introduced_at, pi.status, pi.official_url, {_SOURCE_COLUMNS}
                FROM parliamentary_initiatives pi
                JOIN source_documents sd ON sd.id = pi.source_document_id
                JOIN LATERAL (
                    SELECT r.publishable, r.reviewed_at
                    FROM data_publication_reviews r
                    WHERE r.entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                      AND r.entity_id = pi.source_document_id
                      AND r.source_document_id = pi.source_document_id
                    ORDER BY r.reviewed_at DESC, r.id DESC
                    LIMIT 1
                ) review ON review.publishable = TRUE
                WHERE sd.publisher = 'PARLIAMENT'
                  AND EXISTS (
                      SELECT 1 FROM source_archive_attestations a
                      WHERE a.source_document_id = sd.id
                        AND a.content_sha256 = sd.content_sha256
                        AND a.retrieval_url = sd.url
                  )
                ORDER BY pi.introduced_at DESC NULLS LAST, pi.number, pi.id
                LIMIT $1 OFFSET $2
                """,
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

    async def list_votes(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT ve.id, ve.source_id, ve.title, ve.initiative_number,
                       ve.voted_at, ve.result, ve.is_nominal, {_SOURCE_COLUMNS}
                FROM vote_events ve
                JOIN source_documents sd ON sd.id = ve.source_document_id
                JOIN LATERAL (
                    SELECT r.publishable, r.reviewed_at
                    FROM data_publication_reviews r
                    WHERE r.entity_type = 'PARLIAMENT_VOTES_SNAPSHOT'
                      AND r.entity_id = ve.source_document_id
                      AND r.source_document_id = ve.source_document_id
                    ORDER BY r.reviewed_at DESC, r.id DESC
                    LIMIT 1
                ) review ON review.publishable = TRUE
                WHERE sd.publisher = 'PARLIAMENT'
                  AND EXISTS (
                      SELECT 1 FROM source_archive_attestations a
                      WHERE a.source_document_id = sd.id
                        AND a.content_sha256 = sd.content_sha256
                        AND a.retrieval_url = sd.url
                  )
                ORDER BY ve.voted_at DESC NULLS LAST, ve.id
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            vote_ids = [row["id"] for row in rows]
            record_rows = (
                await connection.fetch(
                    """
                    SELECT vote_event_id, actor_label, actor_type::text,
                           choice::text, person_id, party_id
                    FROM vote_records
                    WHERE vote_event_id = ANY($1::text[])
                    ORDER BY vote_event_id, actor_type, actor_label
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
                "title": row["title"],
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
