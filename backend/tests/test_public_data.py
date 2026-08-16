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
            "contract_version": "v5.6",
            "membership_observations": [
                {
                    "id": "membership-1",
                    "legislature": "XVII",
                    "parliamentary_name": "Pessoa Publicada",
                    "party": "Partido",
                    "party_short": "P",
                    "constituency": "Lisboa",
                    "observed_at": datetime(2026, 8, 1, tzinfo=UTC),
                    "verified_at": datetime(2026, 8, 2, tzinfo=UTC),
                    "source": self._source("https://www.parlamento.pt/"),
                }
            ],
            "mandates": [],
            "attendance": {
                "available": False,
                "record_count": 0,
                "present_count": 0,
                "absent_count": 0,
                "excused_count": 0,
                "attendance_rate": None,
                "observed_from": None,
                "observed_through": None,
                "note": "Sem registos individuais suficientes.",
                "source": None,
            },
            "attendance_rate": None,
            "attendance_label": "Sem registos individuais suficientes.",
            "nominal_votes_available": False,
            "nominal_vote_count": 0,
            "initiatives": [],
            "declarations": [],
            "declaration": None,
            "declaration_source": None,
            "declaration_lookup_source": {
                "publisher": "EPT",
                "label": "Entidade para a Transparência — portal oficial",
                "url": "https://www.tribunalconstitucional.pt/tc/ept/",
                "note": "Portal de pesquisa; não é prova individual.",
            },
            "coverage": self._coverage(),
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
            "observed_at": datetime(2026, 8, 1, tzinfo=UTC),
            "verified_at": datetime(2026, 8, 1, tzinfo=UTC),
            "profile_source": cls._source("https://www.parlamento.pt/"),
        }

    @classmethod
    def _coverage(cls) -> dict[str, Any]:
        unavailable = {
            "state": "UNAVAILABLE",
            "record_count": 0,
            "note": "Dados indisponíveis.",
            "observed_from": None,
            "observed_through": None,
            "source": None,
        }
        return {
            "identity": {
                "state": "AVAILABLE",
                "record_count": 1,
                "note": "Identidade observada e revista.",
                "observed_from": datetime(2026, 8, 1, tzinfo=UTC),
                "observed_through": datetime(2026, 8, 1, tzinfo=UTC),
                "source": cls._source("https://www.parlamento.pt/"),
            },
            "membership_observations": {
                "state": "AVAILABLE",
                "record_count": 1,
                "note": "Uma observação oficial revista.",
                "observed_from": datetime(2026, 8, 1, tzinfo=UTC),
                "observed_through": datetime(2026, 8, 1, tzinfo=UTC),
                "source": cls._source("https://www.parlamento.pt/"),
            },
            "mandates": dict(unavailable),
            "attendance": dict(unavailable),
            "initiatives": dict(unavailable),
            "nominal_votes": dict(unavailable),
            "declarations": dict(unavailable),
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
    assert list_response.json()[0]["observed_at"].startswith("2026-08-01")
    assert profile_response.status_code == 200
    assert profile_response.json()["contract_version"] == "v5.6"
    assert profile_response.json()["coverage"]["mandates"]["state"] == "UNAVAILABLE"
    assert profile_response.json()["declarations"] == []
    assert profile_response.json()["declaration"] is None
    assert profile_response.json()["declaration_source"] is None
    assert "não é prova" in profile_response.json()["declaration_lookup_source"]["note"]
    assert profile_response.json()["attendance_rate"] is None
    assert profile_response.json()["nominal_votes_available"] is False
    assert profile_response.json()["nominal_vote_count"] == 0
    assert profile_response.json()["votes"] == []
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


def test_status_database_failure_returns_controlled_503() -> None:
    class FailingRepository:
        async def get_public_data_status(self) -> dict[str, Any]:
            raise OSError("internal database connection details")

    app.dependency_overrides[get_repository] = lambda: FailingRepository()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/public/data-status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "O servi\u00e7o de dados est\u00e1 temporariamente indispon\u00edvel."
    )
    assert "internal database connection details" not in response.text
