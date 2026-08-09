"""Prova verificável para cópias lógicas cifradas da base de dados.

Este módulo não cria nem restaura a cópia. Mantém apenas a parte determinística:
validação dos inventários, SHA-256 do ficheiro cifrado, manifesto e atestação do
ensaio de restauro. Credenciais e chaves privadas nunca são aceites por estas
funções.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

INVENTORY_SCHEMA_VERSION = "transparencia-total.database-inventory/v1"
BACKUP_SCHEMA_VERSION = "transparencia-total.database-backup/v1"
RESTORE_SCHEMA_VERSION = "transparencia-total.database-restore/v1"
MINIMUM_OBJECT_LOCK_DAYS = 30

CRITICAL_TABLES = frozenset(
    {
        "_prisma_migrations",
        "ai_summaries",
        "audit_events",
        "contract_match_reviews",
        "data_publication_reviews",
        "parliamentary_initiatives",
        "parliamentary_sessions",
        "people",
        "promises",
        "protected_identifier_digests",
        "raw_source_objects",
        "rights_of_reply",
        "source_archive_attestations",
        "source_documents",
        "vote_events",
        "vote_records",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MIGRATION_NAME_RE = re.compile(r"^[0-9A-Za-z_]+$")
_OBJECT_KEY_RE = re.compile(
    r"^database/daily/\d{4}/\d{2}/\d{2}/"
    r"transparencia-total-\d{8}T\d{6}Z-\d+-\d+\.dump\.age$"
)


class BackupEvidenceError(ValueError):
    """Indica prova de backup incompleta, inconsistente ou adulterada."""


def sha256_file(path: Path) -> str:
    """Calcula SHA-256 em streaming para não carregar a cópia em memória."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    """Calcula o hash de uma representação JSON canónica e independente de indentação."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupEvidenceError(f"JSON inválido em {path.name}") from exc
    if not isinstance(value, dict):
        raise BackupEvidenceError(f"{path.name} deve conter um objeto JSON")
    return cast(dict[str, Any], value)


