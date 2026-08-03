import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.security import hmac_protected_identifier
from app.models.api import BaseContractCollection
from app.models.archive import RawArchiveReceipt
from app.repositories.base_staging import (
    BASE_STAGING_ONLY_MESSAGE,
    _base_snapshot_sha256,
)
from app.repositories.postgres import PostgresRepository, _archive_attestation_sha256
from scripts import protect_identifier
from scripts.sync_base_contracts import (
    REPOSITORY_ROOT,
    _require_path_outside_repository,
    _write_private_review,
    arguments,
    run,
)


class WriteTrackingPool:
    def __init__(self) -> None:
        self.acquire_calls = 0

    def acquire(self) -> Any:
        self.acquire_calls += 1
        raise AssertionError("A barreira BASE não pode adquirir uma ligação à base de dados")


COLLECTED_AT = datetime(2026, 8, 3, 9, 30, tzinfo=UTC)
SOURCE_URL = "https://dados.gov.pt/datasets/versioned/contratos2026.json"
TEST_PEPPER = "pepper-de-teste-com-pelo-menos-32-carateres"


def _collection(*, include_identifier_digest: bool = True) -> BaseContractCollection:
    party: dict[str, object] = {
        "name": "Empresa Demonstrativa",
        "role": "CONTRACTOR",
    }
    if include_identifier_digest:
        party["protected_identifier_digest"] = hmac_protected_identifier(
            "123456789", TEST_PEPPER
        )
    return BaseContractCollection.model_validate(
        {
            "dataset_resource": {
                "title": "contratos2026.json",
                "format": "JSON",
                "url": SOURCE_URL,
                "year": 2026,
            },
            "document_sha256": "a" * 64,
            "contracts": [
                {
                    "source_id": "BASE-2026-001",
                    "object": "Aquisição de serviços",
                    "procedure": "PUBLIC_TENDER",
                    "contract_value": "1250.50",
                    "contracting_authorities": [
                        {
                            "name": "Entidade Pública Demonstrativa",
                            "role": "CONTRACTING_AUTHORITY",
                        }
                    ],
                    "contractors": [party],
                    "source": {
                        "publisher": "BASE",
                        "label": "Portal BASE — dump oficial de contratos",
                        "url": SOURCE_URL,
                        "retrieved_at": COLLECTED_AT,
                        "content_sha256": "a" * 64,
                    },
                }
            ],
            "collected_at": COLLECTED_AT,
        }
    )


def _receipt(retrieved_at: datetime = COLLECTED_AT) -> RawArchiveReceipt:
    return RawArchiveReceipt(
        storage_key=f"sha256/aa/{'a' * 64}",
        content_sha256="a" * 64,
        byte_size=123,
        mime_type="application/json",
        source_url=SOURCE_URL,
        retrieved_at=retrieved_at,
        recorded_at=retrieved_at + timedelta(minutes=1),
        object_created=True,
    )


def test_store_base_collection_requires_archive_before_sync_run_or_database_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PostgresRepository(Settings(environment="test", database_url=None))
    pool = WriteTrackingPool()
    repository.pool = cast(Any, pool)
    start_sync_run = AsyncMock(
        side_effect=AssertionError("A barreira BASE não pode criar um SyncRun")
    )
    monkeypatch.setattr(repository, "_start_sync_run", start_sync_run)

    with pytest.raises(ValueError, match="arquivo prévio"):
        asyncio.run(
            repository.store_base_collection(
                _collection(),
                code_version="base-ingestion-v5",
            )
        )

    assert start_sync_run.await_count == 0
    assert pool.acquire_calls == 0


def test_store_base_collection_refuses_non_staging_before_validation_or_write() -> None:
    repository = PostgresRepository(Settings(environment="development", database_url=None))
    pool = WriteTrackingPool()
    repository.pool = cast(Any, pool)

    with pytest.raises(RuntimeError) as error:
        asyncio.run(
            repository.store_base_collection(
                _collection(),
                code_version="base-ingestion-v5",
                archive_receipt=_receipt(),
            )
        )

    assert str(error.value) == BASE_STAGING_ONLY_MESSAGE
    assert pool.acquire_calls == 0


