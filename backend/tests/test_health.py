import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.5.0-alpha.0"
    assert response.json()["public_capabilities"] == [
        "parliament_explorer_v1",
        "parliament_publication_history_v1",
    ]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-xss-protection"] == "0"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-resource-policy"] == "same-site"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "strict-transport-security" not in response.headers


def test_push_broadcast_requires_admin_configuration() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/push/broadcast",
            json={"title": "Alerta", "body": "Atualização oficial", "url": "/"},
        )
    assert response.status_code in {401, 503}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/parliament/deputies?legislature=XVII",
        "/api/v1/parliament/votes?legislature=XVII",
        "/api/v1/dre/document?source_url=https://diariodarepublica.pt/",
        "/api/v1/dre/rss",
        "/api/v1/transparency-entity/resources",
    ],
)
def test_ingestion_adapters_require_admin_key(path: str) -> None:
    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code in {401, 503}


def test_civic_guide_is_disabled_by_default() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/civic-guide",
            json={
                "profile": {
                    "irs_bracket": "nao_indicar",
                    "district": "Lisboa",
                    "children": 0,
                    "dependants": 0,
                    "employment_status": "nao_indicar",
                },
                "verified_facts": [
                    {
                        "fact_id": "DRE.DEMO.1",
                        "title": "Facto demonstrativo",
                        "deterministic_result": "Sem cálculo aplicável",
                        "effective_date": "2026-01-01",
                        "official_source_url": "https://diariodarepublica.pt/",
                        "source_anchor": "Artigo 1.º",
                        "caveats": [],
                    }
                ],
            },
        )
    assert response.status_code == 503
