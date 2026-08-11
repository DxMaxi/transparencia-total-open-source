from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from app.models.api import (
    OfficialSource,
    SourcePublisher,
    VoteActorType,
    VoteChoice,
    VoteEvent,
    VoteRecord,
)
from app.models.parliamentary import (
    ParliamentActivityDataset,
    ParliamentaryInitiativeRecord,
    ParliamentarySessionRecord,
)
from app.repositories.parliament_activity import (
    ParliamentActivityRepository,
    _dataset_digest,
)
from app.repositories.parliament_activity_bulk import _append_votes as _append_votes_bulk


class BulkVoteConnection:
    def __init__(self) -> None:
        self.scalar_results = iter([0, 0, 1, 2])
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.batches: list[tuple[str, list[tuple[Any, ...]]]] = []

    async def fetchval(self, _query: str, *_arguments: object) -> int:
        return next(self.scalar_results)

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, str]]:
        self.fetch_calls.append((query, arguments))
        if "FROM parliamentary_initiatives" in query:
            return []
        if "FROM vote_events" in query:
            return [{"source_id": "vote-1", "id": "vote-event-1"}]
        if "FROM people" in query:
            return []
        if "FROM parties" in query:
            return [{"source_id": "party-source-1", "id": "party-1"}]
        raise AssertionError("Consulta inesperada no teste da persistência em lote")

    async def executemany(
        self,
        statement: str,
        rows: list[tuple[Any, ...]],
    ) -> None:
        self.batches.append((statement, list(rows)))


def _dataset(*, nominal: bool = True) -> ParliamentActivityDataset:
    source = OfficialSource(
        publisher=SourcePublisher.PARLIAMENT,
        label="Assembleia da República — Dados Abertos",
        url=HttpUrl("https://www.parlamento.pt/dados.json"),
        retrieved_at=datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
        content_sha256="a" * 64,
    )
    actor_type = VoteActorType.PERSON if nominal else VoteActorType.PARTY
    actor_label = "Deputado Exemplo" if nominal else "ABC"
    actor_source_id = "dep-1" if nominal else None
    return ParliamentActivityDataset(
        legislature="XVII",
        dataset_url=HttpUrl("https://www.parlamento.pt/dados.json"),
        document_sha256="a" * 64,
        sessions=[
            ParliamentarySessionRecord(
                source_id="reu-1",
                legislature="XVII",
                session_number="1",
                title="Reunião plenária",
                starts_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
                source=source,
            )
        ],
        initiatives=[
            ParliamentaryInitiativeRecord(
                source_id="ini-1",
                legislature="XVII",
                number="1/XVII/1",
                initiative_type="Projeto de Lei",
                title="Título oficial",
                official_url=HttpUrl("https://www.parlamento.pt/iniciativa/1"),
                source=source,
            )
        ],
        votes=[
            VoteEvent(
                source_id="vote-1",
                title="Votação oficial",
                voted_at=datetime(2026, 8, 2, 15, 0, tzinfo=UTC),
                result="Aprovado",
                initiative_number="1/XVII/1",
                is_nominal=nominal,
                records=[
                    VoteRecord(
                        actor_label=actor_label,
                        actor_source_id=actor_source_id,
                        actor_type=actor_type,
                        choice=VoteChoice.FAVOR,
                    )
                ],
                source=source,
            )
        ],
    )


@pytest.mark.asyncio
async def test_rejects_dataset_without_attested_source() -> None:
    connection = AsyncMock()
    connection.fetchval.return_value = None

    with pytest.raises(RuntimeError, match="arquivados e atestados"):
        await ParliamentActivityRepository._require_attested_source(connection, _dataset())


@pytest.mark.asyncio
async def test_appends_sessions_and_initiatives_to_one_snapshot() -> None:
    connection = AsyncMock()
    connection.fetchval.side_effect = ["session-1", "initiative-1"]
    dataset = _dataset()

    sessions = await ParliamentActivityRepository._append_sessions(
        connection, dataset, "source-1", "snapshot-1"
    )
    initiatives = await ParliamentActivityRepository._append_initiatives(
        connection, dataset, "source-1", "snapshot-1"
    )

    assert sessions == 1
    assert initiatives == 1
    assert connection.fetchval.await_count == 2
    all_sql = "\n".join(call.args[0] for call in connection.fetchval.await_args_list)
    assert "ON CONFLICT (source_id, snapshot_id) DO NOTHING" in all_sql
    assert "UPDATE parliamentary_" not in all_sql
    assert "DELETE FROM parliamentary_" not in all_sql


@pytest.mark.asyncio
async def test_persists_nominal_vote_only_as_person() -> None:
    connection = AsyncMock()
    connection.fetchval.side_effect = [
        "initiative-1",
        "vote-event-1",
        "person-1",
        "vote-record-1",
    ]

    events, records = await ParliamentActivityRepository._append_votes(
        connection, _dataset(nominal=True), "source-1", "snapshot-1"
    )

    assert events == 1
    assert records == 1
    insert_call = connection.fetchval.await_args_list[-1]
    assert insert_call.args[3] == VoteActorType.PERSON.value
    assert insert_call.args[5] == "person-1"
    assert insert_call.args[6] is None


