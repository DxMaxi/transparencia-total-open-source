import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.archive import PrivateRawDocument, RawArchiveReceipt
from app.services.raw_archive import (
    ContentAddressedFileArchive,
    RawArchiveConfigurationError,
    RawArchiveIntegrityError,
)

SOURCE_URL = "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx"


def _document(content: bytes = b'{"fonte":"oficial"}') -> PrivateRawDocument:
    return PrivateRawDocument(
        source_url=SOURCE_URL,
        retrieved_at=datetime(2026, 8, 2, 8, 0, tzinfo=UTC),
        content_sha256=hashlib.sha256(content).hexdigest(),
        mime_type="application/json; charset=utf-8",
        content=content,
    )


def test_private_raw_document_never_serialises_or_reprs_bytes() -> None:
    raw = _document(b"SEGREDO-DE-TESTE-NO-ORIGINAL")

    dumped = raw.model_dump(mode="json")
    serialised = raw.model_dump_json()

    assert "content" not in dumped
    assert "SEGREDO-DE-TESTE" not in serialised
    assert "SEGREDO-DE-TESTE" not in repr(raw)
    assert raw.mime_type == "application/json"


def test_private_raw_document_rejects_hash_mismatch_without_echoing_bytes() -> None:
    sensitive = b"VALOR-QUE-NAO-DEVE-SER-ECOADO"

    with pytest.raises(ValidationError) as error:
        PrivateRawDocument(
            source_url=SOURCE_URL,
            retrieved_at=datetime.now(UTC),
            content_sha256="a" * 64,
            content=sensitive,
        )

    assert sensitive.decode() not in str(error.value)
    assert "não corresponde" in str(error.value)


def test_archive_creates_content_addressed_object_and_is_idempotent(tmp_path: Path) -> None:
    archive = ContentAddressedFileArchive(tmp_path)
    raw = _document()

    first = archive.archive(raw)
    target = tmp_path / "sha256" / raw.content_sha256[:2] / raw.content_sha256
    original_mtime = target.stat().st_mtime_ns
    second = archive.archive(raw)

    assert first.storage_key == f"sha256/{raw.content_sha256[:2]}/{raw.content_sha256}"
    assert first.object_created is True
    assert second.object_created is False
    assert target.read_bytes() == raw.content
    assert target.stat().st_mtime_ns == original_mtime
    assert (
        archive.verify(
            storage_key=first.storage_key,
            expected_sha256=first.content_sha256,
            expected_byte_size=first.byte_size,
        ).status
        == "VERIFIED"
    )


def test_archive_never_overwrites_tampered_existing_object(tmp_path: Path) -> None:
    archive = ContentAddressedFileArchive(tmp_path)
    raw = _document()
    receipt = archive.archive(raw)
    target = tmp_path.joinpath(*receipt.storage_key.split("/"))
    target.write_bytes(b"conteudo-adulterado")

    with pytest.raises(RawArchiveIntegrityError, match="diverge"):
        archive.archive(raw)

    assert target.read_bytes() == b"conteudo-adulterado"
    verification = archive.verify(
        storage_key=receipt.storage_key,
        expected_sha256=receipt.content_sha256,
        expected_byte_size=receipt.byte_size,
    )
    assert verification.status == "CORRUPT"
    assert verification.observed_sha256 != receipt.content_sha256


def test_missing_object_is_reported_as_unavailable(tmp_path: Path) -> None:
    archive = ContentAddressedFileArchive(tmp_path)
    digest = hashlib.sha256(b"ausente").hexdigest()

    verification = archive.verify(
        storage_key=archive.storage_key(digest),
        expected_sha256=digest,
        expected_byte_size=7,
    )

    assert verification.status == "UNAVAILABLE"
    assert "indisponível" in verification.detail


