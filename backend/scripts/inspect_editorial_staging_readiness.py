"""Inspeciona a prontidão PostgreSQL editorial sem escrever nem configurar serviços."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository
from app.services.editorial_staging_readiness import inspect_editorial_staging_readiness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-read-only",
        action="store_true",
        help="Confirmar que a operação autorizada é apenas uma inspeção de staging.",
    )
    return parser


async def _run(*, confirm_read_only: bool) -> dict[str, object]:
    if not confirm_read_only:
        raise RuntimeError("A inspeção exige --confirm-read-only")

    settings = get_settings()
    if settings.environment != "staging":
        raise RuntimeError("A inspeção editorial só pode executar com ENVIRONMENT=staging")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")
    if settings.supabase_url is None:
        raise RuntimeError("SUPABASE_URL de staging não configurada")

    repository = PostgresRepository(settings)
    await repository.connect()
    try:
        if repository.pool is None:
            raise RuntimeError("Ligação PostgreSQL indisponível")
        async with (
            repository.pool.acquire() as connection,
            connection.transaction(readonly=True, isolation="repeatable_read"),
        ):
            return await inspect_editorial_staging_readiness(connection)
    finally:
        await repository.close()


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        report = asyncio.run(_run(confirm_read_only=args.confirm_read_only))
    except RuntimeError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if report["database_ready"] else 1)


if __name__ == "__main__":
    main()
