"""Persistência em lote da fotografia parlamentar.

Reduz as viagens de ida e volta à base de dados sem alterar a semântica
append-only nem a identidade determinística dos registos.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.models.api import VoteActorType
from app.models.parliamentary import ParliamentActivityDataset

BATCH_SIZE = 1_000


def _database_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.replace(tzinfo=None)


def _new_id(prefix: str, stable_value: str) -> str:
    digest = hashlib.sha256(stable_value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


async def _execute_batches(
    connection: asyncpg.Connection,
    statement: str,
    rows: Sequence[tuple[Any, ...]],
) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        await connection.executemany(statement, rows[start : start + BATCH_SIZE])


async def append_activity_snapshot(
    connection: asyncpg.Connection,
    dataset: ParliamentActivityDataset,
    source_document_id: str,
    snapshot_id: str,
) -> tuple[int, int, int, int]:
    sessions_written = await _append_sessions(
        connection,
        dataset,
        source_document_id,
        snapshot_id,
    )
    initiatives_written = await _append_initiatives(
        connection,
        dataset,
        source_document_id,
        snapshot_id,
    )
    vote_events_written, vote_records_written = await _append_votes(
        connection,
        dataset,
        source_document_id,
        snapshot_id,
    )
    return (
        sessions_written,
        initiatives_written,
        vote_events_written,
        vote_records_written,
    )


async def _append_sessions(
    connection: asyncpg.Connection,
    dataset: ParliamentActivityDataset,
    source_document_id: str,
    snapshot_id: str,
) -> int:
    before = int(
        await connection.fetchval(
            "SELECT COUNT(*) FROM parliamentary_sessions WHERE snapshot_id = $1",
            snapshot_id,
        )
    )
    rows = [
        (
            _new_id("session", f"{snapshot_id}|{session.source_id}"),
            session.source_id,
            session.legislature,
            session.session_number,
            session.title,
            _database_timestamp(session.starts_at),
            _database_timestamp(session.ends_at),
            snapshot_id,
            source_document_id,
        )
        for session in dataset.sessions
    ]
    await _execute_batches(
        connection,
        """
        INSERT INTO parliamentary_sessions
            (id, source_id, legislature, session_number, title,
             starts_at, ends_at, snapshot_id, source_document_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (source_id, snapshot_id) DO NOTHING
        """,
        rows,
    )
    after = int(
        await connection.fetchval(
            "SELECT COUNT(*) FROM parliamentary_sessions WHERE snapshot_id = $1",
            snapshot_id,
        )
    )
    return after - before


async def _append_initiatives(
    connection: asyncpg.Connection,
    dataset: ParliamentActivityDataset,
    source_document_id: str,
    snapshot_id: str,
) -> int:
    before = int(
        await connection.fetchval(
            "SELECT COUNT(*) FROM parliamentary_initiatives WHERE snapshot_id = $1",
            snapshot_id,
        )
    )
    rows = [
        (
            _new_id("initiative", f"{snapshot_id}|{initiative.source_id}"),
            initiative.source_id,
            initiative.legislature,
            initiative.number,
            initiative.initiative_type,
            initiative.title,
            initiative.description,
            _database_timestamp(initiative.introduced_at),
            initiative.status,
            str(initiative.official_url),
            snapshot_id,
            source_document_id,
        )
        for initiative in dataset.initiatives
    ]
    await _execute_batches(
        connection,
        """
        INSERT INTO parliamentary_initiatives
            (id, source_id, legislature, number, type, title, description,
             introduced_at, status, official_url, snapshot_id,
             source_document_id, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, NOW(), NOW())
        ON CONFLICT (source_id, snapshot_id) DO NOTHING
        """,
        rows,
    )
    after = int(
        await connection.fetchval(
            "SELECT COUNT(*) FROM parliamentary_initiatives WHERE snapshot_id = $1",
            snapshot_id,
        )
    )
    return after - before


async def _append_votes(
    connection: asyncpg.Connection,
    dataset: ParliamentActivityDataset,
    source_document_id: str,
    snapshot_id: str,
) -> tuple[int, int]:
    for event in dataset.votes:
        if not event.is_nominal and any(
            record.actor_type is VoteActorType.PERSON for record in event.records
        ):
            raise RuntimeError("Uma votação não nominal não pode conter votos atribuídos a pessoas")

    before_events = int(
        await connection.fetchval(
            "SELECT COUNT(*) FROM vote_events WHERE snapshot_id = $1",
            snapshot_id,
        )
    )
    before_records = int(
        await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM vote_records record
            JOIN vote_events event ON event.id = record.vote_event_id
            WHERE event.snapshot_id = $1
              AND record.source_document_id = $2
            """,
            snapshot_id,
            source_document_id,
        )
    )

    initiative_rows = await connection.fetch(
        """
        SELECT number, id
        FROM parliamentary_initiatives
        WHERE snapshot_id = $1
        ORDER BY id
        """,
        snapshot_id,
    )
    initiative_ids: dict[str, str] = {}
    for row in initiative_rows:
        initiative_ids.setdefault(str(row["number"]), str(row["id"]))

    event_rows = [
        (
            _new_id("vote", f"{snapshot_id}|{event.source_id}"),
            event.source_id,
            dataset.legislature,
            initiative_ids.get(event.initiative_number or ""),
            event.title,
            event.initiative_number,
            _database_timestamp(event.voted_at),
            event.result,
            event.is_nominal,
            snapshot_id,
            source_document_id,
        )
        for event in dataset.votes
    ]
    await _execute_batches(
        connection,
        """
        INSERT INTO vote_events
            (id, source_id, legislature, initiative_id, title,
             initiative_number, voted_at, result, is_nominal,
             snapshot_id, source_document_id, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())
        ON CONFLICT (source_id, snapshot_id) DO NOTHING
        """,
        event_rows,
    )

    persisted_events = await connection.fetch(
        "SELECT source_id, id FROM vote_events WHERE snapshot_id = $1",
        snapshot_id,
    )
    event_ids = {str(row["source_id"]): str(row["id"]) for row in persisted_events}

    person_source_ids = sorted(
        {
            record.actor_source_id
            for event in dataset.votes
            for record in event.records
            if record.actor_type is VoteActorType.PERSON and record.actor_source_id
        }
    )
    person_rows = await connection.fetch(
        """
        SELECT source_id, id
        FROM people
        WHERE source_id = ANY($1::text[])
        ORDER BY id
        """,
        person_source_ids,
    )
    person_ids = {str(row["source_id"]): str(row["id"]) for row in person_rows}

    party_labels = sorted(
        {
            record.actor_label
            for event in dataset.votes
            for record in event.records
            if record.actor_type is VoteActorType.PARTY
        }
    )
    party_rows = await connection.fetch(
        """
        SELECT id, short_name, source_id
        FROM parties
        WHERE short_name = ANY($1::text[]) OR source_id = ANY($1::text[])
        ORDER BY id
        """,
        party_labels,
    )
    party_ids: dict[str, str] = {}
    for row in party_rows:
        party_id = str(row["id"])
        for key in (row["short_name"], row["source_id"]):
            if key is not None:
                party_ids.setdefault(str(key), party_id)

    record_rows: list[tuple[Any, ...]] = []
    for event in dataset.votes:
        event_id = event_ids.get(event.source_id)
        if event_id is None:
            raise RuntimeError("Não foi possível persistir a votação parlamentar")
        for record in event.records:
            person_id = (
                person_ids.get(record.actor_source_id or "")
                if record.actor_type is VoteActorType.PERSON
                else None
            )
            party_id = (
                party_ids.get(record.actor_label)
                if record.actor_type is VoteActorType.PARTY
                else None
            )
            record_rows.append(
                (
                    _new_id(
                        "vote_record",
                        f"{event_id}|{record.actor_type.value}|{record.actor_label}",
                    ),
                    event_id,
                    record.actor_type.value,
                    record.actor_label,
                    person_id,
                    party_id,
                    record.choice.value,
                    source_document_id,
                )
            )

    await _execute_batches(
        connection,
        """
        INSERT INTO vote_records
            (id, vote_event_id, actor_type, actor_label,
             person_id, party_id, choice, source_document_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (vote_event_id, actor_type, actor_label) DO NOTHING
        """,
        record_rows,
    )

    after_events = int(
        await connection.fetchval(
            "SELECT COUNT(*) FROM vote_events WHERE snapshot_id = $1",
            snapshot_id,
        )
    )
    after_records = int(
        await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM vote_records record
            JOIN vote_events event ON event.id = record.vote_event_id
            WHERE event.snapshot_id = $1
              AND record.source_document_id = $2
            """,
            snapshot_id,
            source_document_id,
        )
    )
    return after_events - before_events, after_records - before_records