def test_cli_requires_explicit_staging_confirmation_before_collection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_base_contracts",
            "--year",
            "2026",
            "--output",
            "base-review.json",
            "--persist",
        ],
    )

    with pytest.raises(SystemExit) as error:
        arguments()

    assert error.value.code == 2
    assert "--confirm-staging" in capsys.readouterr().err


def test_cli_refuses_to_persist_a_limited_sample(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_base_contracts",
            "--year",
            "2026",
            "--output",
            "base-review.json",
            "--limit",
            "10",
            "--persist",
            "--confirm-staging",
        ],
    )

    with pytest.raises(SystemExit) as error:
        arguments()

    assert error.value.code == 2
    assert "amostra" in capsys.readouterr().err


def test_direct_cli_run_also_requires_staging_confirmation() -> None:
    args = argparse.Namespace(persist=True, confirm_staging=False, limit=None)

    with pytest.raises(RuntimeError, match="confirmação explícita"):
        asyncio.run(run(args))


def test_cli_archives_before_opening_database_and_keeps_review_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    settings = Settings(
        environment="staging",
        database_url=None,
        raw_archive_root=tmp_path / "raw-archive",
        protected_identifier_pepper=TEST_PEPPER,
    )
    collection = _collection().model_copy(
        update={"raw_document": cast(Any, object())}
    )

    class FakeHttp:
        def __init__(self, _settings: Settings) -> None:
            events.append("http-configured")

        async def __aenter__(self) -> "FakeHttp":
            events.append("http-enter")
            return self

        async def __aexit__(self, *_args: object) -> None:
            events.append("http-exit")

    class FakeCollector:
        def __init__(self, _settings: Settings, _http: FakeHttp) -> None:
            pass

        async def collect(
            self,
            year: int,
            *,
            limit: int | None,
        ) -> BaseContractCollection:
            assert year == 2026
            assert limit is None
            events.append("collected")
            return collection

    class FakeArchive:
        def archive(self, _raw_document: object) -> RawArchiveReceipt:
            events.append("archived")
            return _receipt()

    class FakeArchiveFactory:
        @classmethod
        def from_settings(cls, supplied: Settings) -> FakeArchive:
            assert supplied is settings
            events.append("archive-configured")
            return FakeArchive()

    class FakeRepository:
        def __init__(self, supplied: Settings) -> None:
            assert supplied is settings
            assert "archived" in events
            events.append("repository-created")

        async def connect(self) -> None:
            events.append("database-connected")

        async def store_base_collection(
            self,
            supplied: BaseContractCollection,
            *,
            code_version: str,
            archive_receipt: RawArchiveReceipt,
        ) -> dict[str, int]:
            assert supplied is collection
            assert code_version == "base-ingestion-v5"
            assert archive_receipt == _receipt()
            events.append("stored")
            return {
                "contracts_written": 1,
                "parties_written": 2,
                "archive_attestations_written": 1,
            }

        async def close(self) -> None:
            events.append("database-closed")

    monkeypatch.setattr("scripts.sync_base_contracts.Settings", lambda **_kwargs: settings)
    monkeypatch.setattr("scripts.sync_base_contracts.OfficialHttpClient", FakeHttp)
    monkeypatch.setattr("scripts.sync_base_contracts.BaseGovCollector", FakeCollector)
    monkeypatch.setattr(
        "scripts.sync_base_contracts.ContentAddressedFileArchive",
        FakeArchiveFactory,
    )
    monkeypatch.setattr("scripts.sync_base_contracts.PostgresRepository", FakeRepository)
    output = tmp_path / "base-2026-review.json"
    args = argparse.Namespace(
        persist=True,
        confirm_staging=True,
        limit=None,
        output=output,
        actors_file=None,
        year=2026,
        resource_url=None,
    )

    result = asyncio.run(run(args))

    assert result == {
        "contracts_written": 1,
        "parties_written": 2,
        "archive_attestations_written": 1,
    }
    assert events.index("archive-configured") < events.index("http-enter")
    assert events.index("archived") < events.index("repository-created")
    assert events.index("archived") < events.index("database-connected")
    exported = output.read_text(encoding="utf-8")
    assert "123456789" not in exported
    assert hmac_protected_identifier("123456789", TEST_PEPPER) not in exported


class TransactionContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class AcquireContext:
    def __init__(self, connection: "BatchConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "BatchConnection":
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class BatchConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.copies: dict[str, list[tuple[object, ...]]] = {}

    def transaction(self) -> TransactionContext:
        return TransactionContext()

    async def execute(self, query: str, *arguments: object) -> None:
        self.executions.append((query, arguments))

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, object]:
        assert "INSERT INTO base_staging_batches" in query
        return {"id": arguments[0]}

    async def copy_records_to_table(
        self,
        table_name: str,
        *,
        records: object,
        columns: tuple[str, ...],
    ) -> None:
        del columns
        self.copies[table_name] = list(records)  # type: ignore[arg-type]


class BatchPool:
    def __init__(self, connection: BatchConnection) -> None:
        self.connection = connection

    def acquire(self) -> AcquireContext:
        return AcquireContext(self.connection)


def _repository_with_batch_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pepper: str | None,
    connection: BatchConnection | None = None,
) -> tuple[PostgresRepository, BatchConnection, AsyncMock, AsyncMock]:
    repository = PostgresRepository(
        Settings(
            environment="test",
            database_url=None,
            protected_identifier_pepper=pepper,
        )
    )
    connection = connection or BatchConnection()
    repository.pool = cast(Any, BatchPool(connection))
    start_sync = AsyncMock(return_value="sync-base-1")
    finish_sync = AsyncMock()
    monkeypatch.setattr(repository, "_start_sync_run", start_sync)
    monkeypatch.setattr(repository, "_finish_sync_run", finish_sync)
    monkeypatch.setattr(
        repository,
        "_ensure_source_document",
        AsyncMock(return_value="source-base-1"),
    )
    monkeypatch.setattr(
        repository,
        "_attest_source_archive",
        AsyncMock(return_value={"id": "archive-base-1", "created": True}),
    )
    return repository, connection, start_sync, finish_sync


def test_base_snapshot_uses_private_append_only_tables_and_never_public_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, connection, start_sync, finish_sync = _repository_with_batch_fakes(
        monkeypatch,
        pepper=TEST_PEPPER,
    )

    result = asyncio.run(
        repository.store_base_collection(
            _collection(),
            code_version="base-ingestion-v5",
            archive_receipt=_receipt(),
        )
    )

    assert result == {
        "records_read": 1,
        "records_written": 3,
        "contracts_written": 1,
        "parties_written": 2,
        "batch_created": 1,
        "archive_attestations_written": 1,
        "identifier_digests_written": 1,
    }
    assert set(connection.copies) == {
        "base_contract_snapshots",
        "base_contract_party_snapshots",
    }
    party_rows = connection.copies["base_contract_party_snapshots"]
    assert party_rows[1][5] == hmac_protected_identifier("123456789", TEST_PEPPER)
    assert "123456789" not in repr(connection.copies)
    statements = "\n".join(query for query, _arguments in connection.executions)
    assert "INSERT INTO audit_events" in statements
    assert "public_contracts" not in statements
    assert "interest_entities" not in statements
    assert "contract_match_reviews" not in statements
    audit_arguments = next(
        arguments
        for query, arguments in connection.executions
        if "INSERT INTO audit_events" in query
    )
    audit_payload = str(audit_arguments[3])
    assert "Empresa Demonstrativa" not in audit_payload
    assert hmac_protected_identifier("123456789", TEST_PEPPER) not in audit_payload
    assert '"publication_eligible": false' in audit_payload
    start_sync.assert_awaited_once()
    finish_sync.assert_awaited_once()


def test_base_snapshot_drops_ephemeral_identifier_digests_and_marks_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, connection, _start_sync, finish_sync = _repository_with_batch_fakes(
        monkeypatch,
        pepper=None,
    )

    result = asyncio.run(
        repository.store_base_collection(
            _collection(),
            code_version="base-ingestion-v5",
            archive_receipt=_receipt(),
        )
    )

    party_rows = connection.copies["base_contract_party_snapshots"]
    assert all(row[5] is None for row in party_rows)
    assert result["identifier_digests_written"] == 0
    finish_kwargs = finish_sync.await_args.kwargs
    assert finish_kwargs["status_value"] == "PARTIAL"
    assert "Dados indisponíveis" in " ".join(finish_kwargs["warnings"])


