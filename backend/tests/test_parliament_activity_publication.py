from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any

import pytest

from app.repositories.parliament_publication import ParliamentSnapshotPublicationRepository


class Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class PublicationConnection:
    def __init__(self, *, counts: dict[str, int] | None = None, archived: bool = True) -> None:
        self.counts = counts or {
            "sessions": 2,
            "initiatives": 3,
            "votes": 4,
            "vote_records": 5,
        }
        self.archived = archived
        self.fetch_queries: list[str] = []
        self.commands: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> Transaction:
        return Transaction()

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any]:
        self.fetch_queries.append(query)
        if "FROM parliament_activity_snapshots snapshot" in query:
            assert arguments == ("XVII",)
            return {
                "id": "snapshot-1",
                "source_document_id": "source-1",
                "legislature": "XVII",
                "parser_version": "parliament-activity-v2",
                "normalised_sha256": "b" * 64,
                "collected_at": datetime(2026, 8, 8),
                "session_count": self.counts["sessions"],
                "initiative_count": self.counts["initiatives"],
                "vote_count": self.counts["votes"],
                "vote_record_count": self.counts["vote_records"],
                "source_url": "https://www.parlamento.pt/dados.json",
                "source_sha256": "a" * 64,
                "source_retrieved_at": datetime(2026, 8, 8),
                "archive_attestation_id": "archive-1" if self.archived else None,
                "activity_publishable": None,
                "activity_reviewed_at": None,
                "votes_publishable": None,
                "votes_reviewed_at": None,
            }
        assert arguments == ("snapshot-1", "source-1")
        return {
            "sessions": self.counts["sessions"],
            "initiatives": self.counts["initiatives"],
            "votes": self.counts["votes"],
            "vote_records": self.counts["vote_records"],
        }

    async def execute(self, query: str, *arguments: object) -> str:
        self.commands.append((query, arguments))
        return "INSERT 0 1"

    async def fetchval(self, query: str, *arguments: object) -> datetime:
        assert "SELECT GREATEST" in query
        assert arguments == (None,)
        return datetime(2026, 8, 8, 12, 0, 0, 123000)


class Acquire:
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


def _repository(connection: PublicationConnection) -> ParliamentSnapshotPublicationRepository:
    return ParliamentSnapshotPublicationRepository(Pool(connection))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_preview_is_read_only_and_exposes_both_hashes_and_counts() -> None:
    connection = PublicationConnection()

    preview = await _repository(connection).inspect(legislature="XVII")

    assert preview["source_sha256"] == "a" * 64
    assert preview["normalised_sha256"] == "b" * 64
    assert preview["counts"] == connection.counts
    assert preview["publication_eligible"] is True
    assert connection.commands == []
    assert all(query.lstrip().startswith("SELECT") for query in connection.fetch_queries)
    assert "publishable = TRUE" not in connection.fetch_queries[0]


@pytest.mark.asyncio
async def test_publication_writes_one_review_and_audit_event_per_scope() -> None:
    connection = PublicationConnection()

    result = await _repository(connection).review(
        legislature="XVII",
        scopes={"activity", "votes"},
        publishable=True,
        expected_source_sha256="a" * 64,
        expected_normalised_sha256="b" * 64,
        expected_counts=connection.counts,
        reviewer_alias="revisor-01",
        rationale="Fonte, cobertura e posições confirmadas na revisão humana.",
    )

    assert {decision["scope"] for decision in result["decisions"]} == {"activity", "votes"}
    assert "FOR UPDATE OF snapshot" in connection.fetch_queries[0]
    assert "pg_advisory_xact_lock" in connection.commands[0][0]
    review_writes = [item for item in connection.commands if "data_publication_reviews" in item[0]]
    audit_writes = [item for item in connection.commands if "audit_events" in item[0]]
    assert len(review_writes) == 2
    assert len(audit_writes) == 2
    assert {item[1][1] for item in review_writes} == {
        "PARLIAMENT_ACTIVITY_SNAPSHOT",
        "PARLIAMENT_VOTES_SNAPSHOT",
    }
    assert all(item[1][2] == "snapshot-1" for item in review_writes)
    assert all(item[1][4] == "source-1" for item in review_writes)


@pytest.mark.asyncio
async def test_publication_rejects_empty_or_unattested_coverage_before_review_write() -> None:
    empty = PublicationConnection(
        counts={"sessions": 0, "initiatives": 3, "votes": 4, "vote_records": 5}
    )
    with pytest.raises(ValueError, match="cobertura vazia"):
        await _repository(empty).review(
            legislature="XVII",
            scopes={"activity"},
            publishable=True,
            expected_source_sha256="a" * 64,
            expected_normalised_sha256="b" * 64,
            expected_counts=empty.counts,
            reviewer_alias="revisor-01",
            rationale="Fonte e cobertura confirmadas na revisão humana independente.",
        )
    assert not any("data_publication_reviews" in item[0] for item in empty.commands)

    unattested = PublicationConnection(archived=False)
    with pytest.raises(ValueError, match="atestação de arquivo"):
        await _repository(unattested).review(
            legislature="XVII",
            scopes={"votes"},
            publishable=True,
            expected_source_sha256="a" * 64,
            expected_normalised_sha256="b" * 64,
            expected_counts=unattested.counts,
            reviewer_alias="revisor-01",
            rationale="Fonte e cobertura confirmadas na revisão humana independente.",
        )
    assert not any("data_publication_reviews" in item[0] for item in unattested.commands)
