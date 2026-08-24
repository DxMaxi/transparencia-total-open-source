from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import HttpUrl

from app.models.api import OfficialSource, SourcePublisher, VoteActorType, VoteChoice
from app.models.public_parliament import (
    PublishedParliamentaryInitiative,
    PublishedParliamentarySession,
    PublishedParliamentaryVote,
    PublishedParliamentCoverageRow,
    PublishedParliamentExplorer,
    PublishedParliamentPublicationHistoryItem,
    PublishedVoteRecord,
)
from app.repositories.public_parliament import (
    PublicParliamentRepository,
    _like_pattern,
    _sha256_json,
    _vote_title,
)


class QueryConnection:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.queries: list[str] = []
        self.arguments: list[tuple[object, ...]] = []
        self.rows = rows or []

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, Any]]:
        self.queries.append(query)
        self.arguments.append(arguments)
        return self.rows


class ExplorerConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.arguments: list[tuple[object, ...]] = []

    async def fetchval(self, query: str, *arguments: object) -> int:
        self.queries.append(query)
        self.arguments.append(arguments)
        return 1

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, Any]]:
        self.queries.append(query)
        self.arguments.append(arguments)
        if "SELECT event.id" in query:
            return [
                {
                    "id": "vote-1",
                    "source_id": "vote-source-1",
                    "legislature": "XVII",
                    "title": "815",
                    "initiative_number": "815",
                    "voted_at": datetime(2026, 8, 10, 15, 0, tzinfo=UTC),
                    "result": "Aprovado",
                    "is_nominal": False,
                    "verified_at": datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
                    "source_url": "https://www.parlamento.pt/dados.json",
                    "source_retrieved_at": datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
                    "source_sha256": "a" * 64,
                    "initiative_type": "Projeto de Lei",
                    "initiative_title": "Título oficial da iniciativa",
                    "initiative_status": "Aprovada",
                    "initiative_official_url": "https://www.parlamento.pt/iniciativa/815",
                }
            ]
        if "SELECT record.vote_event_id" in query:
            return [
                {
                    "vote_event_id": "vote-1",
                    "actor_label": "Grupo Parlamentar de teste",
                    "actor_type": "PARTY",
                    "choice": "FAVOR",
                    "person_source_id": None,
                    "party_source_id": "party-official-1",
                }
            ]
        raise AssertionError("Consulta inesperada no teste do explorador")


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
                party_source_id="party-official-ps",
            )
        ],
        initiative_type="Projeto de Lei",
        initiative_title="Título oficial",
        initiative_status="Aprovada",
        initiative_official_url="https://www.parlamento.pt/iniciativa/1",
        verified_at=datetime(2026, 8, 6, 11, 0, tzinfo=UTC),
        source=official_source,
    )

    assert session.source.content_sha256 == "a" * 64
    assert initiative.status is None
    assert vote.records[0].actor_type is VoteActorType.PARTY
    assert vote.records[0].person_source_id is None
    assert vote.records[0].party_source_id == "party-official-ps"
    assert vote.initiative_title == "Título oficial"


def test_public_search_escapes_like_metacharacters_as_text() -> None:
    assert _like_pattern("100%_!") == "%100!%!_!!%"


@pytest.mark.asyncio
async def test_vote_explorer_filters_parties_only_by_exact_official_id_and_batches_records() -> (
    None
):
    connection = ExplorerConnection()
    repository = PublicParliamentRepository(None)

    votes, total = await repository._explore_votes(
        connection,
        legislature="XVII",
        query="100%_!",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 11),
        initiative_type="Projeto de Lei",
        vote_result="Aprovado",
        is_nominal=False,
        party_source_id="party-official-1",
        choice="FAVOR",
        limit=20,
        offset=0,
    )

    assert total == 1
    assert len(votes) == 1
    parsed = PublishedParliamentaryVote.model_validate(votes[0])
    assert parsed.title == "Projeto de Lei n.º 815 — Título oficial da iniciativa"
    assert parsed.records[0].party_source_id == "party-official-1"
    count_query, page_query, record_query = connection.queries
    assert "party.source_id =" in count_query
    assert "published.parser_version = 'parliament-activity-v5'" in count_query
    assert "record.actor_label =" not in count_query
    assert "HAVING COUNT(*) = 1" in page_query
    assert "record.vote_event_id = ANY($1::text[])" in record_query
    assert "snapshot.parser_version = 'parliament-activity-v5'" in record_query
    assert connection.arguments[0][1] == "%100!%!_!!%"
    assert connection.arguments[-1] == (["vote-1"],)


def test_explorer_model_keeps_topics_unavailable_without_inference() -> None:
    explorer = PublishedParliamentExplorer.model_validate(
        {
            "kind": "votes",
            "legislature": "XVII",
            "sessions": [],
            "initiatives": [],
            "votes": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
            "facets": {
                "legislatures": ["XVII"],
                "initiative_types": [],
                "initiative_statuses": [],
                "vote_results": [],
                "parties": [],
            },
        }
    )

    assert explorer.facets.topics_available is False
    assert "não o deduz" in explorer.facets.topics_note
    assert "dados indisponíveis" in explorer.explanation_rule


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