class ExistingBatchConnection(BatchConnection):
    def __init__(self, existing: dict[str, object]) -> None:
        super().__init__()
        self.existing = existing

    async def fetchrow(
        self,
        query: str,
        *arguments: object,
    ) -> dict[str, object] | None:
        if "INSERT INTO base_staging_batches" in query:
            return None
        assert "FROM base_staging_batches" in query
        assert arguments == ("source-base-1", "base-ingestion-v5")
        return self.existing


def test_exact_base_snapshot_retry_is_idempotent_without_new_rows_or_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _collection()
    repeated_at = datetime(2026, 8, 3, 10, 30, tzinfo=UTC)
    repeated_contracts = [
        contract.model_copy(
            update={
                "source": contract.source.model_copy(
                    update={"retrieved_at": repeated_at}
                )
            }
        )
        for contract in collection.contracts
    ]
    repeated = collection.model_copy(
        update={"collected_at": repeated_at, "contracts": repeated_contracts}
    )
    existing = {
        "id": "base_batch_existing",
        "resource_year": 2026,
        "resource_title": "contratos2026.json",
        "resource_format": "JSON",
        "normalised_sha256": _base_snapshot_sha256(
            repeated,
            persist_identifier_digests=True,
        ),
        "identifier_digests_stored": True,
        "contract_count": 1,
        "party_count": 2,
        "collected_at": COLLECTED_AT.replace(tzinfo=None),
    }
    repository, connection, _start_sync, finish_sync = _repository_with_batch_fakes(
        monkeypatch,
        pepper=TEST_PEPPER,
        connection=ExistingBatchConnection(existing),
    )
    monkeypatch.setattr(
        repository,
        "_attest_source_archive",
        AsyncMock(return_value={"id": "archive-base-1", "created": False}),
    )

    result = asyncio.run(
        repository.store_base_collection(
            repeated,
            code_version="base-ingestion-v5",
            archive_receipt=_receipt(repeated_at),
        )
    )

    assert result["batch_created"] == 0
    assert result["records_written"] == 0
    assert result["archive_attestations_written"] == 0
    assert connection.copies == {}
    assert all("INSERT INTO audit_events" not in query for query, _args in connection.executions)
    assert finish_sync.await_args.kwargs["records_written"] == 0


def test_same_source_and_parser_rejects_divergent_normalisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _collection()
    existing = {
        "id": "base_batch_existing",
        "resource_year": 2026,
        "resource_title": "contratos2026.json",
        "resource_format": "JSON",
        "normalised_sha256": "f" * 64,
        "identifier_digests_stored": True,
        "contract_count": 1,
        "party_count": 2,
        "collected_at": COLLECTED_AT.replace(tzinfo=None),
    }
    repository, connection, _start_sync, finish_sync = _repository_with_batch_fakes(
        monkeypatch,
        pepper=TEST_PEPPER,
        connection=ExistingBatchConnection(existing),
    )

    with pytest.raises(ValueError, match="nova versão do parser"):
        asyncio.run(
            repository.store_base_collection(
                collection,
                code_version="base-ingestion-v5",
                archive_receipt=_receipt(),
            )
        )

    assert connection.copies == {}
    assert finish_sync.await_args.kwargs["status_value"] == "FAILED"
    assert "Empresa Demonstrativa" not in finish_sync.await_args.kwargs["error_message"]


def test_normalised_snapshot_hash_is_stable_and_protects_private_digests() -> None:
    collection = _collection()
    repeated_later = collection.model_copy(
        update={"collected_at": datetime(2026, 8, 3, 10, 30, tzinfo=UTC)}
    )

    first = _base_snapshot_sha256(collection, persist_identifier_digests=True)
    second = _base_snapshot_sha256(repeated_later, persist_identifier_digests=True)
    without_durable_digest = _base_snapshot_sha256(
        collection,
        persist_identifier_digests=False,
    )

    assert first == second
    assert first != without_durable_digest
    assert hmac_protected_identifier("123456789", TEST_PEPPER) not in first


