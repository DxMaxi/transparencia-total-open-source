import asyncio
from typing import Any

import pytest

from app.repositories.postgres import PostgresRepository


class DeactivationConnection:
    def __init__(self, result: int) -> None:
        self.result = result
        self.query = ""
        self.arguments: tuple[Any, ...] = ()

    async def fetchval(self, query: str, *arguments: object) -> int:
        self.query = query
        self.arguments = arguments
        return self.result


class VoteSnapshotConnection:
    def __init__(self, snapshot_exists: bool) -> None:
        self.snapshot_exists = snapshot_exists
        self.lock_query = ""
        self.lock_arguments: tuple[object, ...] = ()
        self.query = ""

    async def execute(self, query: str, *arguments: object) -> None:
        self.lock_query = query
        self.lock_arguments = arguments

    async def fetchval(self, query: str, *arguments: object) -> bool:
        assert arguments == ()
        self.query = query
        return self.snapshot_exists


def test_deactivates_only_people_missing_from_same_legislature_snapshot() -> None:
    connection = DeactivationConnection(1_160)

    result = asyncio.run(
        PostgresRepository._deactivate_stale_parliament_people(
            connection,  # type: ignore[arg-type]
            legislature="XVII",
            incoming_source_ids=["101", "102"],
        )
    )

    assert result == 1_160
    assert connection.arguments == ("XVII", ["101", "102"])
    assert "snapshot.legislature = $1" in connection.query
    assert "person.source_id <> ALL($2::text[])" in connection.query
    assert "source.publisher = 'PARLIAMENT'" in connection.query
    assert "SET active = FALSE" in connection.query


def test_allows_first_parliament_vote_snapshot_in_empty_staging() -> None:
    connection = VoteSnapshotConnection(snapshot_exists=False)

    asyncio.run(
        PostgresRepository._ensure_initial_parliament_vote_snapshot(
            connection,  # type: ignore[arg-type]
        )
    )

    assert "JOIN source_documents" not in connection.query
    assert "FROM vote_events" in connection.query
    assert "pg_advisory_xact_lock" in connection.lock_query
    assert connection.lock_arguments == ("parliament-votes-initial-snapshot",)


def test_blocks_vote_reingestion_until_append_only_versions_exist() -> None:
    connection = VoteSnapshotConnection(snapshot_exists=True)

    with pytest.raises(ValueError, match="versionamento append-only"):
        asyncio.run(
            PostgresRepository._ensure_initial_parliament_vote_snapshot(
                connection,  # type: ignore[arg-type]
            )
        )

    assert "JOIN source_documents" not in connection.query
    assert "pg_advisory_xact_lock" in connection.lock_query


def test_vote_snapshot_persistence_contains_no_destructive_conflict_path() -> None:
    import inspect

    source = inspect.getsource(PostgresRepository.store_parliament_dataset)

    assert "DELETE FROM vote_records" not in source
    vote_branch = source.split("else:", maxsplit=1)[1]
    assert "ON CONFLICT (source_id) DO UPDATE" not in vote_branch
    assert "ON CONFLICT (vote_event_id, actor_type, actor_label)" not in vote_branch
