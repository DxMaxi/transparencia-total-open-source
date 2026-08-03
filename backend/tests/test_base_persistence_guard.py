import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.security import hmac_protected_identifier
from app.models.api import BaseContractCollection
from app.repositories.postgres import (
    BASE_PERSISTENCE_DISABLED_MESSAGE,
    PostgresRepository,
)
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


def test_store_base_collection_fails_before_sync_run_or_database_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PostgresRepository(Settings(environment="test", database_url=None))
    pool = WriteTrackingPool()
    repository.pool = cast(Any, pool)
    start_sync_run = AsyncMock(
        side_effect=AssertionError("A barreira BASE não pode criar um SyncRun")
    )
    monkeypatch.setattr(repository, "_start_sync_run", start_sync_run)

    with pytest.raises(RuntimeError, match="carga em lote append-only") as error:
        asyncio.run(
            repository.store_base_collection(
                cast(BaseContractCollection, object()),
                code_version="base-ingestion-unsafe",
            )
        )

    assert str(error.value) == BASE_PERSISTENCE_DISABLED_MESSAGE
    assert start_sync_run.await_count == 0
    assert pool.acquire_calls == 0


def test_cli_refuses_persist_before_collection(
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
    assert BASE_PERSISTENCE_DISABLED_MESSAGE in capsys.readouterr().err


def test_direct_cli_run_also_refuses_persist() -> None:
    args = argparse.Namespace(persist=True)

    with pytest.raises(RuntimeError) as error:
        asyncio.run(run(args))

    assert str(error.value) == BASE_PERSISTENCE_DISABLED_MESSAGE


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
