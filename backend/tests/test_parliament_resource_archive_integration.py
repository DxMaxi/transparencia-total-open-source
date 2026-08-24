"""Integração do arquivo parlamentar privado num PostgreSQL descartável."""

import os
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.repositories.parliament_resource_archive import ParliamentResourceArchiveRepository
from app.services.parliament_resource_archive import (
    ParliamentResourceArchiveCollector,
    ParliamentResourceArchiveStager,
)
from app.services.parliament_resource_manifest import (
    ParliamentResourceFormat,
    ParliamentResourceManifestCollector,
    ParliamentResourceManifestStager,
)
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    ParliamentSourceCatalogueCollector,
    ParliamentSourceCatalogueStager,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


@pytest.fixture
async def repository() -> ParliamentResourceArchiveRepository:
    repo = ParliamentResourceArchiveRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_archive_requires_full_parent_chain_and_creates_no_editorial_case(
    repository: ParliamentResourceArchiveRepository,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    catalogue_url = (
        f"https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx?fixture={suffix}"
    )
    candidate_url = (
        f"https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx?Path=fixture-{suffix}"
    )
    catalogue_body = (f'<a href="?Path=fixture-{suffix}">XVII Legislatura</a>').encode()
    catalogue_http = AsyncMock()
    catalogue_http.get.return_value = httpx.Response(
        200,
        content=catalogue_body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", catalogue_url),
    )
    catalogue = await ParliamentSourceCatalogueCollector(catalogue_http).collect(
        ParliamentCatalogueKind.INITIATIVES
    )
    parent = await ParliamentSourceCatalogueStager(Settings(environment="test"), repository).store(
        catalogue,
        code_version=f"parliament-source-catalogue-archive-parent-{suffix}",
    )

    resource_url = (
        "https://app.parlamento.pt/webutils/docs/doc.txt"
        f"?fich=IniciativasXVII_{suffix}_json.txt&Inline=true"
    )
    resource_href = resource_url.replace("&", "&amp;")
    folder_body = (f'<a href="{resource_href}">IniciativasXVII_{suffix}_json.txt</a>').encode()
    folder_http = AsyncMock()
    folder_http.get.return_value = httpx.Response(
        200,
        content=folder_body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", candidate_url),
    )
    manifest_collection = await ParliamentResourceManifestCollector(folder_http).collect(
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        parent_catalogue_snapshot_id=str(parent["snapshot_id"]),
        candidate_url=candidate_url,
    )
    manifest = await ParliamentResourceManifestStager(
        Settings(environment="test"),
        repository,
    ).store(
        manifest_collection,
        code_version=f"parliament-resource-manifest-archive-parent-{suffix}",
    )

    proof = await repository.require_resource_candidate(
        catalogue_snapshot_id=str(parent["snapshot_id"]),
        manifest_snapshot_id=str(manifest["snapshot_id"]),
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        resource_format=ParliamentResourceFormat.JSON,
        resource_url=resource_url,
    )
    resource_body = (f'{{"fixture": "{suffix}", "records": []}}').encode()
    resource_http = AsyncMock()
    resource_http.get.return_value = httpx.Response(
        200,
        content=resource_body,
        headers={"content-type": "application/json; charset=utf-8"},
        request=httpx.Request("GET", resource_url),
    )
    archive_collection = await ParliamentResourceArchiveCollector(
        resource_http,
        max_bytes=1_000_000,
    ).collect(proof)
    result = await ParliamentResourceArchiveStager(
        Settings(environment="test"),
        repository,
    ).store(
        archive_collection,
        code_version=f"parliament-resource-archive-test-{suffix}",
    )

    assert result["parent_catalogue_snapshot_id"] == parent["snapshot_id"]
    assert result["parent_manifest_snapshot_id"] == manifest["snapshot_id"]
    assert result["byte_size"] == len(resource_body)
    assert result["resource_status"] == "ARCHIVED_UNPARSED"
    assert result["records_normalised"] == 0
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        source = await connection.fetchrow(
            """
            SELECT publisher::text AS publisher, url, content_sha256, mime_type
            FROM source_documents
            WHERE id = $1
            """,
            result["source_document_id"],
        )
        raw_object = await connection.fetchrow(
            """
            SELECT content_sha256, byte_size, content
            FROM raw_source_objects
            WHERE storage_key = $1
            """,
            f"sha256/{str(result['content_sha256'])[:2]}/{result['content_sha256']}",
        )
        attestation = await connection.fetchrow(
            """
            SELECT retrieval_url, content_sha256, byte_size
            FROM source_archive_attestations
            WHERE source_document_id = $1
            """,
            result["source_document_id"],
        )
        editorial_case_count = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM editorial_cases
            WHERE source_document_id = $1
            """,
            result["source_document_id"],
        )

    assert source is not None
    assert source["publisher"] == "PARLIAMENT"
    assert source["url"] == resource_url
    assert source["content_sha256"] == result["content_sha256"]
    assert source["mime_type"] == "application/json"
    assert raw_object is not None
    assert raw_object["content_sha256"] == result["content_sha256"]
    assert raw_object["byte_size"] == len(resource_body)
    assert bytes(raw_object["content"]) == resource_body
    assert attestation is not None
    assert attestation["retrieval_url"] == resource_url
    assert attestation["content_sha256"] == result["content_sha256"]
    assert attestation["byte_size"] == len(resource_body)
    assert editorial_case_count == 0

    with pytest.raises(ValueError, match="prova privada"):
        await repository.require_resource_candidate(
            catalogue_snapshot_id=str(parent["snapshot_id"]),
            manifest_snapshot_id=str(manifest["snapshot_id"]),
            catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
            legislature="XVII",
            resource_format=ParliamentResourceFormat.XML,
            resource_url=resource_url,
        )
