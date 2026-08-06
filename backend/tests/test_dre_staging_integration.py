"""Testes reais do circuito DRE privado e append-only.

Exigem PostgreSQL descartável com todas as migrações aplicadas. Sem
DATABASE_URL, o módulo é ignorado.
"""

import hashlib
import os
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import sha256_text
from app.models.api import LegalDocument
from app.models.archive import PrivateRawDocument
from app.repositories.dre_staging import DreStagingRepository
from app.services.raw_archive import ContentAddressedFileArchive

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


def _document() -> LegalDocument:
    content = (
        b"<html><body><h1>Lei n. 1/2026</h1><main>"
        + (b"Texto oficial demonstrativo para teste de persistencia privada. " * 8)
        + b"</main></body></html>"
    )
    retrieved_at = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)
    content_sha256 = hashlib.sha256(content).hexdigest()
    text = "Texto oficial demonstrativo para teste de persistência privada. " * 8
    raw = PrivateRawDocument(
        source_url=HttpUrl("https://data.dre.pt/eli/lei/1/2026/01/01/p/dre/pt/html"),
        retrieved_at=retrieved_at,
        content_sha256=content_sha256,
        mime_type="text/html",
        content=content,
    )
    return LegalDocument(
        title="Lei n.º 1/2026",
        source_url=raw.source_url,
        official_identifier="Lei n.º 1/2026",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        text=text,
        content_sha256=content_sha256,
        normalised_text_sha256=sha256_text(text),
        raw_document=raw,
    )


@pytest.fixture
async def repo(tmp_path) -> DreStagingRepository:
    settings = Settings(
        environment="test",
        raw_archive_root=tmp_path / "raw-archive",
    )
    repository = DreStagingRepository(settings)
    await repository.connect()
    try:
        yield repository
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_dre_requires_archive_before_database(repo: DreStagingRepository) -> None:
    with pytest.raises(ValueError, match="arquivo prévio"):
        await repo.store_dre_document(_document(), code_version="dre-test-v1")


@pytest.mark.asyncio
async def test_dre_private_chain_is_idempotent_and_not_public(
    repo: DreStagingRepository,
) -> None:
    document = _document()
    assert document.raw_document is not None
    archive = ContentAddressedFileArchive.from_settings(repo.settings)
    receipt = archive.archive(document.raw_document)

    first = await repo.store_dre_document(
        document,
        code_version="dre-test-v1",
        archive_receipt=receipt,
    )
    second = await repo.store_dre_document(
        document,
        code_version="dre-test-v1",
        archive_receipt=receipt,
    )

    assert first["snapshot_created"] is True
    assert second["snapshot_created"] is False
    assert first["snapshot_id"] == second["snapshot_id"]

    async with repo.pool.acquire() as connection:
        snapshot_count = await connection.fetchval(
            "SELECT count(*) FROM dre_document_snapshots WHERE id = $1",
            first["snapshot_id"],
        )
        public_law_count = await connection.fetchval(
            "SELECT count(*) FROM laws WHERE official_identifier = $1",
            document.official_identifier,
        )
        review_count = await connection.fetchval(
            """
            SELECT count(*) FROM data_publication_reviews
            WHERE entity_type = 'DRE_DOCUMENT_SNAPSHOT' AND entity_id = $1
            """,
            first["snapshot_id"],
        )
    assert snapshot_count == 1
    assert public_law_count == 0
    assert review_count == 0


@pytest.mark.asyncio
async def test_dre_snapshot_is_append_only_and_inspection_hides_text(
    repo: DreStagingRepository,
) -> None:
    document = _document()
    assert document.raw_document is not None
    receipt = ContentAddressedFileArchive.from_settings(repo.settings).archive(
        document.raw_document
    )
    stored = await repo.store_dre_document(
        document,
        code_version="dre-test-v2",
        archive_receipt=receipt,
    )

    async with repo.pool.acquire() as connection:
        with pytest.raises(Exception, match="append-only"):
            await connection.execute(
                "UPDATE dre_document_snapshots SET title = 'alterado' WHERE id = $1",
                stored["snapshot_id"],
            )
        with pytest.raises(Exception, match="append-only"):
            await connection.execute(
                "DELETE FROM dre_document_snapshots WHERE id = $1",
                stored["snapshot_id"],
            )

    report = await repo.inspect_dre_staging(
        official_identifier=document.official_identifier,
    )
    assert report["publishable"] is False
    assert report["extracted_text_included"] is False
    assert "extracted_text" not in report
    assert all(report["checks"].values())
