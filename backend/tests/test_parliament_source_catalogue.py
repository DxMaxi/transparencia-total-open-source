import hashlib
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.services.parliament_source_catalogue import (
    PARLIAMENT_CANDIDATE_STATUS,
    PARLIAMENT_HISTORICAL_COMPLETENESS,
    ParliamentCatalogueKind,
    ParliamentSourceCatalogueCollector,
    ParliamentSourceCatalogueStager,
)
from scripts.sync_parliament_source_catalogue import validate_private_staging_operation


def _response(body: bytes, *, url: str) -> httpx.Response:
    return httpx.Response(
        200,
        content=body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", url),
    )


@pytest.mark.asyncio
async def test_catalogue_keeps_source_proof_and_only_exact_legislature_candidates() -> None:
    body = """
        <html><body>
          <a href="/acolhimento">Acolhimento aos Deputados - XVII Legislatura</a>
          <a href="?Path=exact-xvii&amp;t=one">XVII Legislatura</a>
          <a href="?Path=exact-xvi&amp;t=two">  XVI\n Legislatura </a>
          <a href="https://app.parlamento.pt/recurso/constituinte">Constituinte</a>
          <a href="?Path=ambiguous">XV Legislatura — arquivo</a>
          <a href="https://www.dre.pt/falso">XIV Legislatura</a>
          <a href="?Path=exact-xvii&amp;t=one">XVII Legislatura</a>
        </body></html>
    """.encode()
    url = "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx"
    http = AsyncMock()
    http.get.return_value = _response(body, url=url)

    result = await ParliamentSourceCatalogueCollector(http).collect(
        ParliamentCatalogueKind.INITIATIVES
    )

    assert result.content_sha256 == hashlib.sha256(body).hexdigest()
    assert result.raw_document.content == body
    assert result.raw_document.mime_type == "text/html"
    assert str(result.source_url) == url
    assert result.publishable is False
    assert result.editorial_proposals_created == 0
    assert [candidate.legislature for candidate in result.candidates] == [
        "XVII",
        "XVI",
        "CONSTITUINTE",
    ]
    assert all(candidate.status == PARLIAMENT_CANDIDATE_STATUS for candidate in result.candidates)
    assert all(
        candidate.historical_completeness == PARLIAMENT_HISTORICAL_COMPLETENESS
        for candidate in result.candidates
    )
    assert all(candidate.publishable is False for candidate in result.candidates)
    assert str(result.candidates[0].url) == (
        "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx?Path=exact-xvii&t=one"
    )


@pytest.mark.asyncio
async def test_catalogue_fails_closed_when_no_exact_legislature_is_present() -> None:
    body = b'<a href="?Path=almost">XVII Legislatura - atual</a>'
    url = "https://www.parlamento.pt/Cidadania/Paginas/DAatividades.aspx"
    http = AsyncMock()
    http.get.return_value = _response(body, url=url)

    with pytest.raises(ValueError, match="etiquetas exatas"):
        await ParliamentSourceCatalogueCollector(http).collect(ParliamentCatalogueKind.ACTIVITIES)


@pytest.mark.asyncio
async def test_catalogue_rejects_an_effective_url_outside_parliament() -> None:
    body = b'<a href="?Path=exact">XVII Legislatura</a>'
    http = AsyncMock()
    http.get.return_value = _response(body, url="https://www.dre.pt/catalogo")

    with pytest.raises(ValueError, match="URL parlamentar não autorizada"):
        await ParliamentSourceCatalogueCollector(http).collect(
            ParliamentCatalogueKind.DEPUTY_ACTIVITY
        )


@pytest.mark.asyncio
async def test_catalogue_rejects_a_non_html_response() -> None:
    url = "https://www.parlamento.pt/Cidadania/Paginas/DAatividades.aspx"
    http = AsyncMock()
    http.get.return_value = httpx.Response(
        200,
        content=b'{"XVII Legislatura": "candidate"}',
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", url),
    )

    with pytest.raises(ValueError, match="não devolveu HTML"):
        await ParliamentSourceCatalogueCollector(http).collect(ParliamentCatalogueKind.ACTIVITIES)


@pytest.mark.asyncio
async def test_stager_keeps_candidates_private_and_does_not_create_proposals() -> None:
    body = b'<a href="?Path=xvii">XVII Legislatura</a>'
    url = "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx"
    http = AsyncMock()
    http.get.return_value = _response(body, url=url)
    collection = await ParliamentSourceCatalogueCollector(http).collect(
        ParliamentCatalogueKind.INITIATIVES
    )
    repository = AsyncMock()
    repository.store_index.return_value = {
        "snapshot_id": "official_index_fixture",
        "publishable": False,
    }

    result = await ParliamentSourceCatalogueStager(Settings(environment="test"), repository).store(
        collection
    )

    assert result["candidate_count"] == 1
    assert result["candidate_status"] == "PENDING_INSPECTION"
    assert result["historical_completeness"] == "NOT_ASSERTED"
    assert result["editorial_proposals_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    call = repository.store_index.await_args.kwargs
    assert call["publisher"] == "PARLIAMENT"
    assert call["resources"][0].category == (
        "PARLIAMENT_SOURCE_CANDIDATE:INITIATIVES:XVII:PENDING_INSPECTION:NOT_ASSERTED"
    )


@pytest.mark.asyncio
async def test_stager_rejects_production_even_for_a_private_collection() -> None:
    body = b'<a href="?Path=xvii">XVII Legislatura</a>'
    url = "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx"
    http = AsyncMock()
    http.get.return_value = _response(body, url=url)
    collection = await ParliamentSourceCatalogueCollector(http).collect(
        ParliamentCatalogueKind.INITIATIVES
    )
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentSourceCatalogueStager(Settings(environment="production"), repository).store(
            collection
        )

    repository.store_index.assert_not_awaited()


@pytest.mark.asyncio
async def test_stager_rejects_evidence_or_candidate_contract_divergence() -> None:
    body = b'<a href="?Path=xvii">XVII Legislatura</a>'
    url = "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx"
    http = AsyncMock()
    http.get.return_value = _response(body, url=url)
    collection = await ParliamentSourceCatalogueCollector(http).collect(
        ParliamentCatalogueKind.INITIATIVES
    )
    repository = AsyncMock()
    stager = ParliamentSourceCatalogueStager(Settings(environment="test"), repository)

    with pytest.raises(ValueError, match="prova do catálogo"):
        await stager.store(replace(collection, content_sha256="0" * 64))

    invalid_candidate = replace(collection.candidates[0], publishable=True)
    with pytest.raises(ValueError, match="contrato privado"):
        await stager.store(replace(collection, candidates=(invalid_candidate,)))

    repository.store_index.assert_not_awaited()


def test_script_requires_explicit_staging_confirmation_and_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_staging_operation(Settings(environment="staging"), confirmed=False)
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_staging_operation(Settings(environment="test"), confirmed=True)
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_staging_operation(
            Settings(environment="staging", database_url=None), confirmed=True
        )

    validate_private_staging_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
