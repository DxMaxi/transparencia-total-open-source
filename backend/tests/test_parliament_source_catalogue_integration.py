"""Integração do catálogo parlamentar privado num PostgreSQL descartável."""

import json
import os
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.repositories.official_index_staging import OfficialIndexStagingRepository
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
async def repository() -> OfficialIndexStagingRepository:
    repo = OfficialIndexStagingRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


def _decode_json(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


@pytest.mark.asyncio
async def test_catalogue_snapshot_is_archived_audited_and_never_publishable(
    repository: OfficialIndexStagingRepository,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    url = f"https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx?fixture={suffix}"
    body = (
        b'<a href="?Path=fixture-xvii">XVII Legislatura</a>'
        b'<a href="?Path=fixture-xvi">XVI Legislatura</a>'
    )
    http = AsyncMock()
    http.get.return_value = httpx.Response(
        200,
        content=body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", url),
    )
    collection = await ParliamentSourceCatalogueCollector(http).collect(
        ParliamentCatalogueKind.INITIATIVES
    )

    result = await ParliamentSourceCatalogueStager(Settings(environment="test"), repository).store(
        collection, code_version=f"parliament-source-catalogue-test-{suffix}"
    )

    assert result["publishable"] is False
    assert result["publication_performed"] is False
    assert result["editorial_proposals_created"] == 0
    assert result["candidate_count"] == 2
    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        snapshot = await connection.fetchrow(
            """
            SELECT publisher::text AS publisher, parser_version, resource_count, publishable
            FROM official_index_snapshots
            WHERE id = $1
            """,
            result["snapshot_id"],
        )
        resources = await connection.fetch(
            """
            SELECT title, category, url
            FROM official_index_resources
            WHERE snapshot_id = $1
            ORDER BY title
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
        audit = await connection.fetchrow(
            """
            SELECT action, after_json
            FROM audit_events
            WHERE entity_type = 'OFFICIAL_INDEX_SNAPSHOT' AND entity_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            result["snapshot_id"],
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
    assert snapshot["resource_count"] == 2
    assert snapshot["publishable"] is False
    assert len(resources) == 2
    assert all("PENDING_INSPECTION:NOT_ASSERTED" in row["category"] for row in resources)
    assert attestation is not None
    assert attestation["retrieval_url"] == url
    assert attestation["content_sha256"] == result["content_sha256"]
    assert audit is not None
    assert audit["action"] == "INGESTED"
    audit_payload = _decode_json(audit["after_json"])
    assert isinstance(audit_payload, dict)
    assert audit_payload["publishable"] is False
    assert editorial_case_count == 0
