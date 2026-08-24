import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_repository
from app.api.routes import public_data
from app.main import app
from app.models.public_search import PublishedGlobalSearch
from app.repositories import public_search
from app.repositories.public_search import PublicGlobalSearchRepository


def _source() -> dict[str, Any]:
    return {
        "publisher": "AR",
        "label": "Assembleia da República — fonte oficial",
        "url": "https://www.parlamento.pt/dados.json",
        "retrieved_at": datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        "content_sha256": "a" * 64,
    }


def _section(kind: str, *, total: int = 0) -> dict[str, object]:
    labels = {
        "politicians": "Políticos",
        "parliament_sessions": "Reuniões parlamentares",
        "parliament_initiatives": "Iniciativas parlamentares",
        "parliament_votes": "Votações parlamentares",
        "promises": "Promessómetro",
        "ai_explanations": "Explicações com IA revistas",
    }
    paths = {
        "politicians": "/politicos?q=habitação",
        "parliament_sessions": "/atividade-parlamentar?tipo=sessoes&q=habita%C3%A7%C3%A3o",
        "parliament_initiatives": "/atividade-parlamentar?tipo=iniciativas&q=habita%C3%A7%C3%A3o",
        "parliament_votes": "/atividade-parlamentar?tipo=votacoes&q=habita%C3%A7%C3%A3o",
        "promises": "/promessas?q=habita%C3%A7%C3%A3o",
        "ai_explanations": "/explicacoes?q=habita%C3%A7%C3%A3o",
    }
    return {
        "kind": kind,
        "label": labels[kind],
        "availability": "AVAILABLE",
        "total": total,
        "total_is_exact": True,
        "items": [],
        "view_all_href": paths[kind],
        "coverage_note": "Apenas projeções oficiais publicadas.",
    }


class ApiRepository:
    pool = object()


class FakeGlobalSearchRepository:
    def __init__(self, pool: object) -> None:
        assert pool is ApiRepository.pool

    async def search(self, **arguments: object) -> dict[str, object]:
        assert arguments == {
            "query": "habitação",
            "legislature": "XVII",
            "section_limit": 5,
        }
        sections = [_section(kind) for kind in public_search._SECTION_ORDER]
        sections[0]["total"] = 1
        sections[0]["items"] = [
            {
                "id": "person-1",
                "kind": "politicians",
                "title": "Pessoa Publicada",
                "description": "Partido · Lisboa · Legislatura XVII",
                "href": "/politicos/pessoa-publicada",
                "source": _source(),
                "verified_at": datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
                "observed_at": datetime(2026, 8, 19, 10, 0, tzinfo=UTC),
                "coverage_note": "Identificador oficial preservado.",
            }
        ]
        return {
            "query": "habitação",
            "legislature": "XVII",
            "section_limit": 5,
            "total_results": 1,
            "available_sections": 6,
            "unavailable_sections": 0,
            "sections": sections,
        }


def test_global_search_endpoint_exposes_only_the_published_projection(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(public_data, "PublicGlobalSearchRepository", FakeGlobalSearchRepository)
    app.dependency_overrides[get_repository] = ApiRepository
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/public/search", params={"q": " habitação "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "habitação"
    assert payload["total_results"] == 1
    assert payload["sections"][0]["items"][0]["href"] == "/politicos/pessoa-publicada"
    assert payload["sections"][0]["items"][0]["source"]["content_sha256"] == "a" * 64
    assert "não cria associações" in payload["search_rule"]


def test_global_search_result_requires_collection_date_and_sha256() -> None:
    sections = [_section(kind) for kind in public_search._SECTION_ORDER]
    sections[0]["total"] = 1
    sections[0]["items"] = [
        {
            "id": "person-1",
            "kind": "politicians",
            "title": "Pessoa Publicada",
            "description": "Identidade oficial",
            "href": "/politicos/pessoa-publicada",
            "source": {
                "publisher": "AR",
                "label": "Fonte oficial",
                "url": "https://www.parlamento.pt/",
            },
            "verified_at": datetime(2026, 8, 20, tzinfo=UTC),
            "coverage_note": "Identidade publicada.",
        }
    ]
    payload = {
        "query": "habitação",
        "legislature": "XVII",
        "section_limit": 5,
        "total_results": 1,
        "available_sections": 6,
        "unavailable_sections": 0,
        "sections": sections,
    }

    with pytest.raises(ValidationError):
        PublishedGlobalSearch.model_validate(payload)


def test_global_search_rejects_blank_terms_after_normalisation() -> None:
    app.dependency_overrides[get_repository] = ApiRepository
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/public/search", params={"q": "  "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_global_search_returns_controlled_503_when_every_projection_fails(
    monkeypatch: Any,
) -> None:
    class FailingSearchRepository:
        def __init__(self, _pool: object) -> None:
            pass

        async def search(self, **_arguments: object) -> dict[str, object]:
            return {"available_sections": 0}

    monkeypatch.setattr(public_data, "PublicGlobalSearchRepository", FailingSearchRepository)
    app.dependency_overrides[get_repository] = ApiRepository
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/public/search", params={"q": "habitação"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "A pesquisa pública está temporariamente indisponível."


