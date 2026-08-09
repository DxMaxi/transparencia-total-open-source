"""Captura, em transação só de leitura, contagens e migrações do esquema public."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg

from app.core.config import get_settings
from app.services.database_backup import INVENTORY_SCHEMA_VERSION, write_json_object


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def capture_inventory() -> dict[str, Any]:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")

    connection = await asyncpg.connect(settings.database_url.get_secret_value())
    started_at = datetime.now(UTC)
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            database = await connection.fetchrow(
                """
                SELECT current_setting('server_version') AS server_version,
                       current_setting('server_version_num')::integer AS server_version_num,
                       pg_database_size(current_database())::bigint AS size_bytes
                """
            )
            table_rows = await connection.fetch(
                """
                SELECT namespace.nspname AS schema_name, relation.relname AS table_name
                FROM pg_class relation
                JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'public'
                  AND relation.relkind IN ('r', 'p')
                ORDER BY relation.relname
                """
            )
            tables: dict[str, int] = {}
            for row in table_rows:
                schema_name = str(row["schema_name"])
                table_name = str(row["table_name"])
                query = (
                    f"SELECT COUNT(*)::bigint FROM {_quote_identifier(schema_name)}."
                    f"{_quote_identifier(table_name)}"
                )
                tables[table_name] = int(await connection.fetchval(query))

            migrations = await connection.fetch(
                """
                SELECT migration_name, checksum, finished_at
                FROM public."_prisma_migrations"
                WHERE finished_at IS NOT NULL
                  AND rolled_back_at IS NULL
                ORDER BY started_at, migration_name
                """
            )
    finally:
        await connection.close()

    completed_at = datetime.now(UTC)
    if database is None:
        raise RuntimeError("não foi possível identificar a base de dados")
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "completed_at": completed_at.isoformat().replace("+00:00", "Z"),
        "database": {
            "server_version": str(database["server_version"]),
            "server_version_num": int(database["server_version_num"]),
            "size_bytes": int(database["size_bytes"]),
        },
        "scope": {"schemas": ["public"], "table_count": len(tables)},
        "tables": tables,
        "migrations": [
            {
                "migration_name": str(row["migration_name"]),
                "checksum": str(row["checksum"]),
                "finished_at": _utc_text(row["finished_at"]),
            }
            for row in migrations
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    report = await capture_inventory()
    write_json_object(args.output, report)
    print(
        f"Inventário só de leitura: {report['scope']['table_count']} tabelas; "
        f"{len(report['migrations'])} migrações."
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