def test_unreadable_object_is_reported_as_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = ContentAddressedFileArchive(tmp_path)
    receipt = archive.archive(_document())

    def refuse_read(_path: Path) -> tuple[str, int]:
        raise PermissionError("falha privada simulada")

    monkeypatch.setattr(archive, "_hash_file", refuse_read)

    verification = archive.verify(
        storage_key=receipt.storage_key,
        expected_sha256=receipt.content_sha256,
        expected_byte_size=receipt.byte_size,
    )

    assert verification.status == "UNAVAILABLE"
    assert "falha privada simulada" not in verification.detail
    assert "ler" in verification.detail


def test_archive_rejects_relative_or_repository_internal_roots(tmp_path: Path) -> None:
    with pytest.raises(RawArchiveConfigurationError, match="absoluto"):
        ContentAddressedFileArchive(Path("arquivo-relativo"))

    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    with pytest.raises(RawArchiveConfigurationError, match="fora do repositório"):
        ContentAddressedFileArchive(
            repository_root / "work" / "archive",
            repository_root=repository_root,
        )

    invalid_root = tmp_path / "arquivo.txt"
    invalid_root.write_text("não é um diretório", encoding="utf-8")
    with pytest.raises(RawArchiveConfigurationError, match="diretório"):
        ContentAddressedFileArchive(invalid_root)


def test_archive_rejects_traversal_and_mismatched_receipt_keys(tmp_path: Path) -> None:
    archive = ContentAddressedFileArchive(tmp_path)
    digest = hashlib.sha256(b"teste").hexdigest()

    with pytest.raises(RawArchiveIntegrityError, match="chave"):
        archive.verify(
            storage_key="sha256/../fora",
            expected_sha256=digest,
            expected_byte_size=5,
        )
    with pytest.raises(ValidationError, match="chave"):
        RawArchiveReceipt(
            storage_key=f"sha256/{digest[:2]}/{'a' * 64}",
            content_sha256=digest,
            byte_size=5,
            source_url=SOURCE_URL,
            retrieved_at=datetime.now(UTC),
            object_created=True,
        )


def test_receipt_schema_allows_a_future_private_storage_backend() -> None:
    raw = _document()

    receipt = RawArchiveReceipt(
        storage_backend="S3_VERSIONED",
        storage_key=f"sha256/{raw.content_sha256[:2]}/{raw.content_sha256}",
        content_sha256=raw.content_sha256,
        byte_size=len(raw.content),
        source_url=raw.source_url,
        retrieved_at=raw.retrieved_at,
        object_created=True,
    )

    assert receipt.storage_backend == "S3_VERSIONED"

    invalid_payload = receipt.model_dump()
    invalid_payload["storage_backend"] = "backend-invalido"
    with pytest.raises(ValidationError, match="storage_backend"):
        RawArchiveReceipt.model_validate(invalid_payload)


def test_receipt_rejects_an_attestation_before_collection() -> None:
    raw = _document()

    with pytest.raises(ValidationError, match="anteceder"):
        RawArchiveReceipt(
            storage_key=f"sha256/{raw.content_sha256[:2]}/{raw.content_sha256}",
            content_sha256=raw.content_sha256,
            byte_size=len(raw.content),
            source_url=raw.source_url,
            retrieved_at=datetime(2026, 8, 3, 8, 1, tzinfo=UTC),
            recorded_at=datetime(2026, 8, 3, 8, 0, tzinfo=UTC),
            object_created=True,
        )


def test_failed_atomic_publication_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = ContentAddressedFileArchive(tmp_path)

    def fail_link(_source: object, _target: object) -> None:
        raise PermissionError("falha simulada")

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(PermissionError, match="falha simulada"):
        archive.archive(_document())

    assert list(tmp_path.rglob("*.tmp")) == []
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []


def test_archive_surface_has_no_delete_or_content_read_method(tmp_path: Path) -> None:
    archive = ContentAddressedFileArchive(tmp_path)

    assert not hasattr(archive, "delete")
    assert not hasattr(archive, "read")
