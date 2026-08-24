import hashlib
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.repositories.parliament_resource_archive import PrivateParliamentResourceCandidateProof
from app.services.parliament_resource_archive import (
    PARLIAMENT_RESOURCE_ARCHIVE_COMPLETENESS,
    PARLIAMENT_RESOURCE_ARCHIVE_STATUS,
    ParliamentResourceArchiveCollector,
    ParliamentResourceArchiveStager,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_source_catalogue import ParliamentCatalogueKind
from scripts.sync_parliament_resource_archive import validate_private_archive_operation

CATALOGUE_SNAPSHOT_ID = f"official_index_{'a' * 32}"
MANIFEST_SNAPSHOT_ID = f"official_index_{'b' * 32}"
RESOURCE_URL = (
    "https://app.parlamento.pt/webutils/docs/doc.txt?fich=IniciativasXVII_json.txt&Inline=true"
)


def _proof() -> PrivateParliamentResourceCandidateProof:
    return PrivateParliamentResourceCandidateProof(
        manifest_snapshot_id=MANIFEST_SNAPSHOT_ID,
        manifest_source_document_id="source_manifest",
        parent_catalogue_snapshot_id=CATALOGUE_SNAPSHOT_ID,
        source_name="PARLIAMENT_RESOURCE_MANIFEST_INITIATIVES_XVII",
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        resource_format=ParliamentResourceFormat.JSON,
        official_label="IniciativasXVII_json.txt",
        resource_url=RESOURCE_URL,
        manifest_source_url=(
            "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx?Path=exact-xvii"
        ),
        manifest_content_sha256="c" * 64,
        manifest_archive_attested=True,
        catalogue_content_sha256="d" * 64,
    )


def _response(
    body: bytes,
    *,
    url: str = RESOURCE_URL,
    mime_type: str = "application/json; charset=utf-8",
) -> httpx.Response:
    return httpx.Response(
        200,
        content=body,
        headers={"content-type": mime_type},
        request=httpx.Request("GET", url),
    )


@pytest.mark.asyncio
async def test_archive_collects_exact_bytes_without_parsing_them() -> None:
    body = b'{"registos": [{"id": "oficial-1"}]}'
    http = AsyncMock()
    http.get.return_value = _response(body)

    result = await ParliamentResourceArchiveCollector(http, max_bytes=12_345).collect(_proof())

    http.get.assert_awaited_once_with(RESOURCE_URL, max_bytes=12_345)
    assert result.content_sha256 == hashlib.sha256(body).hexdigest()
    assert result.byte_size == len(body)
    assert result.raw_document.content == body
    assert result.raw_document.mime_type == "application/json"
    assert result.status == PARLIAMENT_RESOURCE_ARCHIVE_STATUS
    assert result.historical_completeness == PARLIAMENT_RESOURCE_ARCHIVE_COMPLETENESS
    assert result.records_normalised == 0
    assert result.editorial_cases_created == 0
    assert result.publishable is False


@pytest.mark.asyncio
async def test_archive_rejects_an_unattested_proof_before_http() -> None:
    http = AsyncMock()

    with pytest.raises(ValueError, match="prova privada"):
        await ParliamentResourceArchiveCollector(http, max_bytes=12_345).collect(
            replace(_proof(), manifest_archive_attested=False)
        )

    http.get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    (
        (
            _response(
                b"<html>erro</html>",
                mime_type="text/html; charset=utf-8",
            ),
            "devolveu HTML",
        ),
        (
            _response(
                b'{"registos": []}',
                url="https://app.parlamento.pt/webutils/docs/outro_json.txt",
            ),
            "URL efetivo",
        ),
    ),
)
async def test_archive_fails_closed_on_html_or_changed_effective_url(
    response: httpx.Response,
    message: str,
) -> None:
    http = AsyncMock()
    http.get.return_value = response

    with pytest.raises(ValueError, match=message):
        await ParliamentResourceArchiveCollector(http, max_bytes=12_345).collect(_proof())


@pytest.mark.asyncio
async def test_archive_stager_revalidates_parent_and_keeps_bytes_private() -> None:
    body = b'{"registos": [{"id": "oficial-1"}]}'
    http = AsyncMock()
    http.get.return_value = _response(body)
    collection = await ParliamentResourceArchiveCollector(http, max_bytes=12_345).collect(_proof())
    repository = AsyncMock()
    repository.require_resource_candidate.return_value = _proof()
    repository.store_index.return_value = {
        "snapshot_id": "official_index_child",
        "source_document_id": "source_child",
        "publishable": False,
    }

    result = await ParliamentResourceArchiveStager(
        Settings(environment="test"),
        repository,
    ).store(collection)

    assert result["parent_catalogue_snapshot_id"] == CATALOGUE_SNAPSHOT_ID
    assert result["parent_manifest_snapshot_id"] == MANIFEST_SNAPSHOT_ID
    assert result["resource_status"] == "ARCHIVED_UNPARSED"
    assert result["records_normalised"] == 0
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    repository.require_resource_candidate.assert_awaited_once_with(
        catalogue_snapshot_id=CATALOGUE_SNAPSHOT_ID,
        manifest_snapshot_id=MANIFEST_SNAPSHOT_ID,
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        resource_format=ParliamentResourceFormat.JSON,
        resource_url=RESOURCE_URL,
    )
    call = repository.store_index.await_args.kwargs
    assert call["publisher"] == "PARLIAMENT"
    assert call["resources"][0].category == (
        "PARLIAMENT_RESOURCE_ARCHIVE:INITIATIVES:XVII:JSON:"
        f"ARCHIVED_UNPARSED:NOT_ASSERTED:PARENT={MANIFEST_SNAPSHOT_ID}"
    )


@pytest.mark.asyncio
async def test_archive_stager_rejects_production_and_normalised_claim() -> None:
    body = b'{"registos": []}'
    http = AsyncMock()
    http.get.return_value = _response(body)
    collection = await ParliamentResourceArchiveCollector(http, max_bytes=12_345).collect(_proof())
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentResourceArchiveStager(
            Settings(environment="production"),
            repository,
        ).store(collection)

    with pytest.raises(ValueError, match="não pode normalizar"):
        await ParliamentResourceArchiveStager(
            Settings(environment="test"),
            repository,
        ).store(replace(collection, records_normalised=1))

    repository.require_resource_candidate.assert_not_awaited()
    repository.store_index.assert_not_awaited()


def test_archive_script_requires_explicit_staging_and_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_archive_operation(Settings(environment="staging"), confirmed=False)
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_archive_operation(Settings(environment="test"), confirmed=True)
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_archive_operation(
            Settings(environment="staging", database_url=None),
            confirmed=True,
        )

    validate_private_archive_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
