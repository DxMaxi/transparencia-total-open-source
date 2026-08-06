from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from app.models.api import OfficialSource, SourcePublisher, VoteActorType, VoteChoice
from app.models.public_parliament import (
    PublishedParliamentaryInitiative,
    PublishedParliamentarySession,
    PublishedParliamentaryVote,
    PublishedVoteRecord,
)
from app.repositories.public_parliament import PublicParliamentRepository


@pytest.mark.asyncio
async def test_public_repository_rejects_missing_database() -> None:
    repository = PublicParliamentRepository(None)

    with pytest.raises(RuntimeError, match="Base de dados não configurada"):
        await repository.list_sessions(limit=10, offset=0)


@pytest.fixture
def official_source() -> OfficialSource:
    return OfficialSource(
        publisher=SourcePublisher.PARLIAMENT,
        label="Assembleia da República — fonte oficial",
        url=HttpUrl("https://www.parlamento.pt/dados.json"),
        retrieved_at=datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
        content_sha256="a" * 64,
    )


def test_public_models_preserve_source_and_actor_scope(
    official_source: OfficialSource,
) -> None:
    session = PublishedParliamentarySession(
        id="session-1",
        source_id="reu-1",
        legislature="XVII",
        title="Reunião plenária",
        starts_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        verified_at=datetime(2026, 8, 6, 11, 0, tzinfo=UTC),
        source=official_source,
    )
    initiative = PublishedParliamentaryInitiative(
        id="initiative-1",
        source_id="ini-1",
        legislature="XVII",
        number="1/XVII/1",
        initiative_type="Projeto de Lei",
        title="Título oficial",
        official_url="https://www.parlamento.pt/iniciativa/1",
        verified_at=datetime(2026, 8, 6, 11, 0, tzinfo=UTC),
        source=official_source,
    )
    vote = PublishedParliamentaryVote(
        id="vote-1",
        source_id="vot-1",
        title="Votação final global",
        is_nominal=False,
        records=[
            PublishedVoteRecord(
                actor_label="PS",
                actor_type=VoteActorType.PARTY,
                choice=VoteChoice.FAVOR,
                party_id="party-ps",
            )
        ],
        verified_at=datetime(2026, 8, 6, 11, 0, tzinfo=UTC),
        source=official_source,
    )

    assert session.source.content_sha256 == "a" * 64
    assert initiative.status is None
    assert vote.records[0].actor_type is VoteActorType.PARTY
    assert vote.records[0].person_id is None
