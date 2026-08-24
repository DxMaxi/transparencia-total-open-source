import hashlib
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.repositories.parliament_resource_manifest import (
    PrivateParliamentCatalogueCandidateProof,
)
from app.services.parliament_resource_manifest import (
    PARLIAMENT_RESOURCE_COMPLETENESS,
    PARLIAMENT_RESOURCE_STATUS,
    ParliamentResourceFormat,
    ParliamentResourceManifestCollector,
    ParliamentResourceManifestStager,
)
from app.services.parliament_source_catalogue import ParliamentCatalogueKind
from scripts.sync_parliament_resource_manifest import validate_private_manifest_operation

PARENT_SNAPSHOT_ID = f"official_index_{'a' * 32}"
FOLDER_URL = "https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx?Path=exact-xvii"


def _response(body: bytes, *, url: str = FOLDER_URL) -> httpx.Response:
    return httpx.Response(
        200,
        content=body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", url),
    )


@pytest.mark.asyncio
async def test_manifest_keeps_folder_proof_and_only_exact_xml_json_resources() -> None:
    body = b"""
      <html><body>
        <a href="/dados/IniciativasXVII.xml">IniciativasXVII.xml</a>
        <a href="https://app.parlamento.pt/webutils/docs/doc.txt?fich=IniciativasXVII_json.txt&amp;Inline=true">IniciativasXVII_json.txt</a>
        <a href="/dados/nota.pdf">Nota metodologica</a>
        <a href="https://www.dre.pt/falso.json">Fonte externa.json</a>
        <a href="/download?file=um.xml&amp;filename=outro_json.txt">Recurso ambiguo</a>
        <a href="/dados/IniciativasXVII.xml">IniciativasXVII.xml</a>
      </body></html>
    """
    http = AsyncMock()
    http.get.return_value = _response(body)

    result = await ParliamentResourceManifestCollector(http).collect(
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        parent_catalogue_snapshot_id=PARENT_SNAPSHOT_ID,
        candidate_url=FOLDER_URL,
    )

    assert result.content_sha256 == hashlib.sha256(body).hexdigest()
    assert result.raw_document.content == body
    assert str(result.source_url) == FOLDER_URL
    assert result.publishable is False
    assert result.editorial_cases_created == 0
    assert [resource.resource_format for resource in result.resources] == [
        ParliamentResourceFormat.XML,
        ParliamentResourceFormat.JSON,
    ]
    assert all(resource.status == PARLIAMENT_RESOURCE_STATUS for resource in result.resources)
    assert all(
        resource.historical_completeness == PARLIAMENT_RESOURCE_COMPLETENESS
        for resource in result.resources
    )
    assert all(resource.publishable is False for resource in result.resources)


@pytest.mark.asyncio
async def test_manifest_rejects_effective_url_different_from_archived_candidate() -> None:
    http = AsyncMock()
    http.get.return_value = _response(
        b'<a href="/dados/IniciativasXVII.xml">IniciativasXVII.xml</a>',
        url="https://www.parlamento.pt/Cidadania/Paginas/outra-pasta.aspx",
    )

    with pytest.raises(ValueError, match="URL efetivo"):
        await ParliamentResourceManifestCollector(http).collect(
            catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
            legislature="XVII",
            parent_catalogue_snapshot_id=PARENT_SNAPSHOT_ID,
            candidate_url=FOLDER_URL,
        )


@pytest.mark.asyncio
async def test_manifest_fails_closed_without_unambiguous_resources() -> None:
    http = AsyncMock()
    http.get.return_value = _response(b'<a href="/nota.pdf">Nota</a>')

    with pytest.raises(ValueError, match="recursos XML ou JSON inequívocos"):
        await ParliamentResourceManifestCollector(http).collect(
            catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
            legislature="XVII",
            parent_catalogue_snapshot_id=PARENT_SNAPSHOT_ID,
            candidate_url=FOLDER_URL,
        )


@pytest.mark.asyncio
async def test_manifest_stager_revalidates_parent_and_keeps_resources_private() -> None:
    body = b'<a href="/dados/IniciativasXVII.xml">IniciativasXVII.xml</a>'
    http = AsyncMock()
    http.get.return_value = _response(body)
    collection = await ParliamentResourceManifestCollector(http).collect(
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        parent_catalogue_snapshot_id=PARENT_SNAPSHOT_ID,
        candidate_url=FOLDER_URL,
    )
    repository = AsyncMock()
    repository.require_catalogue_candidate.return_value = PrivateParliamentCatalogueCandidateProof(
        snapshot_id=PARENT_SNAPSHOT_ID,
        source_document_id="source_parent",
        source_name="PARLIAMENT_CATALOGUE_INITIATIVES",
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        official_label="XVII Legislatura",
        candidate_url=FOLDER_URL,
        catalogue_source_url=("https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx"),
        catalogue_content_sha256="b" * 64,
        archive_attested=True,
    )
    repository.store_index.return_value = {
        "snapshot_id": "official_index_child",
        "publishable": False,
    }

    result = await ParliamentResourceManifestStager(Settings(environment="test"), repository).store(
        collection
    )

    assert result["parent_catalogue_snapshot_id"] == PARENT_SNAPSHOT_ID
    assert result["resource_count"] == 1
    assert result["resource_status"] == "PENDING_DOWNLOAD"
    assert result["resources_downloaded"] == 0
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    repository.require_catalogue_candidate.assert_awaited_once_with(
        snapshot_id=PARENT_SNAPSHOT_ID,
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        candidate_url=FOLDER_URL,
    )
    call = repository.store_index.await_args.kwargs
    assert call["publisher"] == "PARLIAMENT"
    assert call["resources"][0].category == (
        "PARLIAMENT_RESOURCE_CANDIDATE:INITIATIVES:XVII:XML:"
        f"PENDING_DOWNLOAD:NOT_ASSERTED:PARENT={PARENT_SNAPSHOT_ID}"
    )


@pytest.mark.asyncio
async def test_manifest_stager_rejects_production_and_tampered_resource() -> None:
    body = b'<a href="/dados/IniciativasXVII.xml">IniciativasXVII.xml</a>'
    http = AsyncMock()
    http.get.return_value = _response(body)
    collection = await ParliamentResourceManifestCollector(http).collect(
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        parent_catalogue_snapshot_id=PARENT_SNAPSHOT_ID,
        candidate_url=FOLDER_URL,
    )
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentResourceManifestStager(
            Settings(environment="production"), repository
        ).store(collection)

    tampered = replace(collection.resources[0], publishable=True)
    repository.require_catalogue_candidate.return_value = AsyncMock()
    with pytest.raises(ValueError, match="contrato privado"):
        await ParliamentResourceManifestStager(Settings(environment="test"), repository).store(
            replace(collection, resources=(tampered,))
        )

    repository.store_index.assert_not_awaited()


def test_manifest_script_requires_explicit_staging_and_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_manifest_operation(Settings(environment="staging"), confirmed=False)
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_manifest_operation(Settings(environment="test"), confirmed=True)
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_manifest_operation(
            Settings(environment="staging", database_url=None), confirmed=True
        )

    validate_private_manifest_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
