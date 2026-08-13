import argparse
import asyncio
import hashlib
import inspect
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.models.api import ParliamentDataset
from app.models.archive import RawArchiveReceipt
from app.repositories.postgres import (
    PostgresRepository,
    _archive_attestation_sha256,
)
from scripts import archive_source_document, sync_parliament

SOURCE_ID = "source-votes-1"
SOURCE_URL = "https://app.parlamento.pt/IniciativasXVII_json.txt"


def _receipt() -> RawArchiveReceipt:
    digest = hashlib.sha256(b"documento-oficial").hexdigest()
    return RawArchiveReceipt(
        storage_key=f"sha256/{digest[:2]}/{digest}",
        content_sha256=digest,
        byte_size=len(b"documento-oficial"),
        mime_type="application/json",
        source_url=SOURCE_URL,
        retrieved_at=datetime(2026, 8, 3, 8, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 8, 3, 8, 1, tzinfo=UTC),
        object_created=True,
    )


class AttestationConnection:
    def __init__(self, *, existing: bool = False) -> None:
        self.existing = existing
        self.queries: list[str] = []
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.inserted_row: dict[str, Any] | None = None

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any] | None:
        self.queries.append(query)
        if "FOR UPDATE" in query:
            return {
                "id": SOURCE_ID,
                "url": SOURCE_URL,
                "content_sha256": _receipt().content_sha256,
            }
        if "INSERT INTO source_archive_attestations" in query:
            row = {
                "id": "archive-1",
                "source_document_id": arguments[1],
                "storage_backend": arguments[2],
                "storage_key": arguments[3],
                "content_sha256": arguments[4],
                "byte_size": arguments[5],
                "mime_type": arguments[6],
                "retrieval_url": arguments[7],
                "retrieved_at": arguments[8],
                "archived_at": arguments[9],
                "archived_by": arguments[10],
                "attestation_sha256": arguments[11],
            }
            self.inserted_row = row
            return None if self.existing else row
        if "FROM source_archive_attestations" in query:
            assert self.inserted_row is not None
            return self.inserted_row
        raise AssertionError(f"Consulta inesperada: {query}")

    async def execute(self, query: str, *arguments: object) -> None:
        self.executions.append((query, arguments))


def test_attestation_is_insert_only_and_creates_one_audit_event() -> None:
    connection = AttestationConnection()

    result = asyncio.run(
        PostgresRepository._attest_source_archive(
            connection,  # type: ignore[arg-type]
            source_document_id=SOURCE_ID,
            receipt=_receipt(),
            archived_by="arquivo-v4",
        )
    )

    assert result["created"] is True
    assert result["content_sha256"] == _receipt().content_sha256
    assert len(connection.executions) == 1
    assert "INSERT INTO audit_events" in connection.executions[0][0]
    all_sql = "\n".join(connection.queries + [item[0] for item in connection.executions])
    assert "UPDATE source_archive_attestations" not in all_sql
    assert "DELETE FROM source_archive_attestations" not in all_sql


def test_exact_attestation_retry_is_idempotent_without_second_audit_event() -> None:
    connection = AttestationConnection(existing=True)

    result = asyncio.run(
        PostgresRepository._attest_source_archive(
            connection,  # type: ignore[arg-type]
            source_document_id=SOURCE_ID,
            receipt=_receipt(),
            archived_by="arquivo-v4",
        )
    )

    assert result["created"] is False
    assert connection.executions == []
    assert len(connection.queries) == 3


class WrongSourceConnection(AttestationConnection):
    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any] | None:
        if "FOR UPDATE" in query:
            return {
                "id": SOURCE_ID,
                "url": SOURCE_URL,
                "content_sha256": "a" * 64,
            }
        return await super().fetchrow(query, *arguments)


def test_attestation_rejects_source_hash_mismatch_before_insert() -> None:
    connection = WrongSourceConnection()

    with pytest.raises(ValueError, match="SHA-256"):
        asyncio.run(
            PostgresRepository._attest_source_archive(
                connection,  # type: ignore[arg-type]
                source_document_id=SOURCE_ID,
                receipt=_receipt(),
                archived_by="arquivo-v4",
            )
        )

    assert all(
        "INSERT INTO source_archive_attestations" not in query for query in connection.queries
    )
    assert connection.executions == []


class SourceDocumentConnection:
    def __init__(self) -> None:
        self.query = ""
        self.arguments: tuple[object, ...] = ()

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, str]:
        self.query = query
        self.arguments = arguments
        return {"id": SOURCE_ID}