@pytest.mark.asyncio
async def test_coverage_matrix_uses_only_latest_attested_publications() -> None:
    common = {
        "id": "snapshot-1",
        "source_document_id": "source-1",
        "legislature": "XVII",
        "collected_at": datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        "normalised_sha256": "b" * 64,
        "session_count": 237,
        "initiative_count": 2100,
        "vote_count": 2473,
        "vote_record_count": 19998,
        "verified_at": datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
        "source_url": "https://www.parlamento.pt/dados.json",
        "source_retrieved_at": datetime(2026, 8, 20, 8, 30, tzinfo=UTC),
        "source_sha256": "a" * 64,
        "sessions_from": date(2025, 6, 3),
        "sessions_through": date(2026, 8, 20),
        "initiatives_from": date(2025, 6, 4),
        "initiatives_through": date(2026, 8, 19),
        "votes_from": date(2025, 6, 5),
        "votes_through": date(2026, 8, 18),
    }
    connection = QueryConnection(
        [
            {**common, "scope": "activity"},
            {**common, "id": "snapshot-2", "scope": "votes"},
        ]
    )
    repository = PublicParliamentRepository(Pool(connection))  # type: ignore[arg-type]

    coverage = await repository.list_coverage(limit=10)

    assert connection.arguments == [(10,)]
    assert len(coverage) == 4
    assert [row["record_kind"] for row in coverage] == [
        "sessions",
        "initiatives",
        "votes",
        "vote_records",
    ]
    assert [row["published_count"] for row in coverage] == [237, 2100, 2473, 19998]
    for row in coverage:
        parsed = PublishedParliamentCoverageRow.model_validate(row)
        assert parsed.count_is_exact is True
        assert parsed.historical_completeness == "NOT_ASSERTED"
        assert parsed.source.content_sha256 == "a" * 64
        assert parsed.snapshot_sha256 == "b" * 64

    query = connection.queries[0]
    assert "WITH latest_reviews AS" in query
    assert "review.publishable = TRUE" in query
    assert "attestation.content_sha256 = source.content_sha256" in query
    assert "attestation.retrieval_url = source.url" in query
    assert "PARTITION BY snapshot.legislature, review.entity_type" in query
    assert "session.source_document_id = published.source_document_id" in query
    assert "initiative.source_document_id = published.source_document_id" in query
    assert "event.source_document_id = published.source_document_id" in query
    assert query.count("COUNT(*) AS actual_count") == 3
    assert "actual_record_count" in query
    assert "session_period.actual_count = published.session_count" in query
    assert "initiative_period.actual_count = published.initiative_count" in query
    assert "vote_period.actual_count = published.vote_count" in query
    assert "vote_period.actual_record_count = published.vote_record_count" in query
    assert "similarity(" not in query
    assert "levenshtein" not in query


@pytest.mark.asyncio
async def test_public_withdrawal_history_redacts_private_editorial_link() -> None:
    public_effect = {
        "kind": "DATA_UNAVAILABLE",
        "scope": "activity",
        "legislature": "XVII",
        "message": "Depois da retirada, os dados ficam indisponíveis neste âmbito.",
    }
    connection = QueryConnection(
        [
            {
                "id": "audit-private-id",
                "entity_id": "snapshot-private-id",
                "action": "WITHDRAWN",
                "actor_alias": "admin-teste",
                "after_json": {
                    "publishable": False,
                    "scope": "activity",
                    "legislature": "XVII",
                    "source_sha256": "a" * 64,
                    "normalised_sha256": "b" * 64,
                    "counts": {
                        "sessions": 2,
                        "initiatives": 3,
                        "votes": 4,
                        "vote_records": 5,
                    },
                    "editorial_link": {
                        "case_id": "case-private-id",
                        "version_id": "version-private-id",
                        "withdrawal_reason_category": "SOURCE_DIVERGENCE",
                        "public_effect": public_effect,
                        "public_effect_sha256": _sha256_json(public_effect),
                    },
                },
                "reason": "Fotografia retirada por divergência reproduzível com a fonte.",
                "created_at": datetime(2026, 8, 11, 13, 0, tzinfo=UTC),
                "source_url": "https://www.parlamento.pt/dados.json",
                "source_retrieved_at": datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
                "source_sha256": "a" * 64,
            }
        ]
    )
    repository = PublicParliamentRepository(Pool(connection))  # type: ignore[arg-type]

    history = await repository.list_publication_history(legislature="XVII", limit=10)

    assert len(history) == 1
    item = PublishedParliamentPublicationHistoryItem.model_validate(history[0])
    assert item.action == "WITHDRAWN"
    assert item.reason_category == "SOURCE_DIVERGENCE"
    assert item.public_effect is not None
    assert item.public_effect.kind == "DATA_UNAVAILABLE"
    assert "case_id" not in history[0]
    assert "version_id" not in history[0]
    assert connection.arguments == [("XVII", 10)]
