import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.api.routes import public_data
from app.main import app
from app.repositories.public_politicians import (
    PublicPoliticianCursorError,
    PublicPoliticianRepository,
)


def _raw_person(index: int) -> dict[str, Any]:
    return {
        "id": f"person-{index}",
        "slug": f"pessoa-{index}",
        "name": f"Pessoa {index}",
        "sort_name": f"pessoa {index}",
        "role": "DEPUTY",
        "photo_url": None,
        "party": "Partido de Teste",
        "party_short": "PT",
        "constituency": "Lisboa",
        "legislature": "XVII",
        "observed_at": "2026-08-01T10:00:00+00:00",
        "verified_at": "2026-08-02T10:00:00+00:00",
        "source_publisher": "PARLIAMENT",
        "source_url": "https://www.parlamento.pt/",
        "source_retrieved_at": "2026-08-01T09:00:00+00:00",
        "source_sha256": "a" * 64,
    }


class DirectoryPool:
    def __init__(self, *, items: list[dict[str, Any]], total: int) -> None:
        self.items = items
        self.total = total
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any]:
        self.calls.append((query, arguments))
        return {
            "total": self.total,
            "items": json.dumps(self.items),
            "parties": json.dumps(
                [{"value": "PT", "label": "Partido de Teste", "count": self.total}]
            ),
        }


def test_directory_uses_bound_keyset_cursor_and_exact_published_total() -> None:
    pool = DirectoryPool(items=[_raw_person(1), _raw_person(2), _raw_person(3)], total=7)
    repository = PublicPoliticianRepository(pool)  # type: ignore[arg-type]

    first = asyncio.run(
        repository.explore(
            query="100%_!",
            party_short="PT",
            limit=2,
            cursor=None,
        )
    )

    assert first["total"] == 7
    assert first["limit"] == 2
    assert len(first["items"]) == 2
    assert first["next_cursor"]
    assert first["parties"] == [{"value": "PT", "label": "Partido de Teste", "count": 7}]
    query, arguments = pool.calls[0]
    assert "source_archive_attestations" in query
    assert "archive.retrieved_at = source.retrieved_at" in query
    assert "profile_archive.retrieved_at = source.retrieved_at" in query
    assert "(sort_name, slug)" in query
    assert "OFFSET" not in query.upper()
    assert "similarity" not in query.casefold()
    assert arguments[0] == "%100!%!_!!%"
    assert arguments[1] == "PT"
    assert arguments[4] == 3

    cursor = str(first["next_cursor"])
    asyncio.run(
        repository.explore(
            query="100%_!",
            party_short="PT",
            limit=2,
            cursor=cursor,
        )
    )
    _, second_arguments = pool.calls[1]
    assert second_arguments[2] == "pessoa 2"
    assert second_arguments[3] == "pessoa-2"


def test_cursor_is_rejected_when_filters_change_or_payload_is_invalid() -> None:
    pool = DirectoryPool(items=[_raw_person(1), _raw_person(2)], total=2)
    repository = PublicPoliticianRepository(pool)  # type: ignore[arg-type]
    page = asyncio.run(repository.explore(query=None, party_short=None, limit=1, cursor=None))
    cursor = str(page["next_cursor"])

    with pytest.raises(PublicPoliticianCursorError):
        asyncio.run(
            repository.explore(
                query="outro filtro",
                party_short=None,
                limit=1,
                cursor=cursor,
            )
        )
    with pytest.raises(PublicPoliticianCursorError):
        asyncio.run(
            repository.explore(
                query=None,
                party_short=None,
                limit=1,
                cursor="não-é-base64",
            )
        )
    boolean_version_cursor = base64.urlsafe_b64encode(
        json.dumps([True, "pessoa", "pessoa-1", "0" * 24]).encode("utf-8")
    ).decode("ascii")
    with pytest.raises(PublicPoliticianCursorError):
        asyncio.run(
            repository.explore(
                query=None,
                party_short=None,
                limit=1,
                cursor=boolean_version_cursor,
            )
        )
    assert len(pool.calls) == 1


def test_public_endpoint_returns_422_for_an_invalid_cursor() -> None:
    class RepositoryWithoutDatabase:
        pool = None

    app.dependency_overrides[get_repository] = RepositoryWithoutDatabase
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/public/politicians/explore",
                params={"cursor": "não-é-base64"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Cursor de paginação inválido"


class ApiRepository:
    pool = object()


class ApiDirectoryRepository:
    def __init__(self, pool: object) -> None:
        assert pool is ApiRepository.pool

    async def explore(self, **arguments: object) -> dict[str, object]:
        assert arguments == {
            "query": "Pessoa",
            "party_short": "PT",
            "limit": 12,
            "cursor": None,
        }
        source = {
            "publisher": "AR",
            "label": "Assembleia da República — fonte oficial",
            "url": "https://www.parlamento.pt/",
            "retrieved_at": datetime(2026, 8, 1, tzinfo=UTC),
            "content_sha256": "a" * 64,
        }
        return {
            "items": [
                {
                    "id": "person-1",
                    "slug": "pessoa-1",
                    "name": "Pessoa 1",
                    "role": "DEPUTY",
                    "party": "Partido de Teste",
                    "party_short": "PT",
                    "constituency": "Lisboa",
                    "legislature": "XVII",
                    "observed_at": datetime(2026, 8, 1, tzinfo=UTC),
                    "verified_at": datetime(2026, 8, 2, tzinfo=UTC),
                    "profile_source": source,
                }
            ],
            "total": 1,
            "limit": 12,
            "next_cursor": None,
            "query": "Pessoa",
            "party_short": "PT",
            "parties": [{"value": "PT", "label": "Partido de Teste", "count": 1}],
        }


def test_public_endpoint_exposes_cursor_contract_without_internal_matching(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(public_data, "PublicPoliticianRepository", ApiDirectoryRepository)
    app.dependency_overrides[get_repository] = ApiRepository
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/public/politicians/explore",
                params={"q": " Pessoa ", "party_short": " PT ", "limit": 12},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["total_is_exact"] is True
    assert payload["pagination"] == "CURSOR"
    assert payload["items"][0]["slug"] == "pessoa-1"
    assert "não cria" in payload["search_rule"].casefold()
