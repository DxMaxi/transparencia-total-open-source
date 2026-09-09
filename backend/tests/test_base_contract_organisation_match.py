"""Validação HTTP e prova privada dos candidatos V5.54."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.dependencies import (
    get_base_contract_organisation_match_repository,
    require_editorial_staff,
)
from app.main import app
from app.models.base_contract_organisation_match import (
    BaseContractOrganisationMatchCandidateRequest,
)
from app.repositories.base_contract_organisation_match import _official_url, _safe_text
from app.repositories.editorial import EditorialSourceError


def _payload():
    return {
        "expected_public_contract_id": "base_contract_" + "a" * 64,
        "expected_contract_publication_snapshot_id": "base_contract_publication_" + "b" * 32,
        "expected_contract_party_snapshot_id": "party_synthetic",
        "expected_organisation_id": "base_public_org_" + "c" * 32,
        "expected_organisation_publication_snapshot_id": "base_org_publication_" + "d" * 32,
        "expected_candidate_proof_sha256": "e" * 64,
        "rationale": "Duas fontes oficiais verificadas para um candidato privado.",
        **{
            field: True
            for field in BaseContractOrganisationMatchCandidateRequest.model_fields
            if field.startswith("confirm_")
        },
    }


@pytest.mark.parametrize(
    "field",
    [
        field
        for field in BaseContractOrganisationMatchCandidateRequest.model_fields
        if field.startswith("confirm_")
    ],
)
@pytest.mark.parametrize("value", [False, None])
def test_every_confirmation_is_required(field, value):
    with pytest.raises(ValidationError):
        BaseContractOrganisationMatchCandidateRequest(**{**_payload(), field: value})


@pytest.mark.parametrize(
    "text",
    [" " + " " * 20, "NIF 501234567 observado na fonte oficial.", "HMAC protegido: " + "f" * 64],
)
def test_rationale_refuses_protected_identifiers_and_empty_content(text):
    with pytest.raises(ValidationError):
        BaseContractOrganisationMatchCandidateRequest(**{**_payload(), "rationale": text})


@pytest.mark.parametrize(
    "url",
    [
        "https://publicacoes.mj.pt.evil.example/DetalhePublicacao.aspx",
        "https://publicacoes.mj.pt/DetalhePublicacao.aspx?nipc=501234567",
        "https://user:pass@publicacoes.mj.pt/DetalhePublicacao.aspx",
        "https://publicacoes.mj.pt:invalid/DetalhePublicacao.aspx",
        "javascript:alert(1)",
        "http://publicacoes.mj.pt/DetalhePublicacao.aspx",
    ],
)
def test_unsafe_organisation_urls_fail_closed(url):
    with pytest.raises(EditorialSourceError):
        _official_url(url, publisher="JUSTICE_REGISTRY")


def test_protected_display_text_is_not_echoed_in_error():
    with pytest.raises(EditorialSourceError) as error:
        _safe_text("Fornecedor NIPC 501234567", label="designacao", maximum=500)
    assert "501234567" not in str(error.value)


@pytest.mark.parametrize("authorised", [True, False])
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_http_boundary_never_echoes_identifiers(authorised, method):
    previous = dict(app.dependency_overrides)
    repository = MagicMock(inspect=AsyncMock(), create=AsyncMock())

    def actor():
        if not authorised:
            raise HTTPException(status_code=401, detail="Autenticação necessária")
        return MagicMock()

    app.dependency_overrides[get_base_contract_organisation_match_repository] = lambda: repository
    app.dependency_overrides[require_editorial_staff] = actor
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            url = "/api/v1/editorial/base/contract-organisation-match-candidates"
            if method == "GET":
                response = await client.get(url, params={"public_contract_id": "501234567"})
            else:
                response = await client.post(url, json={**_payload(), "nipc": "501234567"})
        assert response.status_code == (422 if authorised else 401)
        assert "501234567" not in response.text
        assert response.headers["Cache-Control"] == "no-store"
        repository.inspect.assert_not_called()
        repository.create.assert_not_called()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