def write_json_object(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BackupEvidenceError(f"{field} deve ser um objeto")
    return cast(Mapping[str, Any], value)


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BackupEvidenceError(f"{field} deve ser texto não vazio")
    return value


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BackupEvidenceError(f"{field} deve ser inteiro >= {minimum}")
    return value


def _instant(value: object, *, field: str) -> datetime:
    raw = _string(value, field=field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BackupEvidenceError(f"{field} deve ser um instante ISO-8601") from exc
    if parsed.tzinfo is None:
        raise BackupEvidenceError(f"{field} deve incluir fuso horário")
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise BackupEvidenceError("instante sem fuso horário")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_sha256(value: object, *, field: str) -> str:
    digest = _string(value, field=field)
    if _SHA256_RE.fullmatch(digest) is None:
        raise BackupEvidenceError(f"{field} deve ser SHA-256 hexadecimal")
    return digest


def validate_inventory(value: Mapping[str, Any]) -> dict[str, Any]:
    """Valida um inventário de leitura e devolve uma cópia normalizada."""

    if value.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise BackupEvidenceError("versão de inventário desconhecida")

    started_at = _instant(value.get("started_at"), field="inventory.started_at")
    completed_at = _instant(value.get("completed_at"), field="inventory.completed_at")
    if completed_at < started_at:
        raise BackupEvidenceError("inventário termina antes de começar")

    database = _mapping(value.get("database"), field="inventory.database")
    server_version = _string(
        database.get("server_version"), field="inventory.database.server_version"
    )
    server_version_num = _integer(
        database.get("server_version_num"),
        field="inventory.database.server_version_num",
        minimum=100_000,
    )
    size_bytes = _integer(database.get("size_bytes"), field="inventory.database.size_bytes")

    scope = _mapping(value.get("scope"), field="inventory.scope")
    if scope.get("schemas") != ["public"]:
        raise BackupEvidenceError("o inventário deve estar limitado ao esquema public")

    raw_tables = _mapping(value.get("tables"), field="inventory.tables")
    tables: dict[str, int] = {}
    for raw_name, raw_count in raw_tables.items():
        if not isinstance(raw_name, str) or not raw_name:
            raise BackupEvidenceError("nome de tabela inválido no inventário")
        tables[raw_name] = _integer(
            raw_count,
            field=f"inventory.tables.{raw_name}",
        )
    missing = sorted(CRITICAL_TABLES.difference(tables))
    if missing:
        raise BackupEvidenceError("inventário sem tabelas críticas: " + ", ".join(missing))
    if scope.get("table_count") != len(tables):
        raise BackupEvidenceError("table_count não corresponde ao inventário")

    raw_migrations = value.get("migrations")
    if not isinstance(raw_migrations, list):
        raise BackupEvidenceError("inventory.migrations deve ser uma lista")
    migrations: list[dict[str, str]] = []
    seen_migrations: set[str] = set()
    for index, raw_migration in enumerate(raw_migrations):
        migration = _mapping(raw_migration, field=f"inventory.migrations[{index}]")
        name = _string(
            migration.get("migration_name"),
            field=f"inventory.migrations[{index}].migration_name",
        )
        if _MIGRATION_NAME_RE.fullmatch(name) is None or name in seen_migrations:
            raise BackupEvidenceError("nome de migração inválido ou repetido")
        seen_migrations.add(name)
        checksum = _validate_sha256(
            migration.get("checksum"),
            field=f"inventory.migrations[{index}].checksum",
        )
        finished_at = _utc_text(
            _instant(
                migration.get("finished_at"),
                field=f"inventory.migrations[{index}].finished_at",
            )
        )
        migrations.append(
            {
                "migration_name": name,
                "checksum": checksum,
                "finished_at": finished_at,
            }
        )

    if tables["_prisma_migrations"] != len(migrations):
        raise BackupEvidenceError("as migrações concluídas não correspondem a _prisma_migrations")

    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "started_at": _utc_text(started_at),
        "completed_at": _utc_text(completed_at),
        "database": {
            "server_version": server_version,
            "server_version_num": server_version_num,
            "size_bytes": size_bytes,
        },
        "scope": {"schemas": ["public"], "table_count": len(tables)},
        "tables": dict(sorted(tables.items())),
        "migrations": migrations,
    }


def ensure_stable_inventory(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Falha se houve alteração observável durante a criação da cópia."""

    normalised_before = validate_inventory(before)
    normalised_after = validate_inventory(after)
    changed: list[str] = []
    if normalised_before["tables"] != normalised_after["tables"]:
        changed.append("contagens das tabelas")
    if normalised_before["migrations"] != normalised_after["migrations"]:
        changed.append("migrações aplicadas")
    before_database = cast(dict[str, Any], normalised_before["database"])
    after_database = cast(dict[str, Any], normalised_after["database"])
    if before_database["server_version_num"] != after_database["server_version_num"]:
        changed.append("versão do servidor PostgreSQL")
    if changed:
        raise BackupEvidenceError(
            "a base mudou durante o backup; a cópia não será enviada: " + ", ".join(changed)
        )
    return normalised_before, normalised_after


def build_backup_manifest(
    *,
    ciphertext_path: Path,
    object_key: str,
    started_at: datetime,
    completed_at: datetime,
    retain_until: datetime,
    age_recipient: str,
    age_version: str,
    git_sha: str,
    repository: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
    postgres_client: str,
    inventory_before: Mapping[str, Any],
    inventory_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Cria o manifesto sem incluir qualquer credencial ou chave de decifragem."""

    if _OBJECT_KEY_RE.fullmatch(object_key) is None:
        raise BackupEvidenceError("chave de objeto B2 fora do formato permitido")
    if not ciphertext_path.is_file() or ciphertext_path.stat().st_size < 1:
        raise BackupEvidenceError("ficheiro cifrado ausente ou vazio")
    if started_at.tzinfo is None or completed_at.tzinfo is None or retain_until.tzinfo is None:
        raise BackupEvidenceError("instantes do backup devem incluir fuso horário")
    started_at = started_at.astimezone(UTC)
    completed_at = completed_at.astimezone(UTC)
    retain_until = retain_until.astimezone(UTC)
    if completed_at < started_at:
        raise BackupEvidenceError("o backup termina antes de começar")
    minimum_retention = completed_at + timedelta(days=MINIMUM_OBJECT_LOCK_DAYS)
    if retain_until < minimum_retention:
        raise BackupEvidenceError("Object Lock inferior a 30 dias")
    if not age_recipient.startswith("age1") or any(
        character.isspace() for character in age_recipient
    ):
        raise BackupEvidenceError("destinatário age X25519 inválido")
    age_version = age_version.strip()
    if re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", age_version) is None:
        raise BackupEvidenceError("versão da ferramenta age inválida")
    if _GIT_SHA_RE.fullmatch(git_sha) is None:
        raise BackupEvidenceError("git_sha inválido")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise BackupEvidenceError("identificador do repositório inválido")
    if not workflow_run_id.isdigit():
        raise BackupEvidenceError("workflow_run_id inválido")
    if workflow_run_attempt < 1:
        raise BackupEvidenceError("workflow_run_attempt inválido")
    postgres_client = postgres_client.strip()
    client_major_match = re.search(r"PostgreSQL\)\s+(\d+)", postgres_client)
    if client_major_match is None:
        raise BackupEvidenceError("versão do pg_dump não reconhecida")

    before, after = ensure_stable_inventory(inventory_before, inventory_after)
    before_database = cast(dict[str, Any], before["database"])
    server_major = int(before_database["server_version_num"]) // 10_000
    if int(client_major_match.group(1)) != server_major:
        raise BackupEvidenceError("pg_dump e servidor PostgreSQL não têm a mesma versão principal")

    manifest_object_key = object_key.removesuffix(".dump.age") + ".manifest.json"
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": _utc_text(completed_at),
        "source": {
            "provider": "SUPABASE_POSTGRESQL",
            "scope": {"schemas": ["public"]},
            "inventory": before,
            "consistency_window": {
                "inventory_before_completed_at": before["completed_at"],
                "inventory_after_started_at": after["started_at"],
                "observed_stable": True,
            },
        },
        "backup": {
            "started_at": _utc_text(started_at),
            "completed_at": _utc_text(completed_at),
            "object_key": object_key,
            "manifest_object_key": manifest_object_key,
            "ciphertext_sha256": sha256_file(ciphertext_path),
            "ciphertext_size_bytes": ciphertext_path.stat().st_size,
            "dump": {
                "format": "postgresql-custom",
                "schemas": ["public"],
                "owner_restored": False,
                "privileges_restored": False,
                "postgres_client": postgres_client,
            },
            "encryption": {
                "format": "age",
                "recipient_type": "X25519",
                "tool_version": age_version,
                "recipient_sha256": hashlib.sha256(age_recipient.encode("utf-8")).hexdigest(),
                "plaintext_persisted": False,
            },
            "retention": {
                "object_lock_mode": "COMPLIANCE",
                "retain_until": _utc_text(retain_until),
            },
        },
        "provenance": {
            "repository": repository,
            "git_sha": git_sha,
            "workflow": ".github/workflows/database-backup.yml",
            "workflow_run_id": workflow_run_id,
            "workflow_run_attempt": workflow_run_attempt,
        },
    }


def validate_backup_ciphertext(
    *,
    manifest: Mapping[str, Any],
    ciphertext_path: Path,
    object_key: str,
    expected_ciphertext_sha256: str | None = None,
) -> dict[str, Any]:
    """Confirma o manifesto e o SHA-256 antes de qualquer decifragem."""

    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise BackupEvidenceError("versão de manifesto de backup desconhecida")
    _instant(manifest.get("created_at"), field="manifest.created_at")
    source = _mapping(manifest.get("source"), field="manifest.source")
    if source.get("provider") != "SUPABASE_POSTGRESQL":
        raise BackupEvidenceError("provedor de origem inesperado no manifesto")
    if source.get("scope") != {"schemas": ["public"]}:
        raise BackupEvidenceError("âmbito de origem inesperado no manifesto")
    inventory = validate_inventory(
        _mapping(source.get("inventory"), field="manifest.source.inventory")
    )
    consistency_window = _mapping(
        source.get("consistency_window"), field="manifest.source.consistency_window"
    )
    if consistency_window.get("observed_stable") is not True:
        raise BackupEvidenceError("manifesto sem janela de consistência estável")
    _instant(
        consistency_window.get("inventory_before_completed_at"),
        field="manifest.source.consistency_window.inventory_before_completed_at",
    )
    _instant(
        consistency_window.get("inventory_after_started_at"),
        field="manifest.source.consistency_window.inventory_after_started_at",
    )
    backup = _mapping(manifest.get("backup"), field="manifest.backup")
    started_at = _instant(backup.get("started_at"), field="manifest.backup.started_at")
    completed_at = _instant(backup.get("completed_at"), field="manifest.backup.completed_at")
    if completed_at < started_at:
        raise BackupEvidenceError("o backup do manifesto termina antes de começar")
    expected_key = _string(backup.get("object_key"), field="manifest.backup.object_key")
    if _OBJECT_KEY_RE.fullmatch(expected_key) is None or expected_key != object_key:
        raise BackupEvidenceError("objeto pedido não corresponde ao manifesto")
    expected_manifest_key = expected_key.removesuffix(".dump.age") + ".manifest.json"
    if backup.get("manifest_object_key") != expected_manifest_key:
        raise BackupEvidenceError("chave do manifesto inconsistente")
    expected_sha256 = _validate_sha256(
        backup.get("ciphertext_sha256"), field="manifest.backup.ciphertext_sha256"
    )
    if expected_ciphertext_sha256 is not None:
        supplied_sha256 = _validate_sha256(
            expected_ciphertext_sha256, field="expected_ciphertext_sha256"
        )
        if supplied_sha256 != expected_sha256:
            raise BackupEvidenceError("SHA-256 esperado não corresponde ao manifesto")
    expected_size = _integer(
        backup.get("ciphertext_size_bytes"),
        field="manifest.backup.ciphertext_size_bytes",
        minimum=1,
    )
    if not ciphertext_path.is_file():
        raise BackupEvidenceError("ficheiro cifrado não encontrado")
    if ciphertext_path.stat().st_size != expected_size:
        raise BackupEvidenceError("tamanho do ficheiro cifrado não corresponde ao manifesto")
    observed_sha256 = sha256_file(ciphertext_path)
    if observed_sha256 != expected_sha256:
        raise BackupEvidenceError("SHA-256 do ficheiro cifrado não corresponde ao manifesto")

    dump = _mapping(backup.get("dump"), field="manifest.backup.dump")
    if dump.get("format") != "postgresql-custom" or dump.get("schemas") != ["public"]:
        raise BackupEvidenceError("formato ou esquema inesperado no manifesto")
    if dump.get("owner_restored") is not False or dump.get("privileges_restored") is not False:
        raise BackupEvidenceError("manifesto tenta restaurar owner ou privilégios")
    postgres_client = _string(
        dump.get("postgres_client"), field="manifest.backup.dump.postgres_client"
    )
    client_major_match = re.search(r"PostgreSQL\)\s+(\d+)", postgres_client)
    inventory_database = cast(dict[str, Any], inventory["database"])
    if (
        client_major_match is None
        or int(client_major_match.group(1))
        != int(inventory_database["server_version_num"]) // 10_000
    ):
        raise BackupEvidenceError("versão do pg_dump inconsistente no manifesto")

    encryption = _mapping(backup.get("encryption"), field="manifest.backup.encryption")
    if encryption.get("format") != "age" or encryption.get("recipient_type") != "X25519":
        raise BackupEvidenceError("cifragem inesperada no manifesto")
    if (
        re.fullmatch(
            r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?",
            _string(
                encryption.get("tool_version"),
                field="manifest.backup.encryption.tool_version",
            ),
        )
        is None
    ):
        raise BackupEvidenceError("versão age inválida no manifesto")
    _validate_sha256(
        encryption.get("recipient_sha256"),
        field="manifest.backup.encryption.recipient_sha256",
    )
    if encryption.get("plaintext_persisted") is not False:
        raise BackupEvidenceError("manifesto não garante ausência de plaintext persistido")

    retention = _mapping(backup.get("retention"), field="manifest.backup.retention")
    if retention.get("object_lock_mode") != "COMPLIANCE":
        raise BackupEvidenceError("manifesto sem Object Lock em modo COMPLIANCE")
    retain_until = _instant(
        retention.get("retain_until"), field="manifest.backup.retention.retain_until"
    )
    if retain_until < completed_at + timedelta(days=MINIMUM_OBJECT_LOCK_DAYS):
        raise BackupEvidenceError("retenção do manifesto inferior a 30 dias")

    provenance = _mapping(manifest.get("provenance"), field="manifest.provenance")
    if provenance.get("workflow") != ".github/workflows/database-backup.yml":
        raise BackupEvidenceError("workflow de origem inesperada no manifesto")
    manifest_repository = _string(
        provenance.get("repository"), field="manifest.provenance.repository"
    )
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", manifest_repository) is None:
        raise BackupEvidenceError("repositório inválido no manifesto")
    if (
        _GIT_SHA_RE.fullmatch(
            _string(provenance.get("git_sha"), field="manifest.provenance.git_sha")
        )
        is None
    ):
        raise BackupEvidenceError("git_sha inválido no manifesto")
    if not _string(
        provenance.get("workflow_run_id"), field="manifest.provenance.workflow_run_id"
    ).isdigit():
        raise BackupEvidenceError("workflow_run_id inválido no manifesto")
    _integer(
        provenance.get("workflow_run_attempt"),
        field="manifest.provenance.workflow_run_attempt",
        minimum=1,
    )
    return dict(manifest)


def compare_restored_inventory(
    *, manifest: Mapping[str, Any], restored_inventory: Mapping[str, Any]
) -> dict[str, int]:
    """Compara tabelas e migrações restauradas com a fotografia anexada ao backup."""

    source = _mapping(manifest.get("source"), field="manifest.source")
    expected = validate_inventory(
        _mapping(source.get("inventory"), field="manifest.source.inventory")
    )
    restored = validate_inventory(restored_inventory)
    if expected["tables"] != restored["tables"]:
        raise BackupEvidenceError("as contagens restauradas não correspondem ao backup")
    if expected["migrations"] != restored["migrations"]:
        raise BackupEvidenceError("as migrações restauradas não correspondem ao backup")
    expected_database = cast(dict[str, Any], expected["database"])
    restored_database = cast(dict[str, Any], restored["database"])
    if (
        int(expected_database["server_version_num"]) // 10_000
        != int(restored_database["server_version_num"]) // 10_000
    ):
        raise BackupEvidenceError("versão principal do PostgreSQL restaurado é diferente")
    tables = cast(dict[str, int], restored["tables"])
    migrations = cast(list[dict[str, str]], restored["migrations"])
    return {
        "table_count": len(tables),
        "row_count": sum(tables.values()),
        "migration_count": len(migrations),
    }


def build_restore_attestation(
    *,
    manifest: Mapping[str, Any],
    ciphertext_path: Path,
    object_key: str,
    restored_inventory: Mapping[str, Any],
    archive_report: Mapping[str, Any],
    operational_report: Mapping[str, Any],
    started_at: datetime,
    completed_at: datetime,
    repository: str,
    workflow_run_id: str,
    expected_ciphertext_sha256: str,
    expected_manifest_sha256: str,
    manifest_file_sha256: str,
) -> dict[str, Any]:
    """Cria uma atestação não sensível para um restauro isolado já concluído."""

    validated_manifest = validate_backup_ciphertext(
        manifest=manifest,
        ciphertext_path=ciphertext_path,
        object_key=object_key,
        expected_ciphertext_sha256=expected_ciphertext_sha256,
    )
    expected_manifest_sha256 = _validate_sha256(
        expected_manifest_sha256, field="expected_manifest_sha256"
    )
    manifest_file_sha256 = _validate_sha256(manifest_file_sha256, field="manifest_file_sha256")
    if expected_manifest_sha256 != manifest_file_sha256:
        raise BackupEvidenceError("SHA-256 do manifesto não corresponde à prova esperada")
    provenance = _mapping(validated_manifest.get("provenance"), field="manifest.provenance")
    if provenance.get("repository") != repository:
        raise BackupEvidenceError("o backup pertence a outro repositório")
    if not workflow_run_id.isdigit():
        raise BackupEvidenceError("workflow_run_id do restauro inválido")
    inventory_summary = compare_restored_inventory(
        manifest=validated_manifest,
        restored_inventory=restored_inventory,
    )
    if archive_report.get("status") != "VERIFIED" or archive_report.get("corrupt") != 0:
        raise BackupEvidenceError("arquivo oficial restaurado não passou a verificação")
    operational_status = operational_report.get("status")
    if operational_status not in {"HEALTHY", "ATTENTION_REQUIRED"}:
        raise BackupEvidenceError("relatório operacional restaurado inválido")
    if started_at.tzinfo is None or completed_at.tzinfo is None:
        raise BackupEvidenceError("instantes do restauro devem incluir fuso horário")
    started_at = started_at.astimezone(UTC)
    completed_at = completed_at.astimezone(UTC)
    if completed_at < started_at:
        raise BackupEvidenceError("o restauro termina antes de começar")

    backup = _mapping(validated_manifest.get("backup"), field="manifest.backup")
    backup_completed_at = _instant(backup.get("completed_at"), field="manifest.backup.completed_at")
    outcome = "PASS" if operational_status == "HEALTHY" else "PASS_WITH_OPERATIONAL_WARNING"
    attestation: dict[str, Any] = {
        "schema_version": RESTORE_SCHEMA_VERSION,
        "created_at": _utc_text(completed_at),
        "outcome": outcome,
        "backup": {
            "object_key": object_key,
            "ciphertext_sha256": backup["ciphertext_sha256"],
            "manifest_file_sha256": manifest_file_sha256,
            "manifest_canonical_sha256": canonical_json_sha256(validated_manifest),
        },
        "restore": {
            "target": "ISOLATED_EPHEMERAL_POSTGRESQL",
            "production_target_used": False,
            "started_at": _utc_text(started_at),
            "completed_at": _utc_text(completed_at),
            "rto_seconds": round((completed_at - started_at).total_seconds(), 3),
            "rpo_seconds_at_drill_start": round(
                max(0.0, (started_at - backup_completed_at).total_seconds()), 3
            ),
        },
        "checks": {
            "ciphertext_sha256": "PASS",
            "table_counts": "PASS",
            "migrations": "PASS",
            "archive_integrity": "PASS",
            "operational_status": operational_status,
            **inventory_summary,
            "archive_objects_checked": _integer(
                archive_report.get("checked"), field="archive_report.checked"
            ),
        },
        "provenance": {
            "repository": repository,
            "workflow": ".github/workflows/database-restore-drill.yml",
            "workflow_run_id": workflow_run_id,
        },
    }
    attestation["attestation_sha256"] = canonical_json_sha256(attestation)
    return attestation
