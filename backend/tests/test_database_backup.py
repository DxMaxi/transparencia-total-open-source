from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.services.database_backup import (
    BACKUP_SCHEMA_VERSION,
    CRITICAL_TABLES,
    INVENTORY_SCHEMA_VERSION,
    RESTORE_SCHEMA_VERSION,
    BackupEvidenceError,
    build_backup_manifest,
    build_restore_attestation,
    canonical_json_sha256,
    ensure_stable_inventory,
    validate_backup_ciphertext,
)

STARTED_AT = datetime(2026, 8, 9, 5, 17, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 8, 9, 5, 19, tzinfo=UTC)
OBJECT_KEY = "database/daily/2026/08/09/transparencia-total-20260809T051700Z-31299900000-1.dump.age"


def _inventory(*, offset_seconds: int = 0) -> dict[str, Any]:
    tables = {name: index for index, name in enumerate(sorted(CRITICAL_TABLES), start=1)}
    migrations = [
        {
            "migration_name": "20260809043000_v4_pin_database_function_search_paths",
            "checksum": "a" * 64,
            "finished_at": "2026-08-09T04:31:00Z",
        }
    ]
    tables["_prisma_migrations"] = len(migrations)
    start = STARTED_AT + timedelta(seconds=offset_seconds)
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "started_at": start.isoformat().replace("+00:00", "Z"),
        "completed_at": (start + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "database": {
            "server_version": "17.6",
            "server_version_num": 170006,
            "size_bytes": 80_710_803 + offset_seconds,
        },
        "scope": {"schemas": ["public"], "table_count": len(tables)},
        "tables": tables,
        "migrations": migrations,
    }


def _manifest(ciphertext: Path) -> dict[str, Any]:
    return build_backup_manifest(
        ciphertext_path=ciphertext,
        object_key=OBJECT_KEY,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        retain_until=COMPLETED_AT + timedelta(days=31),
        age_recipient="age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
        age_version="1.2.1",
        git_sha="b" * 40,
        repository="DxMaxi/transparencia-total-open-source",
        workflow_run_id="31299900000",
        workflow_run_attempt=1,
        postgres_client="pg_dump (PostgreSQL) 17.6 (Debian 17.6-1.pgdg120+1)",
        inventory_before=_inventory(),
        inventory_after=_inventory(offset_seconds=10),
    )


def test_manifest_records_ciphertext_provenance_without_secret(tmp_path: Path) -> None:
    ciphertext = tmp_path / "backup.dump.age"
    ciphertext.write_bytes(b"age-encrypted-backup")

    manifest = _manifest(ciphertext)

    assert manifest["schema_version"] == BACKUP_SCHEMA_VERSION
    assert manifest["backup"]["ciphertext_size_bytes"] == len(b"age-encrypted-backup")
    assert manifest["backup"]["encryption"]["plaintext_persisted"] is False
    assert manifest["backup"]["encryption"]["tool_version"] == "1.2.1"
    assert manifest["backup"]["retention"]["object_lock_mode"] == "COMPLIANCE"
    assert manifest["source"]["consistency_window"]["observed_stable"] is True
    serialised = str(manifest).lower()
    assert "database_url" not in serialised
    assert "application_key" not in serialised
    assert "age-secret-key" not in serialised


def test_manifest_rejects_changes_observed_during_backup() -> None:
    after = _inventory(offset_seconds=10)
    after["tables"]["audit_events"] += 1

    with pytest.raises(BackupEvidenceError, match="base mudou"):
        ensure_stable_inventory(_inventory(), after)


