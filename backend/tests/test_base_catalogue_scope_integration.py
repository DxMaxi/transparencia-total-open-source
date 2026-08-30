"""Integração real do âmbito BASE numa base PostgreSQL descartável."""

import hashlib
import json
import os
from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.base_catalogue_staging import BaseCatalogueStagingRepository
from app.services.base_catalogue_scope import (
    extract_base_catalogue_scope,
    load_base_catalogue_manifest,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


def _catalogue_bytes() -> bytes:
    resources: list[dict[str, object]] = []
    for year in range(2012, 2027):
        resource_id = f"{year:08x}-1234-4abc-8def-{year:012x}"
        resources.append(
            {
                "id": resource_id,
                "title": f"contratos{year}.zip",
                "format": "zip",
                "url": (
                    "https://dados.gov.pt/s/resources/contratos-publicos-portal-base-impic-"
                    f"contratos-de-2012-a-2026/20260823/contratos{year}.zip"
                ),
                "latest": f"https://dados.gov.pt/api/1/datasets/r/{resource_id}",
                "last_modified": "2026-08-23T10:04:17.578+01:00",
                "filesize": 1_000_000 + year,
            }
        )
    payload = {
        "id": "66d72d488ca4b7cb2de28712",
        "title": "Contratos Públicos - Portal Base - IMPIC - Contratos de 2012 a 2026",
        "organization": {
            "id": "5ae97fa2c8d8c915d5faa3bf",
            "name": "IMPIC - Instituto Dos Mercados Públicos, do Imobiliário e da Construção",
        },
        "license": "other-pd",
        "frequency": "weekly",
        "private": False,
        "page": (
            "https://dados.gov.pt/datasets/"
            "contratos-publicos-portal-base-impic-contratos-de-2012-a-2026"
        ),
        "last_modified": "2026-08-24T11:53:45.607+01:00",
        "resources": resources,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@pytest.fixture
async def repository() -> BaseCatalogueStagingRepository:
    repo = BaseCatalogueStagingRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_scope_is_private_append_only_idempotent_and_creates_no_public_data(
    repository: BaseCatalogueStagingRepository,
) -> None:
    manifest = load_base_catalogue_manifest()
    content = _catalogue_bytes()
    retrieved_at = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
    raw = PrivateRawDocument(
        source_url=manifest.catalogue_api_url,
        retrieved_at=retrieved_at,
        content_sha256=hashlib.sha256(content).hexdigest(),
        mime_type="application/json",
        content=content,
    )
    scope = extract_base_catalogue_scope(
        catalogue_bytes=content,
        retrieved_at=retrieved_at,
        manifest=manifest,
    )
    readiness = await repository.require_scope_schema()
    assert readiness["ready"] is True

    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        before = await connection.fetchrow(
            """
            SELECT
              (SELECT count(*) FROM public_contracts) AS contracts,
              (SELECT count(*) FROM interest_relationships) AS relationships,
              (SELECT count(*) FROM contract_match_reviews) AS matches,
              (SELECT count(*) FROM base_staging_batches) AS batches
            """
        )

    receipt = await repository.archive_raw_document(raw_document=raw)
    first = await repository.stage_scope(
        raw_document=raw,
        archive_receipt=receipt,
        manifest=manifest,
        scope=scope,
        staged_by_alias="pytest-base-scope",
    )
    assert first["scope_created"] is True
    assert first["resource_count"] == 15
    assert first["publication_eligible"] is False

    repeated_receipt = await repository.archive_raw_document(raw_document=raw)
    repeated = await repository.stage_scope(
        raw_document=raw,
        archive_receipt=repeated_receipt,
        manifest=manifest,
        scope=scope,
        staged_by_alias="pytest-base-scope",
    )
    assert repeated["scope_created"] is False
    assert repeated["scope_id"] == first["scope_id"]

    async with repository.pool.acquire() as connection:
        stored = await connection.fetchrow(
            """
            SELECT resource_count, first_year, closed_through_year, rolling_year,
                   source_sha256, scope_sha256
            FROM base_contract_catalogue_scopes
            WHERE id = $1
            """,
            first["scope_id"],
        )
        states = await connection.fetch(
            """
            SELECT coverage_state, count(*) AS count
            FROM base_contract_catalogue_resources
            WHERE scope_id = $1
            GROUP BY coverage_state
            ORDER BY coverage_state
            """,
            first["scope_id"],
        )
        after = await connection.fetchrow(
            """
            SELECT
              (SELECT count(*) FROM public_contracts) AS contracts,
              (SELECT count(*) FROM interest_relationships) AS relationships,
              (SELECT count(*) FROM contract_match_reviews) AS matches,
              (SELECT count(*) FROM base_staging_batches) AS batches
            """
        )
        with pytest.raises(Exception, match="append-only"):
            await connection.execute(
                "UPDATE base_contract_catalogue_scopes SET resource_count = 1 WHERE id = $1",
                first["scope_id"],
            )

    assert stored is not None
    assert dict(stored) == {
        "resource_count": 15,
        "first_year": 2012,
        "closed_through_year": 2025,
        "rolling_year": 2026,
        "source_sha256": scope.source_sha256,
        "scope_sha256": scope.scope_sha256,
    }
    assert {str(row["coverage_state"]): int(row["count"]) for row in states} == {
        "CURRENT_ROLLING_YEAR": 1,
        "HISTORICAL_CLOSED_YEAR": 14,
    }
    assert dict(after) == dict(before)
