from datetime import UTC, datetime
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
from app.repositories.parliament_activity import ParliamentActivityRepository


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
async def test_upserts_sessions_and_initiatives() -> None:
    connection = AsyncMock()
    dataset = _dataset()

    sessions = await ParliamentActivityRepository._upsert_sessions(
        connection, dataset, "source-1"
    )
    initiatives = await ParliamentActivityRepository._upsert_initiatives(
        connection, dataset, "source-1"
    )

    assert sessions == 1
    assert initiatives == 1
    assert connection.execute.await_count == 2


@pytest.mark.asyncio
async def test_persists_nominal_vote_only_as_person() -> None:
    connection = AsyncMock()
    connection.fetchval.side_effect = ["initiative-1", "vote-event-1", "person-1"]

    events, records = await ParliamentActivityRepository._upsert_votes(
        connection, _dataset(nominal=True), "source-1"
    )

    assert events == 1
    assert records == 1
    insert_call = connection.execute.await_args_list[-1]
    assert insert_call.args[3] == VoteActorType.PERSON.value
    assert insert_call.args[5] == "person-1"
    assert insert_call.args[6] is None


@pytest.mark.asyncio
async def test_persists_collective_vote_only_as_party() -> None:
    connection = AsyncMock()
    connection.fetchval.side_effect = ["initiative-1", "vote-event-1", "party-1"]

    events, records = await ParliamentActivityRepository._upsert_votes(
        connection, _dataset(nominal=False), "source-1"
    )

    assert events == 1
    assert records == 1
    insert_call = connection.execute.await_args_list[-1]
    assert insert_call.args[3] == VoteActorType.PARTY.value
    assert insert_call.args[5] is None
    assert insert_call.args[6] == "party-1"


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
        await ParliamentActivityRepository._upsert_votes(
            connection, invalid_dataset, "source-1"
        )