def test_source_document_reuse_does_not_update_historical_metadata() -> None:
    connection = SourceDocumentConnection()

    result = asyncio.run(
        PostgresRepository._ensure_source_document(
            connection,  # type: ignore[arg-type]
            publisher="PARLIAMENT",
            kind="OPEN_DATASET",
            title="Fotografia parlamentar",
            url=SOURCE_URL,
            retrieved_at=datetime.now(UTC),
            content_sha256="b" * 64,
            mime_type="application/json",
            parser_version="v12",
        )
    )

    assert result == SOURCE_ID
    assert "ON CONFLICT (url, content_sha256) DO NOTHING" in connection.query
    assert "DO UPDATE" not in connection.query
    assert "UPDATE source_documents" not in connection.query


class ExistingSourceDocumentConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, str] | None:
        self.queries.append(query)
        if "INSERT INTO source_documents" in query:
            return None
        assert arguments == (SOURCE_URL, "b" * 64)
        return {"id": SOURCE_ID}


def test_source_document_conflict_uses_a_fresh_read_without_mutation() -> None:
    connection = ExistingSourceDocumentConnection()

    result = asyncio.run(
        PostgresRepository._ensure_source_document(
            connection,  # type: ignore[arg-type]
            publisher="PARLIAMENT",
            kind="OPEN_DATASET",
            title="Fotografia parlamentar",
            url=SOURCE_URL,
            retrieved_at=datetime.now(UTC),
            content_sha256="b" * 64,
            mime_type="application/json",
            parser_version="v12",
        )
    )

    assert result == SOURCE_ID
    assert len(connection.queries) == 2
    assert "ON CONFLICT (url, content_sha256) DO NOTHING" in connection.queries[0]
    assert connection.queries[1].lstrip().startswith("SELECT id")


def test_deputy_persistence_requires_archive_before_database_access() -> None:
    repository = PostgresRepository.__new__(PostgresRepository)
    repository.pool = None
    dataset = ParliamentDataset(
        legislature="XVII",
        dataset_url=SOURCE_URL,
        document_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="arquivo prévio"):
        asyncio.run(
            repository.store_parliament_dataset(
                dataset,
                kind="deputies",
                code_version="v12",
            )
        )


def test_archive_cli_requires_both_explicit_write_confirmations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["archive_source_document", "--source-document-id", SOURCE_ID, "--actor", "auditor"],
    )

    with pytest.raises(SystemExit):
        archive_source_document.arguments()


def test_archive_cli_rejects_non_staging_before_repository_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings

    monkeypatch.setattr(
        archive_source_document,
        "get_settings",
        lambda: Settings(environment="production", raw_archive_root=tmp_path),
    )

    with pytest.raises(RuntimeError, match="ENVIRONMENT=staging"):
        asyncio.run(
            archive_source_document.run(
                argparse.Namespace(
                    source_document_id=SOURCE_ID,
                    actor="auditor",
                    persist_attestation=True,
                    confirm_staging=True,
                )
            )
        )


def test_legacy_vote_persistence_redirects_to_versioned_pipeline_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings

    monkeypatch.setattr(
        sync_parliament,
        "get_settings",
        lambda: Settings(environment="test", raw_archive_root=None),
    )

    with pytest.raises(ValueError, match="sync_parliament_activity"):
        asyncio.run(sync_parliament.collect("votes", "XVII", persist=True))


def test_migration_enforces_append_only_archive_attestations() -> None:
    migration = (
        Path(__file__).parents[2]
        / "prisma"
        / "migrations"
        / "20260803070000_v4_raw_evidence_archive"
        / "migration.sql"
    ).read_text(encoding="utf-8")

    assert 'BEFORE UPDATE OR DELETE ON "source_archive_attestations"' in migration
    assert "ON DELETE RESTRICT" in migration
    assert 'CHECK ("content_sha256" ~' in migration
    assert 'CHECK ("storage_key" ~' in migration
    assert "\"storage_key\" = 'sha256/'" in migration
    assert 'CHECK ("storage_backend" ~' in migration
    assert 'CHECK ("archived_at" >= "retrieved_at")' in migration
    assert 'BEFORE INSERT ON "source_archive_attestations"' in migration
    assert 'source."content_sha256" = NEW."content_sha256"' in migration
    assert 'source."url" = NEW."retrieval_url"' in migration
    assert 'BEFORE UPDATE OF "url", "content_sha256" ON "source_documents"' in migration


class InspectionAcquire:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def __aenter__(self) -> Any:
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class InspectionPool:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def acquire(self) -> InspectionAcquire:
        return InspectionAcquire(self.connection)


