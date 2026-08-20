import base64
import hashlib
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.core.config import Settings
from app.core.rate_limit import public_write_rate_limiter
from app.core.security import require_admin_key
from app.main import app
from app.repositories.postgres import PostgresRepository
from app.services.push import PushService

P256DH = base64.urlsafe_b64encode(b"\x04" + b"p" * 64).rstrip(b"=").decode()
AUTH_SECRET = base64.urlsafe_b64encode(b"a" * 16).rstrip(b"=").decode()


class FakePushRepository:
    configured = True

    def __init__(self) -> None:
        self.saved_endpoint: str | None = None
        self.removed_endpoint: str | None = None

    async def save_push_subscription(self, payload: Any) -> str:
        self.saved_endpoint = str(payload.subscription.endpoint)
        return hashlib.sha256(self.saved_endpoint.encode()).hexdigest()

    async def remove_push_subscription(self, endpoint: str) -> None:
        self.removed_endpoint = endpoint

    async def get_publishable_push_alert(self, alert_id: str) -> dict[str, str] | None:
        if alert_id != "alert-approved-1":
            return None
        return {
            "id": alert_id,
            "title": "Alteração oficialmente comprovada",
            "body": "Consulte a explicação e a respetiva fonte oficial.",
            "municipality": "Sintra",
        }

    async def list_active_push_subscriptions(
        self,
        *,
        district: str | None = None,
        municipality: str | None = None,
    ) -> list[dict[str, str]]:
        assert district is None
        assert municipality == "Sintra"
        return []


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> Iterator[None]:
    public_write_rate_limiter.clear()
    yield
    public_write_rate_limiter.clear()


