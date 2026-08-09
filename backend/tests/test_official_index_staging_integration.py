"""Integração real do arquivo privado de índices oficiais.

Exige PostgreSQL descartável com todas as migrações aplicadas. Sem
``DATABASE_URL``, o módulo é ignorado para manter o desenvolvimento local leve.
"""

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.official_index_staging import (
    OfficialIndexItem,
    OfficialIndexStagingRepository,
)
from app.services.transparency_entity import EPT_PORTAL_FALLBACK_WARNING

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
async def test_partial_contingency_keeps_bytes_warning_and_audit_event(
    repository: OfficialIndexStagingRepository,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    content = f"official-ept-contingency-{suffix}".encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    retrieved_at = datetime.now(UTC)
    raw_document = PrivateRawDocument(
        source_url=HttpUrl("https://entidadetransparencia.pt/"),
        retrieved_at=retrieved_at,
        content_sha256=content_sha256,
        mime_type="text/html",
        content=content,
    )
    source_name = f"EPT_CONTINGENCY_TEST_{suffix}"
    code_version = "official-index-integration-v1"

    result = await repository.store_index(
        source_name=source_name,
        publisher="TRANSPARENCY_ENTITY",
        title="Entidade para a Transparência — portal oficial de contingência",
        raw_document=raw_document,
        resources=[],
        code_version=code_version,
        status_value="PARTIAL",
        warnings=[EPT_PORTAL_FALLBACK_WARNING],
    )

    assert result["status"] == "PARTIAL"
    assert result["publishable"] is False
    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        sync_run = await connection.fetchrow(
            """
            SELECT status::text AS status, dataset_url, warnings, code_version
            FROM sync_runs WHERE id = $1
            """,
            result["sync_run_id"],
        )
        snapshot = await connection.fetchrow(
            """
            SELECT publishable, resource_count, parser_version
            FROM official_index_snapshots WHERE id = $1
            """,
            result["snapshot_id"],
        )
        attestation = await connection.fetchrow(
            """
            SELECT retrieval_url, content_sha256
            FROM source_archive_attestations WHERE source_document_id = $1
            """,
            result["source_document_id"],
        )
        audit = await connection.fetchrow(
            """
            SELECT after_json, reason
            FROM audit_events
            WHERE entity_type = 'OFFICIAL_INDEX_SNAPSHOT' AND entity_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            result["snapshot_id"],
        )

    assert sync_run is not None
    assert sync_run["status"] == "PARTIAL"
    assert sync_run["dataset_url"] == "https://entidadetransparencia.pt/"
    assert _decode_json(sync_run["warnings"]) == [EPT_PORTAL_FALLBACK_WARNING]
    assert sync_run["code_version"] == code_version
    assert snapshot is not None
    assert snapshot["publishable"] is False
    assert snapshot["resource_count"] == 0
    assert snapshot["parser_version"] == code_version
    assert attestation is not None
    assert attestation["retrieval_url"] == "https://entidadetransparencia.pt/"
    assert attestation["content_sha256"] == content_sha256
    assert audit is not None
    audit_payload = _decode_json(audit["after_json"])
    assert isinstance(audit_payload, dict)
    assert audit_payload["sync_status"] == "PARTIAL"
    assert audit_payload["parser_version"] == code_version
    assert audit_payload["warnings"] == [EPT_PORTAL_FALLBACK_WARNING]
    assert audit_payload["publishable"] is False
    assert audit["reason"] == (
        "Fonte oficial de contingência preservada como parcial e sem publicação"
    )


@pytest.mark.asyncio
async def test_partial_index_without_an_explicit_warning_is_rejected(
    repository: OfficialIndexStagingRepository,
) -> None:
    content = b"partial-without-warning-must-fail"
    raw_document = PrivateRawDocument(
        source_url=HttpUrl("https://entidadetransparencia.pt/"),
        retrieved_at=datetime.now(UTC),
        content_sha256=hashlib.sha256(content).hexdigest(),
        mime_type="text/html",
        content=content,
    )

    with pytest.raises(ValueError, match="aviso explícito"):
        await repository.store_index(
            source_name=f"EPT_INVALID_PARTIAL_TEST_{uuid.uuid4().hex[:12]}",
            publisher="TRANSPARENCY_ENTITY",
            title="Contingência inválida sem aviso",
            raw_document=raw_document,
            resources=[],
            code_version="official-index-integration-v1",
            status_value="PARTIAL",
            warnings=[],
        )


@pytest.mark.asyncio
async def test_reparsing_the_same_bytes_appends_a_versioned_private_snapshot(
    repository: OfficialIndexStagingRepository,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    content = f"versioned-official-index-{suffix}".encode()
    raw_document = PrivateRawDocument(
        source_url=HttpUrl("https://entidadetransparencia.pt/"),
        retrieved_at=datetime.now(UTC),
        content_sha256=hashlib.sha256(content).hexdigest(),
        mime_type="text/html",
        content=content,
    )
    source_name = f"EPT_VERSIONED_TEST_{suffix}"
    warning = [EPT_PORTAL_FALLBACK_WARNING]
    first_resources = [
        OfficialIndexItem(
            title="Informação institucional",
            url="https://entidadetransparencia.pt/informacao",
        )
    ]
    second_resources = [
        *first_resources,
        OfficialIndexItem(
            title="Contactos",
            url="https://entidadetransparencia.pt/contactos",
        ),
    ]

    first = await repository.store_index(
        source_name=source_name,
        publisher="TRANSPARENCY_ENTITY",
        title="EPT — interpretação privada v1",
        raw_document=raw_document,
        resources=first_resources,
        code_version="official-index-parser-v1",
        status_value="PARTIAL",
        warnings=warning,
    )
    second = await repository.store_index(
        source_name=source_name,
        publisher="TRANSPARENCY_ENTITY",
        title="EPT — interpretação privada v2",
        raw_document=raw_document,
        resources=second_resources,
        code_version="official-index-parser-v2",
        status_value="PARTIAL",
        warnings=warning,
    )
    repeated_second = await repository.store_index(
        source_name=source_name,
        publisher="TRANSPARENCY_ENTITY",
        title="EPT — interpretação privada v2",
        raw_document=raw_document,
        resources=second_resources,
        code_version="official-index-parser-v2",
        status_value="PARTIAL",
        warnings=warning,
    )

    assert first["source_document_id"] == second["source_document_id"]
    assert first["snapshot_id"] != second["snapshot_id"]
    assert first["snapshot_created"] is True
    assert second["snapshot_created"] is True
    assert repeated_second["snapshot_created"] is False
    assert repeated_second["snapshot_id"] == second["snapshot_id"]

    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        snapshots = await connection.fetch(
            """
            SELECT id, parser_version, resource_count, publishable
            FROM official_index_snapshots
            WHERE source_document_id = $1
            ORDER BY parser_version
            """,
            first["source_document_id"],
        )

    assert [
        (
            row["id"],
            row["parser_version"],
            row["resource_count"],
            row["publishable"],
        )
        for row in snapshots
    ] == [
        (first["snapshot_id"], "official-index-parser-v1", 1, False),
        (second["snapshot_id"], "official-index-parser-v2", 2, False),
    ]

    divergent_same_version = [
        first_resources[0],
        OfficialIndexItem(
            title="Outra ligação",
            url="https://entidadetransparencia.pt/outra-ligacao",
        ),
    ]
    with pytest.raises(ValueError, match="snapshot existente diverge"):
        await repository.store_index(
            source_name=source_name,
            publisher="TRANSPARENCY_ENTITY",
            title="EPT — divergência privada v2",
            raw_document=raw_document,
            resources=divergent_same_version,
            code_version="official-index-parser-v2",
            status_value="PARTIAL",
            warnings=warning,
        )
