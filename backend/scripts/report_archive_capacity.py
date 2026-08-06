"""Relatório de capacidade do arquivo privado da V4.

A operação é exclusivamente de leitura. Não apaga, compacta, migra ou publica dados.
Termina com código 2 quando o limite de aviso configurado é atingido, permitindo
alertar antes de ser necessário contratar armazenamento adicional.
"""

import asyncio
import json
import os

import asyncpg

from app.core.config import get_settings

DEFAULT_WARNING_BYTES = 400_000_000


def _warning_limit() -> int:
    raw_value = os.getenv("RAW_ARCHIVE_WARNING_BYTES", str(DEFAULT_WARNING_BYTES))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("RAW_ARCHIVE_WARNING_BYTES deve ser um número inteiro") from exc
    if value < 10_000_000:
        raise RuntimeError("RAW_ARCHIVE_WARNING_BYTES deve ser pelo menos 10000000")
    return value


async def report() -> dict[str, object]:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")

    connection = await asyncpg.connect(settings.database_url.get_secret_value())
    try:
        row = await connection.fetchrow(
            """
            SELECT
                COUNT(*)::bigint AS object_count,
                COALESCE(SUM(byte_size), 0)::bigint AS logical_bytes,
                COALESCE(pg_total_relation_size('raw_source_objects'), 0)::bigint
                    AS relation_bytes,
                COALESCE(MAX(byte_size), 0)::bigint AS largest_object_bytes
            FROM raw_source_objects
            """
        )
    finally:
        await connection.close()

    if row is None:
        raise RuntimeError("Não foi possível calcular a capacidade do arquivo")

    warning_bytes = _warning_limit()
    relation_bytes = int(row["relation_bytes"])
    utilization_percent = round((relation_bytes / warning_bytes) * 100, 2)
    status = "WARNING" if relation_bytes >= warning_bytes else "OK"

    return {
        "status": status,
        "storage_backend": "POSTGRES",
        "object_count": int(row["object_count"]),
        "logical_bytes": int(row["logical_bytes"]),
        "relation_bytes": relation_bytes,
        "largest_object_bytes": int(row["largest_object_bytes"]),
        "warning_bytes": warning_bytes,
        "utilization_percent": utilization_percent,
        "action": (
            "Preparar migração para armazenamento S3/R2 antes de novas recolhas pesadas."
            if status == "WARNING"
            else "Nenhuma compra necessária; continuar a acompanhar a capacidade."
        ),
    }


async def main_async() -> None:
    result = await report()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "WARNING":
        raise SystemExit(2)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