def test_push_subscription_can_be_created_updated_and_removed_by_the_browser() -> None:
    repository = FakePushRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    payload = {
        "subscription": {
            "endpoint": "https://fcm.googleapis.com/wp/opaque-token",
            "keys": {"p256dh": P256DH, "auth": AUTH_SECRET},
        },
        "districts": ["Lisboa"],
        "municipalities": ["Sintra"],
    }
    try:
        with TestClient(app) as client:
            created = client.post("/api/v1/push/subscriptions", json=payload)
            removed = client.request(
                "DELETE",
                "/api/v1/push/subscriptions",
                json={"endpoint": payload["subscription"]["endpoint"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.json()["accepted"] is True
    assert len(created.json()["id"]) == 64
    assert created.headers["cache-control"] == "no-store"
    assert removed.status_code == 200
    assert removed.json() == {"removed": True}
    assert removed.headers["cache-control"] == "no-store"
    assert repository.saved_endpoint == payload["subscription"]["endpoint"]
    assert repository.removed_endpoint == payload["subscription"]["endpoint"]


def test_push_subscription_delete_is_allowed_by_cors_preflight() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/push/subscriptions",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_unavailable_push_storage_fails_closed_without_consuming_quota() -> None:
    class UnconfiguredRepository:
        configured = False

    app.dependency_overrides[get_repository] = lambda: UnconfiguredRepository()
    payload = {
        "subscription": {
            "endpoint": "https://fcm.googleapis.com/wp/opaque-token",
            "keys": {"p256dh": P256DH, "auth": AUTH_SECRET},
        },
        "districts": [],
        "municipalities": [],
    }
    try:
        with TestClient(app) as client:
            responses = [client.post("/api/v1/push/subscriptions", json=payload) for _ in range(21)]
    finally:
        app.dependency_overrides.clear()

    assert {response.status_code for response in responses} == {503}
    assert {response.json()["detail"] for response in responses} == {
        "O serviço de alertas está temporariamente indisponível."
    }


def test_push_provider_failure_does_not_log_subscription_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    endpoint = "https://fcm.googleapis.com/wp/private-token"
    private_key = "private-vapid-key"

    def fail_delivery(**_kwargs: object) -> None:
        from pywebpush import WebPushException

        raise WebPushException(f"provider rejected {endpoint} {private_key}")

    monkeypatch.setattr("app.services.push.webpush", fail_delivery)
    service = PushService(
        Settings(
            _env_file=None,
            environment="test",
            vapid_private_key=private_key,
        )
    )
    with caplog.at_level(logging.WARNING):
        sent = service.send(
            {"endpoint": endpoint, "p256dh": P256DH, "auth": AUTH_SECRET},
            {"title": "Atualização oficial"},
        )

    assert sent is False
    assert "push_delivery_failed" in caplog.text
    assert endpoint not in caplog.text
    assert private_key not in caplog.text


def test_broadcast_accepts_only_an_existing_published_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakePushRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[require_admin_key] = lambda: None
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private-vapid-key")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            approved = client.post(
                "/api/v1/push/broadcast",
                json={"alert_id": "alert-approved-1"},
            )
            arbitrary = client.post(
                "/api/v1/push/broadcast",
                json={
                    "alert_id": "missing-alert",
                    "title": "Texto não aprovado",
                    "body": "Não pode ser enviado.",
                },
            )
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert approved.status_code == 200
    assert approved.json() == {"selected": 0, "sent": 0, "failed": 0}
    assert arbitrary.status_code == 422


@pytest.mark.asyncio
async def test_repository_removes_only_the_exact_hashed_push_endpoint() -> None:
    endpoint = "https://fcm.googleapis.com/wp/opaque-token"

    class Connection:
        arguments: tuple[object, ...] | None = None
        query: str | None = None

        async def execute(self, query: str, *arguments: object) -> str:
            self.query = query
            self.arguments = arguments
            return "DELETE 1"

    connection = Connection()

    class Acquire:
        async def __aenter__(self) -> Connection:
            return connection

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _traceback: object,
        ) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquire:
            return Acquire()

    repository = PostgresRepository(Settings(_env_file=None, environment="test"))
    repository.pool = Pool()  # type: ignore[assignment]

    await repository.remove_push_subscription(endpoint)

    assert connection.query is not None
    assert "DELETE FROM push_subscriptions" in connection.query
    assert connection.arguments == (hashlib.sha256(endpoint.encode()).hexdigest(), endpoint)


@pytest.mark.asyncio
async def test_repository_selects_only_published_attested_unexpired_alerts() -> None:
    class Connection:
        arguments: tuple[object, ...] | None = None
        query: str | None = None

        async def fetchrow(self, query: str, *arguments: object) -> None:
            self.query = query
            self.arguments = arguments
            return None

    connection = Connection()

    class Acquire:
        async def __aenter__(self) -> Connection:
            return connection

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _traceback: object,
        ) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquire:
            return Acquire()

    repository = PostgresRepository(Settings(_env_file=None, environment="test"))
    repository.pool = Pool()  # type: ignore[assignment]

    alert = await repository.get_publishable_push_alert("alert-approved-1")

    assert alert is None
    assert connection.query is not None
    assert "alert.publication_status = 'PUBLISHED'" in connection.query
    assert "alert.requires_human_review = true" in connection.query
    assert "data_publication_reviews" in connection.query
    assert "publication_review.publishable = true" in connection.query
    assert "review.entity_type = 'CITIZEN_ALERT'" in connection.query
    assert "ORDER BY review.reviewed_at DESC, review.id DESC" in connection.query
    assert "alert.effective_at <= now()" in connection.query
    assert "alert.expires_at > now()" in connection.query
    assert "source_archive_attestations" in connection.query
    assert connection.arguments == ("alert-approved-1",)


def test_push_preferences_have_bounded_text_values() -> None:
    repository = FakePushRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    payload = {
        "subscription": {
            "endpoint": "https://fcm.googleapis.com/wp/opaque-token",
            "keys": {"p256dh": P256DH, "auth": AUTH_SECRET},
        },
        "districts": ["x" * 101],
        "municipalities": [],
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/push/subscriptions", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/wp/token",
        "https://127.0.0.1/push/token",
        "https://push.attacker.example/token",
        "https://fcm.googleapis.com.attacker.example/token",
    ],
)
def test_push_subscription_rejects_untrusted_delivery_endpoints(endpoint: str) -> None:
    repository = FakePushRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    payload = {
        "subscription": {
            "endpoint": endpoint,
            "keys": {"p256dh": P256DH, "auth": AUTH_SECRET},
        },
        "districts": ["Lisboa"],
        "municipalities": [],
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/push/subscriptions", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("p256dh", "auth"),
    [
        ("p" * 87, AUTH_SECRET),
        (P256DH, "a" * 20),
        (base64.urlsafe_b64encode(b"p" * 65).rstrip(b"=").decode(), AUTH_SECRET),
    ],
)
def test_push_subscription_rejects_malformed_cryptographic_keys(
    p256dh: str,
    auth: str,
) -> None:
    repository = FakePushRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    payload = {
        "subscription": {
            "endpoint": "https://fcm.googleapis.com/wp/opaque-token",
            "keys": {"p256dh": p256dh, "auth": auth},
        },
        "districts": ["Lisboa"],
        "municipalities": [],
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/push/subscriptions", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
