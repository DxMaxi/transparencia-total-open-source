"""Erros HTTP/CLI do circuito de organizações não ecoam entradas privadas."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.api.dependencies import (
    get_base_organisation_editorial_repository,
    get_editorial_repository,
    require_editorial_staff,
)
from app.main import app, organisation_identity_validation_error, settings
from scripts.stage_base_organisation_identity import _parser

_RAW = "501234567"
_DIGEST = "b" * 64
_BASE = "/api/v1/editorial/base/organisation-identity"


@pytest.fixture
def identity_dependencies():
    previous = dict(app.dependency_overrides)
    repository = MagicMock()
    app.dependency_overrides[get_base_organisation_editorial_repository] = lambda: repository
    app.dependency_overrides[get_editorial_repository] = lambda: repository
    app.dependency_overrides[require_editorial_staff] = lambda: SimpleNamespace(
        public_alias="revisor-teste",
    )
    try:
        yield repository
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
@pytest.mark.parametrize("authorised", [True, False])
@pytest.mark.parametrize("field", ["nipc", "protected_identifier_digest", "legal_name"])
async def test_proposal_validation_never_reflects_extra_private_inputs(
    identity_dependencies,
    authorised: bool,
    field: str,
) -> None:
    if not authorised:

        def unauthorised():
            raise HTTPException(status_code=401, detail="Autenticação necessária")

        app.dependency_overrides[require_editorial_staff] = unauthorised
    body = {
        "observation_id": "base_org_identity_" + "ab" * 16,
        "source_record_sha256": "c" * 64,
        "proposal_confirmation_sha256": "d" * 64,
        "confirm_independent_official_source": True,
        "confirm_private_identity_only": True,
        "confirm_no_publication": True,
        field: _RAW + " " + _DIGEST,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(_BASE + "-proposals", json=body)
    assert response.status_code == (422 if authorised else 401)
    assert _RAW not in response.text and _DIGEST not in response.text
    assert response.headers["Cache-Control"] == "no-store"
    identity_dependencies.create_proposal.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("authorised", [True, False])
async def test_query_validation_never_reflects_invalid_private_query(
    identity_dependencies,
    authorised: bool,
) -> None:
    if not authorised:

        def unauthorised():
            raise HTTPException(status_code=401, detail="Autenticação necessária")

        app.dependency_overrides[require_editorial_staff] = unauthorised
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(_BASE + "-candidates", params={"q": _RAW * 20})
    assert response.status_code == (422 if authorised else 401)
    assert _RAW not in response.text
    identity_dependencies.list_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_json_never_reflects_submitted_secret(identity_dependencies) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            _BASE + "-proposals",
            content='{"nipc":"' + _RAW,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422
    assert _RAW not in response.text


@pytest.mark.asyncio
async def test_sanitizer_preserves_unrelated_validation_handler() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": settings.api_prefix + "/unrelated",
            "headers": [],
        }
    )
    response = await organisation_identity_validation_error(
        request,
        RequestValidationError(
            [
                {
                    "type": "string_too_short",
                    "loc": ["query", "q"],
                    "msg": "normal",
                    "input": "ordinary",
                },
            ]
        ),
    )
    assert json.loads(response.body)["detail"][0]["input"] == "ordinary"


def test_unknown_cli_flag_does_not_echo_private_argument(capsys) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["--nipc", _RAW])
    assert _RAW not in capsys.readouterr().err


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body",
    [
        (
            "/cases",
            {
                "kind": "ORGANISATION_IDENTITY",
                "subject_type": "ORGANISATION",
                "subject_id": "org_fixture",
                "source_document_id": "source_fixture",
                "normalized_data": {"nipc": _RAW},
                "confirm_private_only": True,
            },
        ),
        (
            "/cases/org_fixture/correct",
            {
                "expected_revision": 1,
                "rationale": "Tentativa de correção inválida de teste.",
                "normalized_data": {"nipc": _RAW, "hidden_hmac": _DIGEST},
            },
        ),
    ],
)
async def test_generic_editorial_validation_never_reflects_identity(
    identity_dependencies, path, body
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/editorial" + path, json=body)
    assert response.status_code == 422
    assert _RAW not in response.text and _DIGEST not in response.text
    identity_dependencies.create_case.assert_not_called()
    identity_dependencies.correct_case.assert_not_called()


def test_invalid_cli_choice_does_not_echo_private_argument(capsys) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(
            [
                "source_test",
                "AP-1-2026",
                "Organização teste",
                "--kind",
                _RAW,
                "--actor-alias",
                "operador-teste",
            ]
        )
    assert _RAW not in capsys.readouterr().err
