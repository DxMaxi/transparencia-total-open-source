"""Integração da fotografia privada de deputados num PostgreSQL descartável."""

import json
import os
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.repositories.parliament_resource_deputy_normalization import (
    ParliamentResourceDeputyNormalizationRepository,
)
from app.services.parliament_resource_archive import (
    ParliamentResourceArchiveCollector,
    ParliamentResourceArchiveStager,
)
from app.services.parliament_resource_deputy_normalization import (
    ParliamentResourceDeputyNormalizationStager,
    ParliamentResourceDeputyNormalizer,
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
async def repository() -> ParliamentResourceDeputyNormalizationRepository:
    repo = ParliamentResourceDeputyNormalizationRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


def _deputy(index: int, suffix: str) -> dict[str, object]:
    return {
        "Deputado": {
            "DepId": f"deputy-{suffix}-{index}",
            "DepCadId": f"candidate-{suffix}-{index}",
            "DepNomeParlamentar": f"Pessoa Deputada {index:03d}",
            "DepNomeCompleto": f"Pessoa Deputada de Teste {index:03d}",
            "DepCPId": f"constituency-{index % 20}",
            "DepCPDes": f"Círculo {index % 20}",
            "DepGP": [
                {
                    "GpId": f"group-{index % 5}",
                    "GpSigla": f"G{index % 5}",
                    "GpDtInicio": "2025-06-03",
                }
            ],
            "DepSituacao": [
                {
                    "SioDes": "Efetivo",
                    "SioDtInicio": "2025-06-03",
                }
            ],
            "DepCargo": [
                {
                    "CarId": f"office-{suffix}-{index}",
                    "CarDes": "Membro de comissão",
                    "CarDtInicio": "2025-06-10",
                }
            ],
            "DepEmail": f"private-{suffix}-{index}@example.invalid",
        }
    }


@pytest.mark.asyncio
async def test_deputy_normalization_remains_private_and_derived_from_attested_bytes(
    repository: ParliamentResourceDeputyNormalizationRepository,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    catalogue_url = (
        f"https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx?fixture={suffix}"
    )
    candidate_url = (
        "https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx"
        f"?Path=fixture-{suffix}"
    )
    catalogue_body = (f'<a href="?Path=fixture-{suffix}">XVII Legislatura</a>').encode()
    catalogue_http = AsyncMock()
    catalogue_http.get.return_value = httpx.Response(
        200,
        content=catalogue_body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", catalogue_url),
    )
    catalogue_collection = await ParliamentSourceCatalogueCollector(catalogue_http).collect(
        ParliamentCatalogueKind.DEPUTY_ACTIVITY
    )
    catalogue = await ParliamentSourceCatalogueStager(
        Settings(environment="test"),
        repository,
    ).store(
        catalogue_collection,
        code_version=f"parliament-source-catalogue-deputies-parent-{suffix}",
    )

    resource_url = (
        "https://app.parlamento.pt/webutils/docs/doc.txt"
        f"?fich=AtividadeDeputadoXVII_{suffix}_json.txt&Inline=true"
    )
    folder_body = (
        f'<a href="{resource_url.replace("&", "&amp;")}">'
        f"AtividadeDeputadoXVII_{suffix}_json.txt</a>"
    ).encode()
    folder_http = AsyncMock()
    folder_http.get.return_value = httpx.Response(
        200,
        content=folder_body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", candidate_url),
    )
    manifest_collection = await ParliamentResourceManifestCollector(folder_http).collect(
        catalogue_kind=ParliamentCatalogueKind.DEPUTY_ACTIVITY,
        legislature="XVII",
        parent_catalogue_snapshot_id=str(catalogue["snapshot_id"]),
        candidate_url=candidate_url,
    )
    manifest = await ParliamentResourceManifestStager(
        Settings(environment="test"),
        repository,
    ).store(
        manifest_collection,
        code_version=f"parliament-resource-manifest-deputies-parent-{suffix}",
    )

    resource_body = json.dumps(
        [_deputy(index, suffix) for index in range(100)],
        ensure_ascii=False,
    ).encode()
    manifest_proof = await repository.require_resource_candidate(
        catalogue_snapshot_id=str(catalogue["snapshot_id"]),
        manifest_snapshot_id=str(manifest["snapshot_id"]),
        catalogue_kind=ParliamentCatalogueKind.DEPUTY_ACTIVITY,
        legislature="XVII",
        resource_format=ParliamentResourceFormat.JSON,
        resource_url=resource_url,
    )
    resource_http = AsyncMock()
    resource_http.get.return_value = httpx.Response(
        200,
        content=resource_body,
        headers={"content-type": "application/json; charset=utf-8"},
        request=httpx.Request("GET", resource_url),
    )
    archive_collection = await ParliamentResourceArchiveCollector(
        resource_http,
        max_bytes=2_000_000,
    ).collect(manifest_proof)
    archive = await ParliamentResourceArchiveStager(
        Settings(environment="test"),
        repository,
    ).store(
        archive_collection,
        code_version=f"parliament-resource-archive-deputies-parent-{suffix}",
    )

    archive_proof = await repository.require_archived_resource(
        catalogue_snapshot_id=str(catalogue["snapshot_id"]),
        manifest_snapshot_id=str(manifest["snapshot_id"]),
        archive_snapshot_id=str(archive["snapshot_id"]),
        catalogue_kind=ParliamentCatalogueKind.DEPUTY_ACTIVITY,
        legislature="XVII",
        resource_format=ParliamentResourceFormat.JSON,
        resource_url=resource_url,
    )
    collection = ParliamentResourceDeputyNormalizer().normalise(archive_proof)
    result = await ParliamentResourceDeputyNormalizationStager(
        Settings(environment="test"),
        repository,
    ).store(collection)

    assert result["parent_catalogue_snapshot_id"] == catalogue["snapshot_id"]
    assert result["parent_manifest_snapshot_id"] == manifest["snapshot_id"]
    assert result["parent_archive_snapshot_id"] == archive["snapshot_id"]
    assert result["records_normalised"] == 400
    assert result["historical_completeness"] == "NOT_ASSERTED"
    assert result["sync_status"] == "PARTIAL"
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False

    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        snapshot = await connection.fetchrow(
            """
            SELECT source_document_id, legislature, parser_version,
                   deputy_count, group_period_count, situation_period_count,
                   office_period_count
            FROM parliament_deputy_snapshots
            WHERE id = $1
            """,
            result["normalised_snapshot_id"],
        )
        observation = await connection.fetchrow(
            """
            SELECT source_id, candidate_source_id, constituency_source_id,
                   constituency_label, parliamentary_groups,
                   mandate_situations, offices
            FROM parliament_deputy_observations
            WHERE snapshot_id = $1
            ORDER BY source_id
            LIMIT 1
            """,
            result["normalised_snapshot_id"],
        )
        sync_run = await connection.fetchrow(
            """
            SELECT status::text AS status, records_read, records_written, warnings
            FROM sync_runs
            WHERE id = $1
            """,
            result["sync_run_id"],
        )
        editorial_case_count = await connection.fetchval(
            "SELECT COUNT(*) FROM editorial_cases WHERE source_document_id = $1",
            result["source_document_id"],
        )
        publication_count = await connection.fetchval(
            """
            SELECT COUNT(*) FROM editorial_publication_events
            WHERE target_id = $1
            """,
            result["normalised_snapshot_id"],
        )
        people_count = await connection.fetchval(
            "SELECT COUNT(*) FROM people WHERE source_id LIKE $1",
            f"deputy-{suffix}-%",
        )
        contact_columns = await connection.fetchval(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'parliament_deputy_observations'
              AND column_name IN ('email', 'nif', 'nipc', 'tax_id')
            """
        )

    assert snapshot is not None
    assert snapshot["source_document_id"] == archive["source_document_id"]
    assert snapshot["legislature"] == "XVII"
    assert snapshot["parser_version"] == "parliament-historical-deputies-v1"
    assert snapshot["deputy_count"] == 100
    assert snapshot["group_period_count"] == 100
    assert snapshot["situation_period_count"] == 100
    assert snapshot["office_period_count"] == 100
    assert observation is not None
    assert observation["source_id"].startswith(f"deputy-{suffix}-")
    assert observation["candidate_source_id"].startswith(f"candidate-{suffix}-")
    assert observation["constituency_source_id"].startswith("constituency-")
    groups = (
        json.loads(observation["parliamentary_groups"])
        if isinstance(observation["parliamentary_groups"], str)
        else observation["parliamentary_groups"]
    )
    situations = (
        json.loads(observation["mandate_situations"])
        if isinstance(observation["mandate_situations"], str)
        else observation["mandate_situations"]
    )
    offices = (
        json.loads(observation["offices"])
        if isinstance(observation["offices"], str)
        else observation["offices"]
    )
    assert len(groups) == 1
    assert groups[0]["source_id"].startswith("group-")
    assert len(situations) == 1
    assert len(offices) == 1
    assert sync_run is not None
    assert sync_run["status"] == "PARTIAL"
    assert sync_run["records_read"] == 400
    assert sync_run["records_written"] == 100
    warnings = (
        json.loads(sync_run["warnings"])
        if isinstance(sync_run["warnings"], str)
        else sync_run["warnings"]
    )
    assert len(warnings) == 2
    assert editorial_case_count == 0
    assert publication_count == 0
    assert people_count == 0
    assert contact_columns == 0
