from __future__ import annotations

import base64
import json
from email.message import Message
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from app.services import b2_credentials
from app.services.b2_credentials import (
    AUTHORIZE_ACCOUNT_URL,
    BACKUP_KEY_CAPABILITIES,
    RESTORE_KEY_CAPABILITIES,
    B2CredentialScopeError,
    authorize_b2_application_key,
    validate_b2_application_key_scope,
)

BUCKET = "transparencia-total-db-backup-eu-example"
PREFIX = "database/"
ENDPOINT = "https://s3.eu-central-003.backblazeb2.com"


class _AuthorizationResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _AuthorizationResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


def _authorization(*, capabilities: frozenset[str]) -> dict[str, Any]:
    return {
        "accountId": "not-returned-by-validator",
        "authorizationToken": "must-not-be-returned",
        "apiInfo": {
            "storageApi": {
                "allowed": {
                    "buckets": [{"id": "bucket-id", "name": BUCKET}],
                    "capabilities": sorted(capabilities),
                    "namePrefix": PREFIX,
                },
                "s3ApiUrl": ENDPOINT,
            }
        },
    }


def test_authorization_uses_only_the_fixed_https_endpoint_and_basic_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, *, timeout: float) -> _AuthorizationResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _AuthorizationResponse(
            json.dumps(_authorization(capabilities=RESTORE_KEY_CAPABILITIES)).encode()
        )

    monkeypatch.setattr(b2_credentials, "urlopen", fake_urlopen)
    key_id = "dummy-key-id"
    application_key = "dummy-application-key"

    result = authorize_b2_application_key(
        application_key_id=key_id,
        application_key=application_key,
        timeout_seconds=3.0,
    )

    request = captured["request"]
    assert isinstance(request, Request)
    assert request.full_url == AUTHORIZE_ACCOUNT_URL
    assert key_id not in request.full_url
    assert application_key not in request.full_url
    expected_basic = base64.b64encode(f"{key_id}:{application_key}".encode()).decode("ascii")
    assert request.get_header("Authorization") == f"Basic {expected_basic}"
    assert captured["timeout"] == 3.0
    assert result["apiInfo"]["storageApi"]["s3ApiUrl"] == ENDPOINT


def test_authorization_error_never_repeats_the_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Request, *, timeout: float) -> _AuthorizationResponse:
        raise HTTPError(request.full_url, 401, "unauthorized", hdrs=Message(), fp=None)

    monkeypatch.setattr(b2_credentials, "urlopen", fake_urlopen)
    key_id = "do-not-repeat-key-id"
    application_key = "do-not-repeat-application-key"

    with pytest.raises(B2CredentialScopeError) as error:
        authorize_b2_application_key(
            application_key_id=key_id,
            application_key=application_key,
        )

    assert key_id not in str(error.value)
    assert application_key not in str(error.value)


@pytest.mark.parametrize(
    ("role", "capabilities"),
    [
        ("backup", BACKUP_KEY_CAPABILITIES),
        ("restore", RESTORE_KEY_CAPABILITIES),
    ],
)
def test_scope_accepts_only_the_exact_role_profile(role: str, capabilities: frozenset[str]) -> None:
    result = validate_b2_application_key_scope(
        _authorization(capabilities=capabilities),
        role=role,
        expected_bucket=BUCKET,
        expected_prefix=PREFIX,
        expected_s3_endpoint=ENDPOINT,
    )

    assert result["capabilities"] == sorted(capabilities)
    assert "authorizationToken" not in str(result)
    assert "accountId" not in str(result)


@pytest.mark.parametrize("extra", ["deleteFiles", "bypassGovernance", "writeBuckets"])
def test_backup_scope_rejects_dangerous_extra_capabilities(extra: str) -> None:
    with pytest.raises(B2CredentialScopeError, match="a mais"):
        validate_b2_application_key_scope(
            _authorization(capabilities=BACKUP_KEY_CAPABILITIES | frozenset({extra})),
            role="backup",
            expected_bucket=BUCKET,
            expected_prefix=PREFIX,
            expected_s3_endpoint=ENDPOINT,
        )


def test_scope_rejects_missing_capability() -> None:
    with pytest.raises(B2CredentialScopeError, match="em falta"):
        validate_b2_application_key_scope(
            _authorization(capabilities=BACKUP_KEY_CAPABILITIES - {"writeFileRetentions"}),
            role="backup",
            expected_bucket=BUCKET,
            expected_prefix=PREFIX,
            expected_s3_endpoint=ENDPOINT,
        )


def test_scope_rejects_an_unrestricted_bucket_list() -> None:
    authorization = _authorization(capabilities=RESTORE_KEY_CAPABILITIES)
    authorization["apiInfo"]["storageApi"]["allowed"]["buckets"] = []

    with pytest.raises(B2CredentialScopeError, match="único bucket"):
        validate_b2_application_key_scope(
            authorization,
            role="restore",
            expected_bucket=BUCKET,
            expected_prefix=PREFIX,
            expected_s3_endpoint=ENDPOINT,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("bucket", "outro-bucket", "bucket errado"),
        ("prefix", "outro/", "prefixo errado"),
        ("endpoint", "https://s3.us-west-004.backblazeb2.com", "EU Central"),
    ],
)
def test_scope_rejects_wrong_destination(field: str, value: str, message: str) -> None:
    expected_bucket = value if field == "bucket" else BUCKET
    expected_prefix = value if field == "prefix" else PREFIX
    expected_endpoint = value if field == "endpoint" else ENDPOINT

    with pytest.raises(B2CredentialScopeError, match=message):
        validate_b2_application_key_scope(
            _authorization(capabilities=RESTORE_KEY_CAPABILITIES),
            role="restore",
            expected_bucket=expected_bucket,
            expected_prefix=expected_prefix,
            expected_s3_endpoint=expected_endpoint,
        )
