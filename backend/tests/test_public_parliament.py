from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import HttpUrl

from app.models.api import OfficialSource, SourcePublisher, VoteActorType, VoteChoice
from app.models.public_parliament import (
    PublishedParliamentaryInitiative,
    PublishedParliamentarySession,
    PublishedParliamentaryVote,
    PublishedVoteRecord,
)
from app.repositories.public_parliament import PublicParliamentRepository, _vote_title


class QueryConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.arguments: list[tuple[object, ...]] = []

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, Any]]:
        self.queries.append(query)
        self.arguments.append(arguments)
        return []


class Acquire:
    def __init__(self, connection: QueryConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> QueryConnection:
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class Pool:
    def __init__(self, connection: QueryConnection) -> None:
        self.connection = connection

    def acquire(self) -> Acquire:
        return Acquire(self.connection)


@pytest.mark.asyncio
async def test_public_repository_rejects_missing_database() -> None:
    repository = PublicParliamentRepository(None)

    with pytest.raises(RuntimeError, match="Base de dados não configurada"):
        await repository.list_sessions(legislature="XVII", limit=10, offset=0)


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
        legislature="XVII",
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


def test_numeric_vote_title_uses_a_unique_linked_initiative() -> None:
    title = _vote_title(
        {
            "title": "815",
            "initiative_number": "815",
            "initiative_type": "Projeto de Lei",
            "initiative_title": "Título oficial da iniciativa",
        }
    )

    assert title == "Projeto de Lei n.º 815 — Título oficial da iniciativa"


@pytest.mark.parametrize(
    ("title", "initiative_title"),
    [
        ("Votação final global", "Título oficial da iniciativa"),
        ("815", None),
    ],
)
def test_vote_title_does_not_infer_without_an_unambiguous_match(
    title: str,
    initiative_title: str | None,
) -> None:
    assert (
        _vote_title(
            {
                "title": title,
                "initiative_number": "815",
                "initiative_type": "Projeto de Lei",
                "initiative_title": initiative_title,
            }
        )
        == title
    )


@pytest.mark.asyncio
async def test_all_public_lists_are_bound_to_one_reviewed_snapshot() -> None:
    connection = QueryConnection()
    repository = PublicParliamentRepository(Pool(connection))  # type: ignore[arg-type]

    await repository.list_sessions(legislature="XVII", limit=10, offset=0)
    await repository.list_initiatives(legislature="XVII", limit=10, offset=0)
    await repository.list_votes(legislature="XVII", limit=10, offset=0)

    assert connection.arguments == [("XVII", 10, 0)] * 3
    assert len(connection.queries) == 3
    for query in connection.queries:
        assert "WITH published_snapshot AS" in query
        assert "candidate.entity_id = snapshot.id" in query
        assert "candidate.source_document_id = source.id" in query
        assert "candidate.publishable = TRUE" not in query
        assert "review.publishable = TRUE" in query
        assert "attestation.content_sha256 = source.content_sha256" in query
        assert "published.id =" in query
    assert "HAVING COUNT(*) = 1" in connection.queries[-1]