@pytest.mark.asyncio
async def test_collective_label_remains_unlinked_without_official_id() -> None:
    connection = AsyncMock()
    connection.fetchval.side_effect = [
        "initiative-1",
        "vote-event-1",
        "vote-record-1",
    ]

    events, records = await ParliamentActivityRepository._append_votes(
        connection, _dataset(nominal=False), "source-1", "snapshot-1"
    )

    assert events == 1
    assert records == 1
    insert_call = connection.fetchval.await_args_list[-1]
    assert insert_call.args[3] == VoteActorType.PARTY.value
    assert insert_call.args[5] is None
    assert insert_call.args[6] is None
    all_sql = "\n".join(call.args[0] for call in connection.fetchval.await_args_list)
    assert "short_name" not in all_sql


@pytest.mark.asyncio
async def test_collective_vote_links_party_only_by_official_source_id() -> None:
    dataset = _dataset(nominal=False)
    record = dataset.votes[0].records[0].model_copy(update={"actor_source_id": "party-source-1"})
    event = dataset.votes[0].model_copy(update={"records": [record]})
    dataset = dataset.model_copy(update={"votes": [event]})
    connection = AsyncMock()
    connection.fetchval.side_effect = [
        "initiative-1",
        "vote-event-1",
        "party-1",
        "vote-record-1",
    ]

    events, records = await ParliamentActivityRepository._append_votes(
        connection, dataset, "source-1", "snapshot-1"
    )

    assert events == 1
    assert records == 1
    party_lookup = connection.fetchval.await_args_list[-2]
    assert "WHERE source_id = $1" in party_lookup.args[0]
    assert "short_name" not in party_lookup.args[0]
    assert party_lookup.args[1] == "party-source-1"
    insert_call = connection.fetchval.await_args_list[-1]
    assert insert_call.args[5] is None
    assert insert_call.args[6] == "party-1"


@pytest.mark.asyncio
async def test_bulk_persistence_never_links_a_collective_label_as_party_identity() -> None:
    dataset = _dataset(nominal=False)
    unlinked = dataset.votes[0].records[0]
    linked = unlinked.model_copy(
        update={
            "actor_label": "Outro rótulo coletivo",
            "actor_source_id": "party-source-1",
        }
    )
    event = dataset.votes[0].model_copy(update={"records": [unlinked, linked]})
    dataset = dataset.model_copy(update={"votes": [event]})
    connection = BulkVoteConnection()

    events, records = await _append_votes_bulk(
        connection,  # type: ignore[arg-type]
        dataset,
        "source-1",
        "snapshot-1",
    )

    assert (events, records) == (1, 2)
    party_query, party_arguments = next(
        call for call in connection.fetch_calls if "FROM parties" in call[0]
    )
    assert "WHERE source_id = ANY($1::text[])" in party_query
    assert "short_name" not in party_query
    assert party_arguments == (["party-source-1"],)
    record_statement, record_rows = connection.batches[-1]
    assert "INSERT INTO vote_records" in record_statement
    assert record_rows[0][5] is None
    assert record_rows[1][5] == "party-1"


@pytest.mark.asyncio
async def test_rejects_person_record_in_non_nominal_vote() -> None:
    dataset = _dataset(nominal=False)
    invalid_event = dataset.votes[0].model_copy(
        update={
            "records": [
                VoteRecord(
                    actor_label="Deputado Exemplo",
                    actor_source_id="dep-1",
                    actor_type=VoteActorType.PERSON,
                    choice=VoteChoice.FAVOR,
                )
            ]
        }
    )
    invalid_dataset = dataset.model_copy(update={"votes": [invalid_event]})
    connection = AsyncMock()
    connection.fetchval.side_effect = ["initiative-1", "vote-event-1"]

    with pytest.raises(RuntimeError, match="não nominal"):
        await ParliamentActivityRepository._append_votes(
            connection,
            invalid_dataset,
            "source-1",
            "snapshot-1",
        )


def test_normalised_digest_is_stable_and_bound_to_parser_version() -> None:
    dataset = _dataset()

    assert _dataset_digest(dataset) == _dataset_digest(dataset.model_copy(deep=True))
    assert _dataset_digest(dataset) != _dataset_digest(
        dataset.model_copy(update={"parser_version": "parliament-activity-v3"})
    )


def test_migration_enforces_versioned_append_only_parliament_snapshots() -> None:
    migration = (
        Path(__file__).parents[2]
        / "prisma"
        / "migrations"
        / "20260808090000_v4_parliament_activity_snapshots"
        / "migration.sql"
    ).read_text(encoding="utf-8")

    assert 'CREATE TABLE "parliament_activity_snapshots"' in migration
    assert "normalised_sha256_format" in migration
    assert 'DROP INDEX IF EXISTS "vote_events_source_id_key"' in migration
    assert '"vote_events_source_id_snapshot_id_key"' in migration
    for table in (
        "parliament_activity_snapshots",
        "parliamentary_membership_snapshots",
        "parliamentary_sessions",
        "parliamentary_initiatives",
        "vote_events",
        "vote_records",
    ):
        assert f'BEFORE UPDATE OR DELETE ON "{table}"' in migration
