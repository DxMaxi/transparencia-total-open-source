"""Contrato HTTP da consulta pública V5.53, sem dados privados nem cache."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.api.routes import public_organisations
from app.main import app

PUBLIC_ID = "base_public_org_" + "a" * 32
RECORD_SHA = "b" * 64
SOURCE_SHA = "c" * 64
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


class ApiRepository:
    pool = object()


class FakePublicOrganisationRepository:
    def __init__(self, pool: object) -> None:
        assert pool is ApiRepository.pool

    async def list(self, *, limit: int, offset: int) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": PUBLIC_ID,
                    "legal_name": "Organização pública de ensaio",
                    "kind": "COMPANY",
                    "registry_record_id": "ACT-public-test",
                    "public_record_sha256": RECORD_SHA,
                    "published_at": NOW,
                }
            ],
            "total": 1,
            "limit": limit,
            "offset": offset,
        }

    async def get(self, *, public_id: str) -> dict[str, Any] | None:
        if public_id != PUBLIC_ID:
            return None
        return {
            "id": PUBLIC_ID,
            "legal_name": "Organização pública de ensaio",
            "kind": "COMPANY",
            "registry_record_id": "ACT-public-test",
            "official_url": "https://publicacoes.mj.pt/DetalhePublicacao.aspx",
            "source_record_sha256": SOURCE_SHA,
            "public_record_sha256": RECORD_SHA,
            "published_at": NOW,
            "source": {
                "publisher": "IRN",
                "title": "Ato público de ensaio",
                "url": "https://publicacoes.mj.pt/DetalhePublicacao.aspx",
                "retrieved_at": NOW,
                "content_sha256": SOURCE_SHA,
            },
            "replies": [],
        }

    async def history(self, *, public_id: str) -> dict[str, Any] | None:
        if public_id != PUBLIC_ID:
            return None
        return {
            "public_id": PUBLIC_ID,
            "items": [
                {
                    "public_id": PUBLIC_ID,
                    "action": "PUBLISH",
                    "public_record_sha256": RECORD_SHA,
                    "source_record_sha256": SOURCE_SHA,
                    "public_rationale": (
                        "Identificação factual mínima confirmada na fonte oficial."
                    ),
                    "actor_alias": "revisor-publico",
                    "occurred_at": NOW,
                }
            ],
            "replies": [],
        }


def test_public_organisation_routes_are_explicit_and_never_cached(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        public_organisations,
        "PublicOrganisationRepository",
        FakePublicOrganisationRepository,
    )
    app.dependency_overrides[get_repository] = ApiRepository
    try:
        with TestClient(app) as client:
            listing = client.get("/api/v1/public/organisations?limit=12&offset=0")
            detail = client.get(f"/api/v1/public/organisations/{PUBLIC_ID}")
            history = client.get(f"/api/v1/public/organisations/{PUBLIC_ID}/publication-history")
    finally:
        app.dependency_overrides.clear()

    assert listing.status_code == detail.status_code == history.status_code == 200
    for response in (listing, detail, history):
        assert response.headers["cache-control"] == "no-store, max-age=0, must-revalidate"
    assert listing.json()["total"] == 1
    assert detail.json()["source"]["publisher"] == "IRN"
    assert history.json()["items"][0]["action"] == "PUBLISH"
    serialised = f"{listing.text}{detail.text}{history.text}".casefold()
    assert "protected_identifier" not in serialised
    assert "observation_id" not in serialised
    assert "nipc" not in serialised


def test_invalid_or_unconfigured_public_organisation_is_fail_closed() -> None:
    class RepositoryWithoutDatabase:
        pool = None

    app.dependency_overrides[get_repository] = RepositoryWithoutDatabase
    try:
        with TestClient(app) as client:
            invalid = client.get("/api/v1/public/organisations/identificador-invalido")
            unavailable = client.get("/api/v1/public/organisations")
    finally:
        app.dependency_overrides.clear()

    assert invalid.status_code == 404
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == (
        "A consulta pública de organizações está temporariamente indisponível."
    )
