from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.main import app


class FakePublicRepository:
    async def get_public_data_status(self) -> dict[str, Any]:
        return {
            "mode": "LIVE",
            "database_configured": True,
            "counts": {
                "politicians": 1,
                "promises": 0,
                "contracts": 0,
                "relationships": 0,
                "news": 0,
                "citizen_alerts": 0,
            },
            "sources": [
                {
                    "source_name": "PARLIAMENT_DEPUTIES",
                    "status": "SUCCEEDED",
                    "records_read": 230,
                    "records_written": 230,
                    "warning_count": 0,
                    "dataset_url": "https://www.parlamento.pt/",
                    "code_version": "test-v3",
                }
            ],
            "message": "1 registo aprovado.",
        }

    async def list_public_politicians(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        assert limit == 100
        assert offset == 0
        return [self._person()]

    async def get_public_politician(self, slug: str) -> dict[str, Any] | None:
        if slug != "pessoa-publicada":
            return None
        return {
            **self._person(),
            "attendance_rate": None,
            "attendance_label": "Sem registos individuais suficientes.",
            "declaration_source": self._source("https://www.tribunalconstitucional.pt/tc/ept/"),
            "votes": [],
        }

    async def list_public_promises(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        return []

    async def get_public_investigator_dataset(self, *, limit: int) -> dict[str, Any]:
        return {"nodes": [], "edges": [], "comparisons": []}

    @classmethod
    def _person(cls) -> dict[str, Any]:
        return {
            "id": "person-1",
            "slug": "pessoa-publicada",
            "name": "Pessoa Publicada",
            "role": "DEPUTY",
            "party": "Partido",
            "party_short": "P",
            "constituency": "Lisboa",
            "legislature": "XVII",
            "portrait_url": None,
            "verified_at": datetime(2026, 8, 1, tzinfo=UTC),
            "profile_source": cls._source("https://www.parlamento.pt/"),
        }

    @staticmethod
    def _source(url: str) -> dict[str, Any]:
        return {
            "publisher": "AR" if "parlamento" in url else "EPT",
            "label": "Fonte oficial",
            "url": url,
            "retrieved_at": datetime(2026, 8, 1, tzinfo=UTC),
            "content_sha256": "a" * 64,
        }


def test_public_status_and_profiles_have_explicit_contract() -> None:
    fake = FakePublicRepository()
    app.dependency_overrides[get_repository] = lambda: fake
    try:
        with TestClient(app) as client:
            status_response = client.get("/api/v1/public/data-status")
            list_response = client.get("/api/v1/public/politicians")
            profile_response = client.get("/api/v1/public/politicians/pessoa-publicada")
            missing_response = client.get("/api/v1/public/politicians/nao-existe")
    finally:
        app.dependency_overrides.clear()

    assert status_response.status_code == 200
    assert status_response.json()["mode"] == "LIVE"
    assert status_response.json()["counts"]["politicians"] == 1
    assert list_response.status_code == 200
    assert list_response.json()[0]["profile_source"]["url"].startswith("https://")
    assert profile_response.status_code == 200
    assert profile_response.json()["attendance_rate"] is None
    assert missing_response.status_code == 404


def test_status_never_claims_live_data_without_database() -> None:
    class UnconfiguredRepository:
        async def get_public_data_status(self) -> dict[str, Any]:
            return {
                "mode": "UNAVAILABLE",
                "database_configured": False,
                "counts": {},
                "sources": [],
                "message": "Base de dados não configurada.",
            }

    app.dependency_overrides[get_repository] = lambda: UnconfiguredRepository()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/public/data-status")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["mode"] == "UNAVAILABLE"
    assert response.json()["database_configured"] is False