def test_ciphertext_is_verified_before_restore_and_tampering_fails(tmp_path: Path) -> None:
    ciphertext = tmp_path / "backup.dump.age"
    ciphertext.write_bytes(b"age-encrypted-backup")
    manifest = _manifest(ciphertext)

    validated = validate_backup_ciphertext(
        manifest=manifest,
        ciphertext_path=ciphertext,
        object_key=OBJECT_KEY,
        expected_ciphertext_sha256=manifest["backup"]["ciphertext_sha256"],
    )
    assert validated["backup"]["ciphertext_sha256"]

    ciphertext.write_bytes(b"alterado")
    with pytest.raises(BackupEvidenceError, match="tamanho|SHA-256"):
        validate_backup_ciphertext(
            manifest=manifest,
            ciphertext_path=ciphertext,
            object_key=OBJECT_KEY,
            expected_ciphertext_sha256=manifest["backup"]["ciphertext_sha256"],
        )


def test_restore_rejects_out_of_band_hash_that_does_not_match_manifest(tmp_path: Path) -> None:
    ciphertext = tmp_path / "backup.dump.age"
    ciphertext.write_bytes(b"age-encrypted-backup")

    with pytest.raises(BackupEvidenceError, match="SHA-256 esperado"):
        validate_backup_ciphertext(
            manifest=_manifest(ciphertext),
            ciphertext_path=ciphertext,
            object_key=OBJECT_KEY,
            expected_ciphertext_sha256="f" * 64,
        )


def test_restore_attestation_compares_counts_migrations_and_archive(tmp_path: Path) -> None:
    ciphertext = tmp_path / "backup.dump.age"
    ciphertext.write_bytes(b"age-encrypted-backup")
    manifest = _manifest(ciphertext)

    attestation = build_restore_attestation(
        manifest=manifest,
        ciphertext_path=ciphertext,
        object_key=OBJECT_KEY,
        restored_inventory=_inventory(offset_seconds=120),
        archive_report={
            "status": "VERIFIED",
            "checked": 32,
            "verified": 32,
            "corrupt": 0,
            "failures": [],
        },
        operational_report={
            "status": "HEALTHY",
            "unhealthy_sources": [],
            "sources": [],
        },
        started_at=COMPLETED_AT + timedelta(minutes=1),
        completed_at=COMPLETED_AT + timedelta(minutes=4),
        repository="DxMaxi/transparencia-total-open-source",
        workflow_run_id="31300000000",
        expected_ciphertext_sha256=manifest["backup"]["ciphertext_sha256"],
        expected_manifest_sha256="c" * 64,
        manifest_file_sha256="c" * 64,
    )

    assert attestation["schema_version"] == RESTORE_SCHEMA_VERSION
    assert attestation["outcome"] == "PASS"
    assert attestation["restore"]["production_target_used"] is False
    assert attestation["checks"]["archive_integrity"] == "PASS"
    digest = attestation.pop("attestation_sha256")
    assert digest == canonical_json_sha256(attestation)


def test_restore_records_stale_sources_without_falsifying_them(tmp_path: Path) -> None:
    ciphertext = tmp_path / "backup.dump.age"
    ciphertext.write_bytes(b"age-encrypted-backup")

    attestation = build_restore_attestation(
        manifest=_manifest(ciphertext),
        ciphertext_path=ciphertext,
        object_key=OBJECT_KEY,
        restored_inventory=_inventory(offset_seconds=120),
        archive_report={"status": "VERIFIED", "checked": 32, "corrupt": 0},
        operational_report={"status": "ATTENTION_REQUIRED"},
        started_at=COMPLETED_AT + timedelta(days=40),
        completed_at=COMPLETED_AT + timedelta(days=40, minutes=3),
        repository="DxMaxi/transparencia-total-open-source",
        workflow_run_id="31300000001",
        expected_ciphertext_sha256=_manifest(ciphertext)["backup"]["ciphertext_sha256"],
        expected_manifest_sha256="c" * 64,
        manifest_file_sha256="c" * 64,
    )

    assert attestation["outcome"] == "PASS_WITH_OPERATIONAL_WARNING"
    assert attestation["checks"]["operational_status"] == "ATTENTION_REQUIRED"
