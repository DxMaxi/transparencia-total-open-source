"""Valida e inventaria o destino Supabase de staging sem escrever dados."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository
from app.services.staging_target import inspect_staging_target, validate_staging_target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-read-only",
        action="store_true",
        help="Confirmar que a operação autorizada lê apenas catálogo de staging.",
    )
    parser.add_argument(
        "--require-v5-migrations",
        action="store_true",
        help="Exigir as migrações V5 depois de uma migração autorizada.",
    )
    return parser


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} não configurada")
    return value


async def _run(
    *,
    confirm_read_only: bool,
    require_v5_migrations: bool,
) -> dict[str, object]:
    if not confirm_read_only:
        raise RuntimeError("O inventário exige --confirm-read-only")

    settings = get_settings()
    if settings.environment != "staging":
        raise RuntimeError("O inventário só pode executar com ENVIRONMENT=staging")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")
    if settings.supabase_url is None:
        raise RuntimeError("SUPABASE_URL de staging não configurada")

    target = validate_staging_target(
        database_url=settings.database_url.get_secret_value(),
        supabase_url=str(settings.supabase_url),
        expected_project_ref=_required_environment("STAGING_SUPABASE_PROJECT_REF"),
        forbidden_project_refs=_required_environment("STAGING_FORBIDDEN_PROJECT_REFS"),
    )

    repository = PostgresRepository(settings)
    await repository.connect()
    try:
        if repository.pool is None:
            raise RuntimeError("Ligação PostgreSQL indisponível")
        async with (
            repository.pool.acquire() as connection,
            connection.transaction(readonly=True, isolation="repeatable_read"),
        ):
            return await inspect_staging_target(
                connection,
                target,
                require_v5_migrations=require_v5_migrations,
            )
    finally:
        await repository.close()


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        report = asyncio.run(
            _run(
                confirm_read_only=args.confirm_read_only,
                require_v5_migrations=args.require_v5_migrations,
            )
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if report["catalog_ready"] else 1)


if __name__ == "__main__":
    main()
