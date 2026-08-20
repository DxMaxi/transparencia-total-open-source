import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.main import app
from app.repositories.official_index_staging import OfficialIndexStagingRepository


def test_health_contract() -> None:
    class UnconfiguredRepository:
        pool = None

        async def connect(self) -> None:
            return None

    app.dependency_overrides[get_repository] = UnconfiguredRepository
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

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


class _SchemaConnection:
    def __init__(self, result: bool | Exception) -> None:
        self.result = result
        self.arguments: tuple[object, ...] | None = None

    async def fetchval(self, _query: str, *arguments: object) -> bool:
        self.arguments = arguments
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _SchemaAcquire:
    def __init__(self, connection: _SchemaConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _SchemaConnection:
        return self.connection

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        return None


class _SchemaPool:
    def __init__(self, connection: _SchemaConnection) -> None:
        self.connection = connection

    def acquire(self) -> _SchemaAcquire:
        return _SchemaAcquire(self.connection)


class _SchemaRepository:
    def __init__(self, result: bool | Exception) -> None:
        self.connection = _SchemaConnection(result)
        self.pool = _SchemaPool(self.connection)


def test_health_advertises_ai_only_after_schema_and_migrations_are_ready() -> None:
    repository = _SchemaRepository(True)
    app.dependency_overrides[get_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["public_capabilities"] == [
        "parliament_explorer_v1",
        "parliament_publication_history_v1",
        "ai_explanations_v1",
    ]
    assert repository.connection.arguments is not None
    required_relations, relation_count, required_migrations, migration_count = (
        repository.connection.arguments
    )
    assert isinstance(required_relations, list)
    assert isinstance(relation_count, int)
    assert isinstance(required_migrations, list)
    assert isinstance(migration_count, int)
    assert relation_count == len(required_relations)
    assert migration_count == len(required_migrations)
    assert "public.editorial_cases" in required_relations
    assert "20260811110000_v5_editorial_foundation" in required_migrations


@pytest.mark.parametrize("result", [False, OSError("catalogue unavailable")])
def test_health_hides_ai_when_schema_readiness_is_not_proven(
    result: bool | Exception,
) -> None:
    repository = _SchemaRepository(result)
    app.dependency_overrides[get_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["public_capabilities"] == [
        "parliament_explorer_v1",
        "parliament_publication_history_v1",
    ]


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


def test_database_outage_keeps_process_live_and_readiness_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_connect(self: OfficialIndexStagingRepository) -> None:
        raise OSError("database unavailable")

    monkeypatch.setattr(OfficialIndexStagingRepository, "connect", fail_connect)

    with TestClient(app) as client:
        live_response = client.get("/api/v1/health/live")
        ready_response = client.get("/api/v1/health/ready")

    assert live_response.status_code == 200
    assert live_response.json() == {"status": "ok"}
    assert ready_response.status_code == 503
    assert ready_response.json()["detail"]["database_ready"] is False


def test_readiness_retries_database_after_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConnection:
        async def fetchval(self, _query: str) -> int:
            return 1

    class FakeAcquire:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _traceback: object,
        ) -> None:
            return None

    class FakePool:
        def acquire(self) -> FakeAcquire:
            return FakeAcquire()

        async def close(self) -> None:
            return None

    attempts = 0

    async def flaky_connect(self: OfficialIndexStagingRepository) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("temporary database outage")
        self.pool = FakePool()  # type: ignore[assignment]

    monkeypatch.setattr(OfficialIndexStagingRepository, "connect", flaky_connect)

    with TestClient(app) as client:
        live_response = client.get("/api/v1/health/live")
        ready_response = client.get("/api/v1/health/ready")

    assert live_response.status_code == 200
    assert ready_response.status_code == 200
    assert ready_response.json()["database_ready"] is True
    assert attempts == 2