def test_v4_base_migration_enforces_private_append_only_staging() -> None:
    migration = (
        REPOSITORY_ROOT
        / "prisma"
        / "migrations"
        / "20260803080000_v4_base_staging"
        / "migration.sql"
    ).read_text(encoding="utf-8")

    assert 'CREATE TABLE "base_staging_batches"' in migration
    assert 'CREATE TABLE "base_contract_snapshots"' in migration
    assert 'CREATE TABLE "base_contract_party_snapshots"' in migration
    assert 'CREATE TRIGGER "base_staging_batches_append_only"' in migration
    assert 'CREATE TRIGGER "base_contract_snapshots_append_only"' in migration
    assert 'CREATE TRIGGER "base_contract_party_snapshots_append_only"' in migration
    assert 'CREATE TRIGGER "audit_events_append_only"' in migration
    assert "arquivo atestado e SyncRun coerente" in migration
    assert "INSERT INTO public_contracts" not in migration
    assert "INSERT INTO interest_entities" not in migration


def test_base_inspection_does_not_select_names_or_identifier_values() -> None:
    import inspect

    source = inspect.getsource(PostgresRepository.inspect_base_staging)

    assert "party.source_name" not in source
    assert "party.protected_identifier_digest AS" not in source
    assert '"publication_eligible": False' in source
    assert "Dados indisponíveis" in source


class InspectionConnection:
    def __init__(self, *, identifiers_stored: bool) -> None:
        self.identifiers_stored = identifiers_stored

    async def fetchrow(self, query: str, year: int) -> dict[str, object]:
        assert "FROM base_staging_batches" in query
        assert year == 2026
        return {
            "batch_id": "base_batch_1",
            "resource_year": 2026,
            "resource_title": "contratos2026.json",
            "resource_format": "JSON",
            "parser_version": "base-ingestion-v5",
            "normalised_sha256": "b" * 64,
            "identifier_digests_stored": self.identifiers_stored,
            "contract_count": 1,
            "party_count": 2,
            "collected_at": COLLECTED_AT,
            "created_at": COLLECTED_AT,
            "sync_run_id": "sync-base-1",
            "sync_status": "SUCCEEDED",
            "started_at": COLLECTED_AT,
            "finished_at": datetime(2026, 8, 3, 9, 32, tzinfo=UTC),
            "records_read": 1,
            "records_written": 3,
            "warnings": [],
            "error_message": None,
            "code_version": "base-ingestion-v5",
            "source_document_id": "source-base-1",
            "source_publisher": "BASE_GOV",
            "source_kind": "OPEN_DATASET",
            "source_title": "Portal BASE — contratos — 2026",
            "source_url": SOURCE_URL,
            "retrieved_at": COLLECTED_AT,
            "content_sha256": "a" * 64,
            "mime_type": "application/json",
            "archive_attestation_id": "archive-base-1",
            "storage_backend": "FILESYSTEM",
            "storage_key": f"sha256/aa/{'a' * 64}",
            "archive_content_sha256": "a" * 64,
            "byte_size": 123,
            "archive_mime_type": "application/json",
            "retrieval_url": SOURCE_URL,
            "archive_retrieved_at": COLLECTED_AT,
            "archived_at": datetime(2026, 8, 3, 9, 31, tzinfo=UTC),
            "archived_by": "sync:base-ingestion-v5",
            "attestation_sha256": _archive_attestation_sha256(
                source_document_id="source-base-1",
                receipt=_receipt(),
                archived_at=_receipt().recorded_at,
                archived_by="sync:base-ingestion-v5",
            ),
            "observed_contract_count": 1,
            "observed_party_count": 2,
            "protected_identifier_digest_count": 1 if self.identifiers_stored else 0,
        }

    async def fetch(self, query: str, batch_id: str) -> list[dict[str, object]]:
        assert "party.source_name" not in query
        assert batch_id == "base_batch_1"
        return [
            {"dimension": "procedure", "value": "PUBLIC_TENDER", "count": 1},
            {"dimension": "role", "value": "CONTRACTING_AUTHORITY", "count": 1},
            {"dimension": "role", "value": "CONTRACTOR", "count": 1},
        ]


