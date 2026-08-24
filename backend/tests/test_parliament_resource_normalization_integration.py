"""Integração do primeiro lote histórico normalizado num PostgreSQL descartável."""

import json
import os
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.repositories.parliament_resource_normalization import (
    ParliamentResourceNormalizationRepository,
)
from app.services.parliament_resource_archive import (
    ParliamentResourceArchiveCollector,
    ParliamentResourceArchiveStager,
)
from app.services.parliament_resource_manifest import (
    ParliamentResourceFormat,
    ParliamentResourceManifestCollector,
    ParliamentResourceManifestStager,
)
from app.services.parliament_resource_normalization import (
    ParliamentResourceNormalizationStager,
    ParliamentResourceNormalizer,
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
async def repository() -> ParliamentResourceNormalizationRepository:
    repo = ParliamentResourceNormalizationRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_normalization_reuses_attested_bytes_and_remains_outside_editorial_cycle(
    repository: ParliamentResourceNormalizationRepository,
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
    catalogue_collection = await ParliamentSourceCatalogueCollector(catalogue_http).collect(
        ParliamentCatalogueKind.INITIATIVES
    )
    catalogue = await ParliamentSourceCatalogueStager(
        Settings(environment="test"),
        repository,
    ).store(
        catalogue_collection,
        code_version=f"parliament-source-catalogue-normalization-parent-{suffix}",
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
        parent_catalogue_snapshot_id=str(catalogue["snapshot_id"]),
        candidate_url=candidate_url,
    )
    manifest = await ParliamentResourceManifestStager(
        Settings(environment="test"),
        repository,
    ).store(
        manifest_collection,
        code_version=f"parliament-resource-manifest-normalization-parent-{suffix}",
    )

    resource_body = json.dumps(
        {
            "Iniciativas": [
                {
                    "IniId": f"initiative-{suffix}",
                    "IniNr": f"1/XVII/{suffix}",
                    "IniDescTipo": "Projeto de Lei",
                    "IniTitulo": f"Iniciativa oficial {suffix}",
                    "IniLinkTexto": (
                        f"/ActividadeParlamentar/Paginas/DetalheIniciativa.aspx?BID={suffix}"
                    ),
                    "IniDataEntrada": "2026-08-01",
                    "IniSituacao": "Entrada",
                }
            ]
        },
        ensure_ascii=False,
    ).encode()
    manifest_proof = await repository.require_resource_candidate(
        catalogue_snapshot_id=str(catalogue["snapshot_id"]),
        manifest_snapshot_id=str(manifest["snapshot_id"]),
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
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
        max_bytes=1_000_000,
    ).collect(manifest_proof)
    archive = await ParliamentResourceArchiveStager(
        Settings(environment="test"),
        repository,
    ).store(
        archive_collection,
        code_version=f"parliament-resource-archive-normalization-parent-{suffix}",
    )

    archive_proof = await repository.require_archived_resource(
        catalogue_snapshot_id=str(catalogue["snapshot_id"]),
        manifest_snapshot_id=str(manifest["snapshot_id"]),
        archive_snapshot_id=str(archive["snapshot_id"]),
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        resource_format=ParliamentResourceFormat.JSON,
        resource_url=resource_url,
    )
    normalization_collection = ParliamentResourceNormalizer().normalise(archive_proof)
    result = await ParliamentResourceNormalizationStager(
        Settings(environment="test"),
        repository,
    ).store(normalization_collection)

    assert result["parent_catalogue_snapshot_id"] == catalogue["snapshot_id"]
    assert result["parent_manifest_snapshot_id"] == manifest["snapshot_id"]
    assert result["parent_archive_snapshot_id"] == archive["snapshot_id"]
    assert result["records_normalised"] == 1
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
                   session_count, initiative_count, vote_count, vote_record_count
            FROM parliament_activity_snapshots
            WHERE id = $1
            """,
            result["normalised_snapshot_id"],
        )
        initiative = await connection.fetchrow(
            """
            SELECT source_id, legislature, number, title, official_url, source_document_id
            FROM parliamentary_initiatives
            WHERE snapshot_id = $1
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
            """
            SELECT COUNT(*) FROM editorial_cases
            WHERE source_document_id = $1
            """,
            result["source_document_id"],
        )
        publication_count = await connection.fetchval(
            """
            SELECT COUNT(*) FROM editorial_publication_events
            WHERE target_id = $1
            """,
            result["normalised_snapshot_id"],
        )

    assert snapshot is not None
    assert snapshot["source_document_id"] == archive["source_document_id"]
    assert snapshot["legislature"] == "XVII"
    assert snapshot["parser_version"] == "parliament-historical-initiatives-v1"
    assert snapshot["session_count"] == 0
    assert snapshot["initiative_count"] == 1
    assert snapshot["vote_count"] == 0
    assert snapshot["vote_record_count"] == 0
    assert initiative is not None
    assert initiative["source_id"] == f"initiative-{suffix}"
    assert initiative["legislature"] == "XVII"
    assert initiative["number"] == f"1/XVII/{suffix}"
    assert initiative["title"] == f"Iniciativa oficial {suffix}"
    assert initiative["official_url"].startswith("https://www.parlamento.pt/")
    assert initiative["source_document_id"] == archive["source_document_id"]
    assert sync_run is not None
    assert sync_run["status"] == "PARTIAL"
    assert sync_run["records_read"] == 1
    assert sync_run["records_written"] == 1
    warnings = (
        json.loads(sync_run["warnings"])
        if isinstance(sync_run["warnings"], str)
        else sync_run["warnings"]
    )
    assert warnings == [
        "Cobertura histórica não afirmada: esta fotografia contém apenas "
        "iniciativas observadas num único recurso oficial arquivado."
    ]
    assert editorial_case_count == 0
    assert publication_count == 0
