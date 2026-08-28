from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any, Literal

import asyncpg

_NUMERIC_VOTE_TITLE = re.compile(r"^\s*\d+(?:/[A-Z0-9.ª-]+)*\s*$", re.IGNORECASE)
_EXACT_ACTOR_ID_PARSER_VERSION = "parliament-activity-v6"


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


def _json_object(value: object) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _sha256_json(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _like_pattern(value: str) -> str:
    """Trata %, _ e o marcador ! como texto na pesquisa parametrizada."""

    escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


def _facet_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "value": str(row["value"]),
            "label": str(row["label"]),
            "count": int(row["count"]),
        }
        for row in rows
    ]


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
                       snapshot.legislature, snapshot.parser_version,
                       review.reviewed_at AS verified_at,
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
                       linked_initiative.initiative_title,
                       linked_initiative.initiative_status,
                       linked_initiative.initiative_official_url
                FROM vote_events event
                JOIN published_snapshot published
                  ON published.id = event.snapshot_id
                 AND published.source_document_id = event.source_document_id
                LEFT JOIN LATERAL (
                    SELECT MIN(candidate.type) AS initiative_type,
                           MIN(candidate.title) AS initiative_title,
                           MIN(candidate.status) AS initiative_status,
                           MIN(candidate.official_url) AS initiative_official_url
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
                           person.source_id AS person_source_id,
                           CASE
                             WHEN snapshot.parser_version = 'parliament-activity-v6'
                              AND (to_jsonb(record) ->> 'actor_source_id') = party.source_id
                             THEN party.source_id
                             ELSE NULL
                           END AS party_source_id
                    FROM vote_records record
                    JOIN vote_events event ON event.id = record.vote_event_id
                    JOIN parliament_activity_snapshots snapshot
                      ON snapshot.id = event.snapshot_id
                    LEFT JOIN people person
                      ON person.id = record.person_id
                     AND person.source_id = (to_jsonb(record) ->> 'actor_source_id')
                    LEFT JOIN parties party ON party.id = record.party_id
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
                    "person_source_id": row["person_source_id"],
                    "party_source_id": row["party_source_id"],
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
                "initiative_type": row["initiative_type"],
                "initiative_title": row["initiative_title"],
                "initiative_status": row["initiative_status"],
                "initiative_official_url": row["initiative_official_url"],
                "records": grouped.get(str(row["id"]), []),
                "verified_at": row["verified_at"],
                "source": _source(row),
            }
            for row in rows
        ]

    async def explore(
        self,
        *,
        kind: Literal["sessions", "initiatives", "votes"],
        legislature: str,
        query: str | None,
        date_from: date | None,
        date_to: date | None,
        initiative_type: str | None,
        initiative_status: str | None,
        vote_result: str | None,
        is_nominal: bool | None,
        party_source_id: str | None,
        choice: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Pesquisa uma única fotografia pública sem cruzamentos textuais de identidade."""

        pool = self._require_pool()
        sessions: list[dict[str, Any]] = []
        initiatives: list[dict[str, Any]] = []
        votes: list[dict[str, Any]] = []
        async with pool.acquire() as connection:
            if kind == "sessions":
                sessions, total = await self._explore_sessions(
                    connection,
                    legislature=legislature,
                    query=query,
                    date_from=date_from,
                    date_to=date_to,
                    limit=limit,
                    offset=offset,
                )
            elif kind == "initiatives":
                initiatives, total = await self._explore_initiatives(
                    connection,
                    legislature=legislature,
                    query=query,
                    date_from=date_from,
                    date_to=date_to,
                    initiative_type=initiative_type,
                    initiative_status=initiative_status,
                    limit=limit,
                    offset=offset,
                )
            else:
                votes, total = await self._explore_votes(
                    connection,
                    legislature=legislature,
                    query=query,
                    date_from=date_from,
                    date_to=date_to,
                    initiative_type=initiative_type,
                    vote_result=vote_result,
                    is_nominal=is_nominal,
                    party_source_id=party_source_id,
                    choice=choice,
                    limit=limit,
                    offset=offset,
                )
            facets = await self._explore_facets(connection, legislature=legislature)

        return {
            "kind": kind,
            "legislature": legislature,
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
            "sessions": sessions,
            "initiatives": initiatives,
            "votes": votes,
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": facets,
        }

    async def search_global(
        self,
        *,
        query: str,
        legislature: str,
        limit: int,
    ) -> dict[str, dict[str, object]]:
        """Pesquisa as três projeções sem calcular facetas ou misturar os seus totais."""

        pool = self._require_pool()
        async with pool.acquire() as connection:
            sessions, session_total = await self._explore_sessions(
                connection,
                legislature=legislature,
                query=query,
                date_from=None,
                date_to=None,
                limit=limit,
                offset=0,
            )
            initiatives, initiative_total = await self._explore_initiatives(
                connection,
                legislature=legislature,
                query=query,
                date_from=None,
                date_to=None,
                initiative_type=None,
                initiative_status=None,
                limit=limit,
                offset=0,
            )
            votes, vote_total = await self._explore_votes(
                connection,
                legislature=legislature,
                query=query,
                date_from=None,
                date_to=None,
                initiative_type=None,
                vote_result=None,
                is_nominal=None,
                party_source_id=None,
                choice=None,
                limit=limit,
                offset=0,
            )
        return {
            "sessions": {"items": sessions, "total": session_total},
            "initiatives": {"items": initiatives, "total": initiative_total},
            "votes": {"items": votes, "total": vote_total},
        }

    async def list_coverage(self, *, limit: int) -> list[dict[str, Any]]:
        """Matriz da última fotografia publicada por legislatura e âmbito."""

        pool = self._require_pool()
        async with pool.acquire() as connection:
            snapshots = await connection.fetch(
                """
                WITH latest_reviews AS (
                    SELECT DISTINCT ON (
                               review.entity_type, review.entity_id, review.source_document_id
                           )
                           review.entity_type, review.entity_id, review.source_document_id,
                           review.publishable, review.reviewed_at
                    FROM data_publication_reviews review
                    WHERE review.entity_type IN (
                              'PARLIAMENT_ACTIVITY_SNAPSHOT',
                              'PARLIAMENT_VOTES_SNAPSHOT'
                          )
                    ORDER BY review.entity_type, review.entity_id,
                             review.source_document_id,
                             review.reviewed_at DESC, review.id DESC
                ), ranked_snapshots AS (
                    SELECT snapshot.id, snapshot.source_document_id,
                           snapshot.legislature, snapshot.collected_at,
                           snapshot.normalised_sha256,
                           snapshot.session_count, snapshot.initiative_count,
                           snapshot.vote_count, snapshot.vote_record_count,
                           review.reviewed_at AS verified_at,
                           CASE review.entity_type
                             WHEN 'PARLIAMENT_ACTIVITY_SNAPSHOT' THEN 'activity'
                             ELSE 'votes'
                           END AS scope,
                           source.url AS source_url,
                           source.retrieved_at AS source_retrieved_at,
                           source.content_sha256 AS source_sha256,
                           ROW_NUMBER() OVER (
                               PARTITION BY snapshot.legislature, review.entity_type
                               ORDER BY review.reviewed_at DESC,
                                        snapshot.collected_at DESC,
                                        snapshot.created_at DESC, snapshot.id DESC
                           ) AS publication_rank
                    FROM parliament_activity_snapshots snapshot
                    JOIN source_documents source
                      ON source.id = snapshot.source_document_id
                    JOIN latest_reviews review
                      ON review.entity_id = snapshot.id
                     AND review.source_document_id = source.id
                     AND review.publishable = TRUE
                    WHERE source.publisher = 'PARLIAMENT'
                      AND EXISTS (
                          SELECT 1 FROM source_archive_attestations attestation
                          WHERE attestation.source_document_id = source.id
                            AND attestation.content_sha256 = source.content_sha256
                            AND attestation.retrieval_url = source.url
                      )
                )
                SELECT published.*,
                       session_period.observed_from AS sessions_from,
                       session_period.observed_through AS sessions_through,
                       initiative_period.observed_from AS initiatives_from,
                       initiative_period.observed_through AS initiatives_through,
                       vote_period.observed_from AS votes_from,
                       vote_period.observed_through AS votes_through
                FROM ranked_snapshots published
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS actual_count,
                           MIN(session.starts_at)::date AS observed_from,
                           MAX(session.starts_at)::date AS observed_through
                    FROM parliamentary_sessions session
                    WHERE session.snapshot_id = published.id
                      AND session.source_document_id = published.source_document_id
                ) session_period ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS actual_count,
                           MIN(initiative.introduced_at)::date AS observed_from,
                           MAX(initiative.introduced_at)::date AS observed_through
                    FROM parliamentary_initiatives initiative
                    WHERE initiative.snapshot_id = published.id
                      AND initiative.source_document_id = published.source_document_id
                ) initiative_period ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS actual_count,
                           MIN(event.voted_at)::date AS observed_from,
                           MAX(event.voted_at)::date AS observed_through,
                           (
                               SELECT COUNT(*)
                               FROM vote_records record
                               JOIN vote_events record_event
                                 ON record_event.id = record.vote_event_id
                               WHERE record_event.snapshot_id = published.id
                                 AND record_event.source_document_id =
                                     published.source_document_id
                                 AND record.source_document_id =
                                     published.source_document_id
                           ) AS actual_record_count
                    FROM vote_events event
                    WHERE event.snapshot_id = published.id
                      AND event.source_document_id = published.source_document_id
                ) vote_period ON TRUE
                WHERE published.publication_rank = 1
                  AND (
                      (
                          published.scope = 'activity'
                          AND session_period.actual_count = published.session_count
                          AND initiative_period.actual_count = published.initiative_count
                      )
                      OR (
                          published.scope = 'votes'
                          AND vote_period.actual_count = published.vote_count
                          AND vote_period.actual_record_count = published.vote_record_count
                      )
                  )
                ORDER BY published.collected_at DESC, published.legislature DESC,
                         published.scope
                LIMIT $1
                """,
                limit,
            )

        rows: list[dict[str, Any]] = []
        for snapshot in snapshots:
            common = {
                "legislature": snapshot["legislature"],
                "scope": snapshot["scope"],
                "count_is_exact": True,
                "collected_at": snapshot["collected_at"],
                "verified_at": snapshot["verified_at"],
                "source": _source(snapshot),
                "snapshot_sha256": str(snapshot["normalised_sha256"]),
                "historical_completeness": "NOT_ASSERTED",
            }
            if snapshot["scope"] == "activity":
                specs = (
                    (
                        "sessions",
                        "Reuniões observadas",
                        "session_count",
                        "sessions_from",
                        "sessions_through",
                        "A fonte contém observações de reuniões; não equivale à agenda "
                        "integral da Assembleia da República.",
                    ),
                    (
                        "initiatives",
                        "Iniciativas",
                        "initiative_count",
                        "initiatives_from",
                        "initiatives_through",
                        "A contagem é exata dentro desta fotografia; a completude histórica "
                        "fora do período observado não é afirmada.",
                    ),
                )
            else:
                specs = (
                    (
                        "votes",
                        "Votações",
                        "vote_count",
                        "votes_from",
                        "votes_through",
                        "A contagem é exata dentro desta fotografia; resultado não prova "
                        "entrada em vigor ou impacto material.",
                    ),
                    (
                        "vote_records",
                        "Posições registadas",
                        "vote_record_count",
                        "votes_from",
                        "votes_through",
                        "Inclui posições normalizadas, inclusive UNKNOWN; identidades só são "
                        "associadas por identificador oficial exato.",
                    ),
                )
            for kind, label, count_key, from_key, through_key, limitation in specs:
                rows.append(
                    {
                        **common,
                        "record_kind": kind,
                        "record_label": label,
                        "published_count": int(snapshot[count_key]),
                        "observed_from": snapshot[from_key],
                        "observed_through": snapshot[through_key],
                        "limitation": limitation,
                    }
                )
        return rows[:limit]

    async def _explore_sessions(
        self,
        connection: Any,
        *,
        legislature: str,
        query: str | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        arguments: list[object] = [legislature]
        conditions: list[str] = []
        if query:
            arguments.append(_like_pattern(query))
            parameter = f"${len(arguments)}"
            conditions.append(
                "(session.title ILIKE "
                f"{parameter} ESCAPE '!' OR "
                f"COALESCE(session.session_number, '') ILIKE {parameter} ESCAPE '!' OR "
                f"session.source_id ILIKE {parameter} ESCAPE '!')"
            )
        if date_from is not None:
            arguments.append(date_from)
            conditions.append(f"session.starts_at >= ${len(arguments)}::date")
        if date_to is not None:
            arguments.append(date_to)
            conditions.append(f"session.starts_at < (${len(arguments)}::date + INTERVAL '1 day')")
        where = "".join(f"\n                  AND {condition}" for condition in conditions)
        cte = self._latest_snapshot_cte("PARLIAMENT_ACTIVITY_SNAPSHOT")
        from_sql = f"""
            FROM parliamentary_sessions session
            JOIN published_snapshot published
              ON published.id = session.snapshot_id
             AND published.source_document_id = session.source_document_id
            WHERE TRUE{where}
        """
        total = int(await connection.fetchval(cte + " SELECT COUNT(*) " + from_sql, *arguments))
        page_arguments = [*arguments, limit, offset]
        rows = await connection.fetch(
            cte
            + f"""
                SELECT session.id, session.source_id, session.legislature,
                       session.session_number, session.title, session.starts_at,
                       session.ends_at, published.verified_at,
                       published.source_url, published.source_retrieved_at,
                       published.source_sha256
                {from_sql}
                ORDER BY session.starts_at DESC, session.id
                LIMIT ${len(arguments) + 1} OFFSET ${len(arguments) + 2}
            """,
            *page_arguments,
        )
        return (
            [
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
            ],
            total,
        )

    async def _explore_initiatives(
        self,
        connection: Any,
        *,
        legislature: str,
        query: str | None,
        date_from: date | None,
        date_to: date | None,
        initiative_type: str | None,
        initiative_status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        arguments: list[object] = [legislature]
        conditions: list[str] = []
        if query:
            arguments.append(_like_pattern(query))
            parameter = f"${len(arguments)}"
            conditions.append(
                "(initiative.title ILIKE "
                f"{parameter} ESCAPE '!' OR "
                f"COALESCE(initiative.description, '') ILIKE {parameter} ESCAPE '!' OR "
                f"initiative.number ILIKE {parameter} ESCAPE '!' OR "
                f"initiative.source_id ILIKE {parameter} ESCAPE '!')"
            )
        if date_from is not None:
            arguments.append(date_from)
            conditions.append(f"initiative.introduced_at >= ${len(arguments)}::date")
        if date_to is not None:
            arguments.append(date_to)
            conditions.append(
                f"initiative.introduced_at < (${len(arguments)}::date + INTERVAL '1 day')"
            )
        if initiative_type:
            arguments.append(initiative_type)
            conditions.append(f"initiative.type = ${len(arguments)}")
        if initiative_status:
            arguments.append(initiative_status)
            conditions.append(f"initiative.status = ${len(arguments)}")
        where = "".join(f"\n                  AND {condition}" for condition in conditions)
        cte = self._latest_snapshot_cte("PARLIAMENT_ACTIVITY_SNAPSHOT")
        from_sql = f"""
            FROM parliamentary_initiatives initiative
            JOIN published_snapshot published
              ON published.id = initiative.snapshot_id
             AND published.source_document_id = initiative.source_document_id
            WHERE TRUE{where}
        """
        total = int(await connection.fetchval(cte + " SELECT COUNT(*) " + from_sql, *arguments))
        page_arguments = [*arguments, limit, offset]
        rows = await connection.fetch(
            cte
            + f"""
                SELECT initiative.id, initiative.source_id, initiative.legislature,
                       initiative.number, initiative.type AS initiative_type,
                       initiative.title, initiative.description,
                       initiative.introduced_at, initiative.status,
                       initiative.official_url, published.verified_at,
                       published.source_url, published.source_retrieved_at,
                       published.source_sha256
                {from_sql}
                ORDER BY initiative.introduced_at DESC NULLS LAST,
                         initiative.number, initiative.id
                LIMIT ${len(arguments) + 1} OFFSET ${len(arguments) + 2}
            """,
            *page_arguments,
        )
        return (
            [
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
            ],
            total,
        )

    async def _explore_votes(
        self,
        connection: Any,
        *,
        legislature: str,
        query: str | None,
        date_from: date | None,
        date_to: date | None,
        initiative_type: str | None,
        vote_result: str | None,
        is_nominal: bool | None,
        party_source_id: str | None,
        choice: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        arguments: list[object] = [legislature]
        conditions: list[str] = []
        if query:
            arguments.append(_like_pattern(query))
            parameter = f"${len(arguments)}"
            conditions.append(
                "(event.title ILIKE "
                f"{parameter} ESCAPE '!' OR "
                f"COALESCE(event.initiative_number, '') ILIKE {parameter} ESCAPE '!' OR "
                f"COALESCE(event.result, '') ILIKE {parameter} ESCAPE '!' OR "
                f"event.source_id ILIKE {parameter} ESCAPE '!' OR "
                f"COALESCE(linked_initiative.initiative_title, '') ILIKE {parameter} ESCAPE '!')"
            )
        if date_from is not None:
            arguments.append(date_from)
            conditions.append(f"event.voted_at >= ${len(arguments)}::date")
        if date_to is not None:
            arguments.append(date_to)
            conditions.append(f"event.voted_at < (${len(arguments)}::date + INTERVAL '1 day')")
        if initiative_type:
            arguments.append(initiative_type)
            conditions.append(f"linked_initiative.initiative_type = ${len(arguments)}")
        if vote_result:
            arguments.append(vote_result)
            conditions.append(f"event.result = ${len(arguments)}")
        if is_nominal is not None:
            arguments.append(is_nominal)
            conditions.append(f"event.is_nominal = ${len(arguments)}")
        record_conditions: list[str] = []
        if party_source_id:
            arguments.append(party_source_id)
            conditions.append(f"published.parser_version = '{_EXACT_ACTOR_ID_PARSER_VERSION}'")
            record_conditions.append("record.actor_type = 'PARTY'")
            record_conditions.append("(to_jsonb(record) ->> 'actor_source_id') = party.source_id")
            record_conditions.append(f"party.source_id = ${len(arguments)}")
        if choice:
            arguments.append(choice)
            record_conditions.append(f"record.choice::text = ${len(arguments)}")
        if record_conditions:
            record_where = " AND ".join(record_conditions)
            conditions.append(
                "EXISTS ("
                "SELECT 1 FROM vote_records record "
                "LEFT JOIN parties party ON party.id = record.party_id "
                "WHERE record.vote_event_id = event.id "
                "AND record.source_document_id = event.source_document_id "
                f"AND {record_where})"
            )
        where = "".join(f"\n                  AND {condition}" for condition in conditions)
        cte = self._latest_snapshot_cte("PARLIAMENT_VOTES_SNAPSHOT")
        from_sql = f"""
            FROM vote_events event
            JOIN published_snapshot published
              ON published.id = event.snapshot_id
             AND published.source_document_id = event.source_document_id
            LEFT JOIN LATERAL (
                SELECT MIN(candidate.type) AS initiative_type,
                       MIN(candidate.title) AS initiative_title,
                       MIN(candidate.status) AS initiative_status,
                       MIN(candidate.official_url) AS initiative_official_url
                FROM parliamentary_initiatives candidate
                WHERE candidate.snapshot_id = event.snapshot_id
                  AND candidate.source_document_id = event.source_document_id
                  AND candidate.number = event.initiative_number
                HAVING COUNT(*) = 1
            ) linked_initiative ON TRUE
            WHERE TRUE{where}
        """
        total = int(await connection.fetchval(cte + " SELECT COUNT(*) " + from_sql, *arguments))
        page_arguments = [*arguments, limit, offset]
        rows = await connection.fetch(
            cte
            + f"""
                SELECT event.id, event.source_id, event.legislature,
                       event.title, event.initiative_number, event.voted_at,
                       event.result, event.is_nominal, published.verified_at,
                       published.source_url, published.source_retrieved_at,
                       published.source_sha256,
                       linked_initiative.initiative_type,
                       linked_initiative.initiative_title,
                       linked_initiative.initiative_status,
                       linked_initiative.initiative_official_url
                {from_sql}
                ORDER BY event.voted_at DESC NULLS LAST, event.id
                LIMIT ${len(arguments) + 1} OFFSET ${len(arguments) + 2}
            """,
            *page_arguments,
        )
        vote_ids = [str(row["id"]) for row in rows]
        record_rows = (
            await connection.fetch(
                """
                SELECT record.vote_event_id, record.actor_label,
                       record.actor_type::text, record.choice::text,
                       person.source_id AS person_source_id,
                       CASE
                         WHEN snapshot.parser_version = 'parliament-activity-v6'
                          AND (to_jsonb(record) ->> 'actor_source_id') = party.source_id
                         THEN party.source_id
                         ELSE NULL
                       END AS party_source_id
                FROM vote_records record
                JOIN vote_events event ON event.id = record.vote_event_id
                JOIN parliament_activity_snapshots snapshot
                  ON snapshot.id = event.snapshot_id
                LEFT JOIN people person
                  ON person.id = record.person_id
                 AND person.source_id = (to_jsonb(record) ->> 'actor_source_id')
                LEFT JOIN parties party ON party.id = record.party_id
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
        for record in record_rows:
            grouped[str(record["vote_event_id"])].append(
                {
                    "actor_label": record["actor_label"],
                    "actor_type": record["actor_type"],
                    "choice": record["choice"],
                    "person_source_id": record["person_source_id"],
                    "party_source_id": record["party_source_id"],
                }
            )
        return (
            [
                {
                    "id": row["id"],
                    "source_id": row["source_id"],
                    "legislature": row["legislature"],
                    "title": _vote_title(row),
                    "initiative_number": row["initiative_number"],
                    "voted_at": row["voted_at"],
                    "result": row["result"],
                    "is_nominal": row["is_nominal"],
                    "initiative_type": row["initiative_type"],
                    "initiative_title": row["initiative_title"],
                    "initiative_status": row["initiative_status"],
                    "initiative_official_url": row["initiative_official_url"],
                    "records": grouped.get(str(row["id"]), []),
                    "verified_at": row["verified_at"],
                    "source": _source(row),
                }
                for row in rows
            ],
            total,
        )

    async def _explore_facets(self, connection: Any, *, legislature: str) -> dict[str, Any]:
        legislature_rows = await connection.fetch(
            """
            WITH latest_reviews AS (
                SELECT DISTINCT ON (
                           review.entity_type, review.entity_id, review.source_document_id
                       )
                       review.entity_type, review.entity_id,
                       review.source_document_id, review.publishable
                FROM data_publication_reviews review
                WHERE review.entity_type IN (
                          'PARLIAMENT_ACTIVITY_SNAPSHOT',
                          'PARLIAMENT_VOTES_SNAPSHOT'
                      )
                ORDER BY review.entity_type, review.entity_id,
                         review.source_document_id,
                         review.reviewed_at DESC, review.id DESC
            )
            SELECT snapshot.legislature AS value
            FROM parliament_activity_snapshots snapshot
            JOIN source_documents source ON source.id = snapshot.source_document_id
            JOIN latest_reviews review
              ON review.entity_id = snapshot.id
             AND review.source_document_id = source.id
             AND review.publishable = TRUE
            WHERE source.publisher = 'PARLIAMENT'
              AND EXISTS (
                  SELECT 1 FROM source_archive_attestations attestation
                  WHERE attestation.source_document_id = source.id
                    AND attestation.content_sha256 = source.content_sha256
                    AND attestation.retrieval_url = source.url
              )
            GROUP BY snapshot.legislature
            ORDER BY snapshot.legislature DESC
            """
        )
        initiative_rows = await connection.fetch(
            self._latest_snapshot_cte("PARLIAMENT_ACTIVITY_SNAPSHOT")
            + """
            SELECT 'initiative_type' AS facet, initiative.type AS value,
                   initiative.type AS label, COUNT(*)::int AS count
            FROM parliamentary_initiatives initiative
            JOIN published_snapshot published ON published.id = initiative.snapshot_id
            WHERE initiative.type <> ''
            GROUP BY initiative.type
            UNION ALL
            SELECT 'initiative_status' AS facet, initiative.status AS value,
                   initiative.status AS label, COUNT(*)::int AS count
            FROM parliamentary_initiatives initiative
            JOIN published_snapshot published ON published.id = initiative.snapshot_id
            WHERE initiative.status IS NOT NULL AND initiative.status <> ''
            GROUP BY initiative.status
            ORDER BY facet, label
            """,
            legislature,
        )
        vote_rows = await connection.fetch(
            self._latest_snapshot_cte("PARLIAMENT_VOTES_SNAPSHOT")
            + """
            SELECT 'vote_result' AS facet, event.result AS value,
                   event.result AS label, COUNT(*)::int AS count
            FROM vote_events event
            JOIN published_snapshot published ON published.id = event.snapshot_id
            WHERE event.result IS NOT NULL AND event.result <> ''
            GROUP BY event.result
            UNION ALL
            SELECT 'party' AS facet, party.source_id AS value,
                   COALESCE(NULLIF(party.short_name, ''), party.name) AS label,
                   COUNT(DISTINCT record.vote_event_id)::int AS count
            FROM vote_records record
            JOIN vote_events event ON event.id = record.vote_event_id
            JOIN published_snapshot published ON published.id = event.snapshot_id
            JOIN parties party ON party.id = record.party_id
            WHERE record.actor_type = 'PARTY'
              AND published.parser_version = 'parliament-activity-v6'
              AND (to_jsonb(record) ->> 'actor_source_id') = party.source_id
              AND party.source_id IS NOT NULL
              AND party.source_id <> ''
              AND record.source_document_id = event.source_document_id
            GROUP BY party.source_id, party.short_name, party.name
            ORDER BY facet, label
            """,
            legislature,
        )
        return {
            "legislatures": [str(row["value"]) for row in legislature_rows],
            "initiative_types": _facet_rows(
                [row for row in initiative_rows if row["facet"] == "initiative_type"]
            ),
            "initiative_statuses": _facet_rows(
                [row for row in initiative_rows if row["facet"] == "initiative_status"]
            ),
            "vote_results": _facet_rows(
                [row for row in vote_rows if row["facet"] == "vote_result"]
            ),
            "parties": _facet_rows([row for row in vote_rows if row["facet"] == "party"]),
            "topics_available": False,
        }

    async def list_publication_history(
        self,
        *,
        legislature: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Histórico público redigido; nunca expõe IDs ou fundamentação editorial privada."""

        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT audit.id, audit.entity_id, audit.action, audit.actor_alias,
                       audit.after_json, audit.reason, audit.created_at,
                       source.url AS source_url,
                       source.retrieved_at AS source_retrieved_at,
                       source.content_sha256 AS source_sha256
                FROM audit_events AS audit
                JOIN parliament_activity_snapshots AS snapshot
                  ON snapshot.id = audit.entity_id
                JOIN source_documents AS source
                  ON source.id = snapshot.source_document_id
                WHERE audit.entity_type IN (
                          'PARLIAMENT_ACTIVITY_SNAPSHOT',
                          'PARLIAMENT_VOTES_SNAPSHOT'
                      )
                  AND audit.action IN ('PUBLISHED', 'WITHDRAWN')
                  AND audit.after_json ->> 'legislature' = $1
                  AND audit.after_json -> 'editorial_link' IS NOT NULL
                  AND source.publisher = 'PARLIAMENT'
                  AND source.url LIKE 'https://%'
                ORDER BY audit.created_at DESC, audit.id DESC
                LIMIT $2
                """,
                legislature,
                limit,
            )

        history: list[dict[str, Any]] = []
        for row in rows:
            after = _json_object(row["after_json"])
            if after is None:
                continue
            link = _json_object(after.get("editorial_link"))
            counts = after.get("counts")
            scope = after.get("scope")
            source_sha256 = after.get("source_sha256")
            snapshot_sha256 = after.get("normalised_sha256")
            if (
                link is None
                or scope not in {"activity", "votes"}
                or source_sha256 != str(row["source_sha256"])
                or not isinstance(snapshot_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256)
                or not isinstance(counts, dict)
                or set(counts) != {"sessions", "initiatives", "votes", "vote_records"}
                or any(
                    not isinstance(value, int) or isinstance(value, bool) or value < 0
                    for value in counts.values()
                )
            ):
                continue
            public_effect = _json_object(link.get("public_effect"))
            public_effect_sha256 = link.get("public_effect_sha256")
            action = str(row["action"])
            if action == "WITHDRAWN" and (
                public_effect is None
                or not isinstance(public_effect_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", public_effect_sha256)
                or _sha256_json(public_effect) != public_effect_sha256
            ):
                continue
            history.append(
                {
                    "event_reference_sha256": hashlib.sha256(
                        str(row["id"]).encode("utf-8")
                    ).hexdigest(),
                    "action": action,
                    "scope": scope,
                    "scope_label": ("atividade parlamentar" if scope == "activity" else "votações"),
                    "legislature": legislature,
                    "target_reference_sha256": hashlib.sha256(
                        str(row["entity_id"]).encode("utf-8")
                    ).hexdigest(),
                    "decided_at": row["created_at"],
                    "actor_alias": str(row["actor_alias"]),
                    "public_rationale": str(row["reason"]),
                    "reason_category": (
                        str(link["withdrawal_reason_category"])
                        if link.get("withdrawal_reason_category") is not None
                        else None
                    ),
                    "source": _source(row),
                    "snapshot_sha256": snapshot_sha256,
                    "manifest_counts": counts,
                    "public_effect": public_effect,
                    "public_effect_sha256": (
                        str(public_effect_sha256) if public_effect_sha256 is not None else None
                    ),
                }
            )
        return history