class InspectionPool:
    def __init__(self, connection: InspectionConnection) -> None:
        self.connection = connection

    def acquire(self) -> AcquireContext:
        return AcquireContext(cast(BatchConnection, self.connection))


def test_base_inspection_returns_only_aggregate_private_metadata() -> None:
    repository = PostgresRepository(Settings(environment="test", database_url=None))
    repository.pool = cast(Any, InspectionPool(InspectionConnection(identifiers_stored=False)))

    report = asyncio.run(repository.inspect_base_staging(year=2026))
    exported = json.dumps(report, ensure_ascii=False, default=str)

    assert report["publication_eligible"] is False
    assert report["counts"] == {
        "contracts": 1,
        "parties": 2,
        "protected_identifier_digests": 0,
    }
    assert report["protected_identifier_matching"] == {
        "status": "UNAVAILABLE",
        "description": (
            "Dados indisponíveis: o lote não persistiu digests sem pepper durável."
        ),
    }
    assert all(report["checks"].values())
    assert "Empresa Demonstrativa" not in exported
    assert hmac_protected_identifier("123456789", TEST_PEPPER) not in exported


def test_private_review_is_written_atomically_without_temporary_residue(
    tmp_path: Path,
) -> None:
    output = tmp_path / "base-2026-review.json"
    payload = {"contracts": [], "publication_rule": "PENDING_REVIEW"}

    _write_private_review(output, payload)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_private_review_path_inside_repository_is_refused() -> None:
    unsafe_output = REPOSITORY_ROOT / "data" / "base-2026-review.json"

    with pytest.raises(ValueError, match="fora do repositório"):
        _require_path_outside_repository(
            unsafe_output,
            label="O ficheiro de revisão BASE",
        )


def test_private_review_refuses_to_replace_an_existing_version(tmp_path: Path) -> None:
    output = tmp_path / "base-2026-review.json"
    original = {"version": "original"}
    _write_private_review(output, original)

    with pytest.raises(FileExistsError):
        _write_private_review(output, {"version": "nova"})

    assert json.loads(output.read_text(encoding="utf-8")) == original
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_private_review_removes_temporary_file_when_atomic_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "base-2026-review.json"

    def fail_link(_source: object, _target: object) -> None:
        raise OSError("falha simulada")

    monkeypatch.setattr("scripts.sync_base_contracts.os.link", fail_link)

    with pytest.raises(OSError, match="falha simulada"):
        _write_private_review(output, {"contracts": []})

    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_identifier_helper_outputs_only_hmac(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pepper = "pepper-de-teste-com-pelo-menos-32-carateres"
    plaintext = "123456789"
    monkeypatch.setattr(
        protect_identifier,
        "get_settings",
        lambda: Settings(environment="test", protected_identifier_pepper=pepper),
    )
    monkeypatch.setattr(protect_identifier.getpass, "getpass", lambda _prompt: plaintext)

    protect_identifier.main()

    output = capsys.readouterr().out.strip()
    assert output == hmac_protected_identifier(plaintext, pepper)
    assert plaintext not in output


def test_cli_actor_validation_does_not_echo_plaintext_identifier(tmp_path: Path) -> None:
    plaintext = "123456789"
    actors_file = tmp_path / "actors.json"
    actors_file.write_text(
        json.dumps(
            [
                {
                    "person_id": "person-test",
                    "public_name": "Pessoa Pública",
                    "public_role": "DEPUTY",
                    "official_role_source_url": "https://www.parlamento.pt/",
                    "protected_nif": plaintext,
                }
            ]
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        persist=False,
        output=tmp_path / "base-review.json",
        actors_file=actors_file,
        year=2026,
        resource_url=None,
        limit=1,
    )

    with pytest.raises(ValueError) as error:
        asyncio.run(run(args))

    assert plaintext not in str(error.value)
    assert "digests HMAC-SHA-256" in str(error.value)
