"""Relatório de capacidade da base e do arquivo privado.

A operação é exclusivamente de leitura. Não apaga, compacta, migra ou publica dados.
Termina com código 2 quando o limite de aviso configurado é atingido, permitindo
alertar antes de ser necessário contratar armazenamento adicional.
"""

import asyncio
import json
import os
from datetime import UTC, datetime

import asyncpg

from app.core.config import get_settings
from app.repositories.postgres import _asyncpg_connection_options

DEFAULT_WARNING_BYTES = 400_000_000
DEFAULT_DATABASE_WARNING_BYTES = 450_000_000


def _warning_limit(
    name: str = "RAW_ARCHIVE_WARNING_BYTES", default: int = DEFAULT_WARNING_BYTES
) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} deve ser um número inteiro") from exc
    if value < 10_000_000:
        raise RuntimeError(f"{name} deve ser pelo menos 10000000")
    return value


async def report() -> dict[str, object]:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")

    warning_bytes = _warning_limit()
    database_warning_bytes = _warning_limit(
        "DATABASE_WARNING_BYTES", DEFAULT_DATABASE_WARNING_BYTES
    )
    dsn, server_settings = _asyncpg_connection_options(settings.database_url.get_secret_value())
    connection = await asyncpg.connect(
        dsn, server_settings=server_settings, timeout=10, command_timeout=30
    )
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            row = await connection.fetchrow(
                """
            SELECT
                COUNT(*)::bigint AS object_count,
                COALESCE(SUM(byte_size), 0)::bigint AS logical_bytes,
                COALESCE(pg_total_relation_size('raw_source_objects'), 0)::bigint
                    AS relation_bytes,
                COALESCE(MAX(byte_size), 0)::bigint AS largest_object_bytes,
                pg_database_size(current_database())::bigint AS database_bytes
            FROM raw_source_objects
            """
            )
    finally:
        await connection.close()

    if row is None:
        raise RuntimeError("Não foi possível calcular a capacidade do arquivo")

    relation_bytes = int(row["relation_bytes"])
    database_bytes = int(row["database_bytes"])
    utilization_percent = round((relation_bytes / warning_bytes) * 100, 2)
    reasons = []
    if relation_bytes >= warning_bytes:
        reasons.append("ARCHIVE_WARNING_THRESHOLD_REACHED")
    if database_bytes >= database_warning_bytes:
        reasons.append("DATABASE_WARNING_THRESHOLD_REACHED")
    status = "WARNING" if reasons else "OK"

    return {
        "status": status,
        "checked_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "warning_reasons": reasons,
        "storage_backend": "POSTGRES",
        "object_count": int(row["object_count"]),
        "logical_bytes": int(row["logical_bytes"]),
        "relation_bytes": relation_bytes,
        "largest_object_bytes": int(row["largest_object_bytes"]),
        "warning_bytes": warning_bytes,
        "utilization_percent": utilization_percent,
        "database_bytes": database_bytes,
        "database_warning_bytes": database_warning_bytes,
        "database_utilization_percent": round(database_bytes / database_warning_bytes * 100, 2),
        "action": (
            "Resolver a capacidade antes de novas recolhas pesadas; preservar os dados existentes."
            if status == "WARNING"
            else "Abaixo dos limites de aviso configurados; continuar a acompanhar o crescimento."
        ),
    }


async def main_async() -> None:
    try:
        result = await report()
    except Exception:
        print(json.dumps({"status": "CHECK_FAILED", "read_only": True}))
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "WARNING":
        raise SystemExit(2)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
