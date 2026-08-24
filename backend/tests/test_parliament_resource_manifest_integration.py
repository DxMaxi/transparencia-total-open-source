"""Integração do manifesto parlamentar privado num PostgreSQL descartável."""

import os
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.repositories.parliament_resource_manifest import ParliamentResourceManifestRepository
from app.services.parliament_resource_manifest import (
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
async def repository() -> ParliamentResourceManifestRepository:
    repo = ParliamentResourceManifestRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_manifest_requires_archived_parent_and_stays_outside_editorial_cycle(
    repository: ParliamentResourceManifestRepository,
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
        catalogue, code_version=f"parliament-source-catalogue-parent-{suffix}"
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
    manifest = await ParliamentResourceManifestCollector(folder_http).collect(
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        parent_catalogue_snapshot_id=str(parent["snapshot_id"]),
        candidate_url=candidate_url,
    )
    result = await ParliamentResourceManifestStager(Settings(environment="test"), repository).store(
        manifest, code_version=f"parliament-resource-manifest-test-{suffix}"
    )

    assert result["parent_catalogue_snapshot_id"] == parent["snapshot_id"]
    assert result["parent_catalogue_content_sha256"] == parent["content_sha256"]
    assert result["resource_count"] == 1
    assert result["resources_downloaded"] == 0
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        snapshot = await connection.fetchrow(
            """
            SELECT publisher::text AS publisher, resource_count, publishable
            FROM official_index_snapshots
            WHERE id = $1
            """,
            result["snapshot_id"],
        )
        resource = await connection.fetchrow(
            """
            SELECT title, category, url
            FROM official_index_resources
            WHERE snapshot_id = $1
            """,
            result["snapshot_id"],
        )
        attestation = await connection.fetchrow(
            """
            SELECT retrieval_url, content_sha256
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

    assert snapshot is not None
    assert snapshot["publisher"] == "PARLIAMENT"
    assert snapshot["resource_count"] == 1
    assert snapshot["publishable"] is False
    assert resource is not None
    assert resource["title"] == f"IniciativasXVII_{suffix}_json.txt"
    assert resource["url"] == resource_url
    assert resource["category"].endswith(f"PARENT={parent['snapshot_id']}")
    assert "PENDING_DOWNLOAD:NOT_ASSERTED" in resource["category"]
    assert attestation is not None
    assert attestation["retrieval_url"] == candidate_url
    assert attestation["content_sha256"] == result["content_sha256"]
    assert editorial_case_count == 0

    with pytest.raises(ValueError, match="prova privada"):
        await repository.require_catalogue_candidate(
            snapshot_id=str(parent["snapshot_id"]),
            catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
            legislature="XVI",
            candidate_url=candidate_url,
        )