class PromiseAcquire:
    def __init__(self, connection: "PromiseConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "PromiseConnection":
        return self.connection

    async def __aexit__(self, *_arguments: object) -> None:
        return None


class PromiseConnection:
    def __init__(self) -> None:
        self.query = ""
        self.arguments: tuple[object, ...] = ()

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, object]:
        self.query = query
        self.arguments = arguments
        return {
            "total": 1,
            "items": json.dumps(
                [
                    {
                        "id": "promise-1",
                        "title": "Apoiar 100%_! da habitação",
                        "area": "Habitação",
                        "status": "UNVERIFIED",
                        "reviewed_at": "2026-08-20T10:00:00+00:00",
                        "source_publisher": "DRE",
                        "source_url": "https://diariodarepublica.pt/documento-oficial",
                        "source_retrieved_at": "2026-08-20T09:00:00+00:00",
                        "source_sha256": "b" * 64,
                    }
                ]
            ),
        }


class PromisePool:
    def __init__(self, connection: PromiseConnection) -> None:
        self.connection = connection

    def acquire(self) -> PromiseAcquire:
        return PromiseAcquire(self.connection)


def test_promise_search_keeps_review_archive_and_bound_query_gates() -> None:
    connection = PromiseConnection()
    repository = PublicGlobalSearchRepository(PromisePool(connection))  # type: ignore[arg-type]

    result = asyncio.run(repository._search_promises(query="100%_!", limit=5))

    assert result["total"] == 1
    assert result["items"][0]["source"]["content_sha256"] == "b" * 64  # type: ignore[index]
    assert "latest_review.decision = 'ACCEPT'" in connection.query
    assert connection.query.count("source_archive_attestations") == 2
    assert "'NOT_STARTED'" in connection.query
    assert "'PARTIAL'" in connection.query
    assert "'BROKEN'" not in connection.query
    assert "'ABANDONED'" not in connection.query
    assert "similarity" not in connection.query.casefold()
    assert connection.arguments == ("%100!%!_!!%", 5)


def test_partial_source_failure_is_visible_and_does_not_hide_other_sections(
    monkeypatch: Any,
) -> None:
    class Politicians:
        def __init__(self, _pool: object) -> None:
            pass

        async def explore(self, **_arguments: object) -> dict[str, object]:
            return {"items": [], "total": 0}

    class Parliament:
        def __init__(self, _pool: object) -> None:
            pass

        async def search_global(self, **_arguments: object) -> dict[str, object]:
            return {
                "sessions": {"items": [], "total": 0},
                "initiatives": {"items": [], "total": 0},
                "votes": {"items": [], "total": 0},
            }

    class MissingAiSchema:
        def __init__(self, _pool: object) -> None:
            pass

        async def list_explanations(self, **_arguments: object) -> dict[str, object]:
            raise asyncpg.UndefinedTableError('relation "editorial_cases" does not exist')

    class Repository(PublicGlobalSearchRepository):
        async def _search_promises(self, **_arguments: object) -> dict[str, object]:
            return _section("promises")

    monkeypatch.setattr(public_search, "PublicPoliticianRepository", Politicians)
    monkeypatch.setattr(public_search, "PublicParliamentRepository", Parliament)
    monkeypatch.setattr(public_search, "PublicAiExplanationRepository", MissingAiSchema)
    result = asyncio.run(
        Repository(object()).search(query="habitação", legislature="XVII", section_limit=5)  # type: ignore[arg-type]
    )

    parsed = PublishedGlobalSearch.model_validate(result)
    ai_section = next(section for section in parsed.sections if section.kind == "ai_explanations")
    assert parsed.available_sections == 5
    assert parsed.unavailable_sections == 1
    assert ai_section.availability == "UNAVAILABLE"
    assert ai_section.total is None
    assert ai_section.items == []
    assert "Dados temporariamente indisponíveis" in ai_section.coverage_note
