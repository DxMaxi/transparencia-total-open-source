"""Integração do catálogo privado do Programa num PostgreSQL descartável."""

import hashlib
import os
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.government_programme import (
    GovernmentProgrammeCatalogue,
    GovernmentProgrammeCatalogueBlock,
    GovernmentProgrammeCatalogueManifest,
    GovernmentProgrammeCoverage,
    GovernmentPromiseCandidate,
)
from app.repositories.government_programme_staging import (
    GovernmentProgrammeStagingRepository,
)
from app.services.government_programme_catalogue import (
    _candidate_digest_payload,
    _sha256_json,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


@pytest.fixture
async def repository() -> GovernmentProgrammeStagingRepository:
    repo = GovernmentProgrammeStagingRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


def _private_catalogue_fixture() -> tuple[
    PrivateRawDocument,
    GovernmentProgrammeCatalogueManifest,
    GovernmentProgrammeCatalogue,
]:
    suffix = uuid.uuid4().hex
    content = (f"%PDF-1.7\nfixture-{suffix}\n".encode() + b"x" * 100_000)[:100_000]
    content_sha256 = hashlib.sha256(content).hexdigest()
    source_url = HttpUrl(f"https://portugal.gov.pt/testes/catalogo-{suffix}.pdf")
    observed_at = datetime.now(UTC).replace(microsecond=0)
    statement = "Medida explicitamente enumerada para teste de integração."
    statement_sha256 = hashlib.sha256(statement.encode()).hexdigest()
    block_id = "test-block"
    area = "Área de teste"
    section_path = "Secção oficial de teste"
    locator_sha256 = _sha256_json(
        {
            "source_sha256": content_sha256,
            "block_id": block_id,
            "ordinal": 1,
            "source_marker": "1.",
            "section_path": section_path,
            "programme_page_start": 1,
            "programme_page_end": 1,
        }
    )
    candidate_key_sha256 = hashlib.sha256(
        f"{content_sha256}:{block_id}:1:{locator_sha256}:{statement_sha256}".encode()
    ).hexdigest()
    candidate = GovernmentPromiseCandidate(
        candidate_key=f"xxv-candidate-{candidate_key_sha256}",
        block_id=block_id,
        ordinal=1,
        parent_ordinal=None,
        hierarchy_level=1,
        source_marker="1.",
        area=area,
        section_path=section_path,
        programme_page_start=1,
        programme_page_end=1,
        statement_text=statement,
        statement_sha256=statement_sha256,
        source_locator_sha256=locator_sha256,
    )
    block_sha256 = _sha256_json([_candidate_digest_payload(candidate)])
    catalogue_sha256 = block_sha256
    block = GovernmentProgrammeCatalogueBlock(
        block_id=block_id,
        part="Teste privado",
        area=area,
        section_path=section_path,
        start_page=1,
        start_anchor="Medidas",
        end_page=1,
        end_anchor=None,
        expected_candidate_count=1,
        expected_block_sha256=block_sha256,
    )
    manifest = GovernmentProgrammeCatalogueManifest(
        government_number="XXV",
        title="Programa do XXV Governo Constitucional — teste privado",
        source_url=source_url,
        source_sha256=content_sha256,
        source_byte_size=len(content),
        source_page_count=1,
        source_retrieved_at=observed_at,
        methodology_version=f"test-method-{suffix}",
        parser_version="government-programme-integration-test-v1",
        scope_statement=(
            "Candidato privado de integração, sem revisão, conclusão ou publicação automática."
        ),
        expected_candidate_count=1,
        expected_catalogue_sha256=catalogue_sha256,
        blocks=(block,),
    )
    layout_sha256 = _sha256_json(manifest.model_dump(mode="json"))
    coverage = GovernmentProgrammeCoverage(
        block_id=block.block_id,
        part=block.part,
        area=block.area,
        section_path=block.section_path,
        start_page=1,
        end_page=1,
        start_anchor=block.start_anchor,
        end_anchor=None,
        candidate_count=1,
        block_sha256=block_sha256,
    )
    catalogue = GovernmentProgrammeCatalogue(
        source_sha256=content_sha256,
        source_byte_size=len(content),
        source_page_count=1,
        layout_manifest_sha256=layout_sha256,
        catalogue_sha256=catalogue_sha256,
        candidates=(candidate,),
        coverage=(coverage,),
    )
    raw_document = PrivateRawDocument(
        source_url=source_url,
        retrieved_at=observed_at,
        content_sha256=content_sha256,
        mime_type="application/pdf",
        content=content,
    )
    return raw_document, manifest, catalogue


@pytest.mark.asyncio
async def test_catalogue_is_append_only_private_and_idempotent(
    repository: GovernmentProgrammeStagingRepository,
) -> None:
    raw_document, manifest, catalogue = _private_catalogue_fixture()
    readiness = await repository.require_catalogue_schema()
    assert readiness["ready"] is True

    receipt = await repository.archive_raw_document(raw_document=raw_document)
    first = await repository.stage_catalogue(
        raw_document=raw_document,
        archive_receipt=receipt,
        manifest=manifest,
        catalogue=catalogue,
        staged_by_alias="pytest-v5.48",
    )
    second = await repository.stage_catalogue(
        raw_document=raw_document,
        archive_receipt=receipt,
        manifest=manifest,
        catalogue=catalogue,
        staged_by_alias="pytest-v5.48",
    )

    assert first["snapshot_created"] is True
    assert second["snapshot_created"] is False
    assert first["publication_performed"] is False
    assert first["public_promises_created"] == 0
    assert first["promise_reviews_created"] == 0
    assert repository.pool is not None
    async with repository.pool.acquire() as connection:
        snapshot = await connection.fetchrow(
            """
            SELECT catalogue_state, publication_performed, candidate_count,
                   coverage_block_count
            FROM government_programme_snapshots
            WHERE id = $1
            """,
            first["snapshot_id"],
        )
        candidate = await connection.fetchrow(
            """
            SELECT criterion_state, review_state, publication_state,
                   publication_performed
            FROM government_promise_candidates
            WHERE snapshot_id = $1
            """,
            first["snapshot_id"],
        )
        audit_count = await connection.fetchval(
            """
            SELECT count(*) FROM audit_events
            WHERE entity_type = 'GOVERNMENT_PROGRAMME_CATALOGUE'
              AND entity_id = $1
            """,
            first["snapshot_id"],
        )
        public_programmes = await connection.fetchval(
            "SELECT count(*) FROM government_programmes WHERE source_document_id = $1",
            first["source_document_id"],
        )
        public_reviews = await connection.fetchval(
            "SELECT count(*) FROM promise_reviews WHERE source_document_id = $1",
            first["source_document_id"],
        )

        assert snapshot is not None
        assert snapshot["catalogue_state"] == "PRIVATE_PENDING_REVIEW"
        assert snapshot["publication_performed"] is False
        assert snapshot["candidate_count"] == 1
        assert snapshot["coverage_block_count"] == 1
        assert candidate is not None
        assert candidate["criterion_state"] == "REQUIRES_HUMAN_DEFINITION"
        assert candidate["review_state"] == "PENDING"
        assert candidate["publication_state"] == "PRIVATE_NOT_PUBLISHED"
        assert candidate["publication_performed"] is False
        assert audit_count == 1
        assert public_programmes == 0
        assert public_reviews == 0

        with pytest.raises(Exception, match="append-only"):
            await connection.execute(
                "UPDATE government_promise_candidates SET review_state = 'ACCEPT' "
                "WHERE snapshot_id = $1",
                first["snapshot_id"],
            )