class InspectionConnection:
    def __init__(self, *, archived: bool) -> None:
        self.archived = archived
        self.queries: list[str] = []

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any]:
        self.queries.append(query)
        assert arguments == (SOURCE_ID,)
        receipt = _receipt()
        archived_at = receipt.recorded_at.replace(tzinfo=None)
        retrieved_at = receipt.retrieved_at.replace(tzinfo=None)
        attestation_sha256 = _archive_attestation_sha256(
            source_document_id=SOURCE_ID,
            receipt=receipt,
            archived_at=receipt.recorded_at,
            archived_by="arquivo-v4",
        )
        return {
            "source_document_id": SOURCE_ID,
            "publisher": "PARLIAMENT",
            "kind": "OPEN_DATASET",
            "title": "Votações XVII",
            "url": SOURCE_URL,
            "source_retrieved_at": datetime(2026, 8, 3),
            "source_sha256": receipt.content_sha256,
            "source_mime_type": "application/json",
            "archive_attestation_id": "archive-1" if self.archived else None,
            "storage_backend": "FILESYSTEM" if self.archived else None,
            "storage_key": receipt.storage_key if self.archived else None,
            "archive_sha256": receipt.content_sha256 if self.archived else None,
            "byte_size": receipt.byte_size if self.archived else None,
            "archive_mime_type": receipt.mime_type if self.archived else None,
            "retrieval_url": SOURCE_URL if self.archived else None,
            "retrieved_at": retrieved_at if self.archived else None,
            "archived_at": archived_at if self.archived else None,
            "archived_by": "arquivo-v4" if self.archived else None,
            "attestation_sha256": attestation_sha256 if self.archived else None,
        }


def _inspection_repository(connection: InspectionConnection) -> PostgresRepository:
    repository = PostgresRepository.__new__(PostgresRepository)
    repository.pool = InspectionPool(connection)  # type: ignore[assignment]
    return repository


def test_attestation_inspector_is_read_only_and_validates_canonical_hash() -> None:
    connection = InspectionConnection(archived=True)

    report = asyncio.run(
        _inspection_repository(connection).inspect_source_archive_attestation(
            source_document_id=SOURCE_ID,
        )
    )

    assert report["publication_eligible"] is False
    assert report["availability"] == "VERIFICATION_PENDING"
    assert all(report["checks"].values())
    assert len(connection.queries) == 1
    assert connection.queries[0].lstrip().startswith("SELECT")
    assert "INSERT" not in connection.queries[0]
    assert "UPDATE" not in connection.queries[0]
    assert "DELETE" not in connection.queries[0]


def test_attestation_inspector_reports_missing_archive_as_unavailable() -> None:
    report = asyncio.run(
        _inspection_repository(
            InspectionConnection(archived=False)
        ).inspect_source_archive_attestation(source_document_id=SOURCE_ID)
    )

    assert report["archive"] is None
    assert report["availability"] == "UNAVAILABLE"
    assert report["checks"]["archive_attested"] is False
    assert report["checks"]["attestation_hash_valid"] is False


def test_public_projection_queries_require_matching_archive_attestations() -> None:
    status_source = inspect.getsource(PostgresRepository.get_public_data_status)
    people_source = inspect.getsource(PostgresRepository._public_person_rows)
    profile_source = inspect.getsource(PostgresRepository.get_public_politician)
    promises_source = inspect.getsource(PostgresRepository.list_public_promises)
    investigator_source = inspect.getsource(PostgresRepository.get_public_investigator_dataset)
    open_data_source = inspect.getsource(PostgresRepository.list_open_data)

    assert status_source.count("source_archive_attestations") >= 6
    assert "source_archive_attestations profile_archive" in people_source
    assert "source_archive_attestations activity_archive" in profile_source
    assert "source_archive_attestations mandate_archive" in profile_source
    assert "source_archive_attestations vote_archive" in profile_source
    assert "source_archive_attestations declaration_archive" in profile_source
    assert "source_archive_attestations programme_archive" in promises_source
    assert "source_archive_attestations evidence_archive" in promises_source
    assert "source_archive_attestations relationship_archive" in investigator_source
    assert "source_archive_attestations comparison_archive" in investigator_source
    assert "source_archive_attestations all_statement_archive" in investigator_source
    assert "source_archive_attestations vote_archive" in investigator_source
    assert "source_archive_attestations statement_archive" in investigator_source
    assert "contract_archive.source_document_id = sd.id" not in investigator_source
    assert "source_archive_attestations contract_archive" in open_data_source
    assert open_data_source.count("source_archive_attestations") >= 5
