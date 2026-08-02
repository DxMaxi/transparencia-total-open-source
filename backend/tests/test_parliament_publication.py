import asyncio
from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest

from app.repositories.postgres import PostgresRepository


class Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class PublicationConnection:
    def __init__(self, *, people: list[dict[str, Any]], source_sha256: str) -> None:
        self.people = people
        self.source_sha256 = source_sha256
        self.commands: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_queries: list[str] = []
        self.writes: list[tuple[str, list[tuple[object, ...]]]] = []

    def transaction(self) -> Transaction:
        return Transaction()

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any] | None:
        if "FROM people person" in query:
            return {"id": "person-1", "active": True, "source_document_id": "source-1"}
        if "FROM sync_runs" in query:
            return {
                "dataset_url": "https://www.parlamento.pt/deputados-xvii.json",
                "status": "SUCCEEDED",
                "records_read": len(self.people),
                "records_written": len(self.people),
                "code_version": "parliament-ingestion-v9",
                "started_at": "2026-08-02T10:00:00",
                "finished_at": "2026-08-02T10:01:00",
            }
        if "FROM source_documents" in query:
            return {
                "id": "source-1",
                "url": "https://www.parlamento.pt/deputados-xvii.json",
                "content_sha256": self.source_sha256,
                "retrieved_at": "2026-08-02T10:00:00",
                "parser_version": "parliament-ingestion-v9",
                "observed_at": "2026-08-02T10:00:00",
                "candidate_count": len(self.people),
            }
        return None

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, Any]]:
        self.fetch_queries.append(query)
        return self.people

    async def execute(self, query: str, *arguments: object) -> None:
        self.commands.append((query, arguments))

    async def executemany(
        self,
        query: str,
        arguments: list[tuple[object, ...]],
    ) -> None:
        self.writes.append((query, arguments))


class Acquire(AbstractAsyncContextManager[PublicationConnection]):
    def __init__(self, connection: PublicationConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> PublicationConnection:
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class Pool:
    def __init__(self, connection: PublicationConnection) -> None:
        self.connection = connection

    def acquire(self) -> Acquire:
        return Acquire(self.connection)


def _people(count: int, *, published: int = 0) -> list[dict[str, Any]]:
    return [
        {
            "id": f"person-{index}",
            "source_id": str(index),
            "name": f"Pessoa {index}",
            "party_short": "AR",
            "constituency": "Lisboa",
            "latest_publishable": index < published,
        }
        for index in range(count)
    ]


def _repository(connection: PublicationConnection) -> PostgresRepository:
    repository = PostgresRepository.__new__(PostgresRepository)
    repository.pool = Pool(connection)  # type: ignore[assignment]
    return repository


def test_preview_does_not_write_and_exposes_snapshot_guard_values() -> None:
    digest = "a" * 64
    connection = PublicationConnection(people=_people(286), source_sha256=digest)

    result = asyncio.run(
        _repository(connection).inspect_parliament_people_publication(legislature="XVII")
    )

    assert result["candidate_count"] == 286
    assert result["source_sha256"] == digest
    assert result["already_published"] == 0
    assert connection.writes == []
    assert "review.source_document_id = snapshot.source_document_id" in connection.fetch_queries[0]


def test_public_listing_requires_review_for_latest_source_document() -> None:
    connection = PublicationConnection(people=[], source_sha256="a" * 64)

    asyncio.run(_repository(connection)._public_person_rows())

    assert "dpr.source_document_id = ms.source_document_id" in connection.fetch_queries[0]


def test_individual_person_review_is_bound_to_latest_source_document() -> None:
    connection = PublicationConnection(people=[], source_sha256="a" * 64)

    result = asyncio.run(
        _repository(connection).review_publication(
            entity_type="PERSON",
            entity_id="person-1",
            publish=True,
            reviewer_alias="revisor-01",
            rationale="Fonte e identidade verificadas no documento oficial.",
        )
    )

    review_commands = [
        item for item in connection.commands if "data_publication_reviews" in item[0]
    ]
    assert result["publishable"] is True
    assert len(review_commands) == 1
    assert review_commands[0][1][8] == "source-1"


def test_publication_rejects_changed_source_hash_before_writing() -> None:
    connection = PublicationConnection(people=_people(286), source_sha256="a" * 64)

    with pytest.raises(ValueError, match="SHA-256"):
        asyncio.run(
            _repository(connection).publish_parliament_people_snapshot(
                legislature="XVII",
                expected_source_sha256="b" * 64,
                expected_count=286,
                reviewer_alias="revisor-01",
                rationale="Fonte e identidade verificadas no documento oficial.",
            )
        )

    assert connection.writes == []


def test_publication_writes_one_review_and_audit_event_per_pending_person() -> None:
    digest = "a" * 64
    connection = PublicationConnection(people=_people(100, published=2), source_sha256=digest)

    result = asyncio.run(
        _repository(connection).publish_parliament_people_snapshot(
            legislature="XVII",
            expected_source_sha256=digest,
            expected_count=100,
            reviewer_alias="revisor-01",
            rationale="Fonte e identidade verificadas no documento oficial.",
        )
    )

    assert result["already_published"] == 2
    assert result["published_now"] == 98
    assert len(connection.writes) == 2
    assert len(connection.writes[0][1]) == 98
    assert len(connection.writes[1][1]) == 98
    assert "data_publication_reviews" in connection.writes[0][0]
    assert "audit_events" in connection.writes[1][0]
    assert connection.writes[0][0].count("necessity_assessment") == 1
    assert connection.writes[0][0].count("proportionality_test") == 1
    assert all(arguments[2] == "source-1" for arguments in connection.writes[0][1])
    assert "pg_advisory_xact_lock" in connection.commands[0][0]
