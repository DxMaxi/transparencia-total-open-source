"""Diagnóstico read-only de recolhas e bloqueios, sem divulgar erros internos."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import asyncpg

from app.core.config import get_settings
from app.services.parliament_readiness import (
    EXACT_VOTE_IDENTITY_MIGRATION,
    exact_vote_identity_schema_is_ready,
)
from app.services.v4_rollout import DEFAULT_ROLLOUT_SOURCES

DEFAULT_MAX_AGE_HOURS = 36
OPERATIONAL_SOURCES = (
    "PARLIAMENT_DEPUTIES",
    "PARLIAMENT_ACTIVITY",
    *DEFAULT_ROLLOUT_SOURCES,
)


async def check_status() -> dict[str, object]:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")

    max_age_hours = int(os.getenv("V4_SOURCE_MAX_AGE_HOURS", str(DEFAULT_MAX_AGE_HOURS)))
    if max_age_hours < 1 or max_age_hours > 720:
        raise ValueError("V4_SOURCE_MAX_AGE_HOURS deve estar entre 1 e 720")

    checked_at = datetime.now(UTC)
    cutoff = checked_at - timedelta(hours=max_age_hours)
    connection = await asyncpg.connect(
        settings.database_url.get_secret_value(), timeout=10, command_timeout=10
    )
    try:
        # As duas consultas observam a mesma fotografia. Não há escrita, nem sequer em SyncRun.
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            parliament_ready = await exact_vote_identity_schema_is_ready(connection)
            rows = await connection.fetch(
                """
                SELECT DISTINCT ON (source_name)
                    source_name, status::text AS status, started_at, finished_at,
                    records_read, records_written, (error_message IS NOT NULL) AS has_error
                FROM sync_runs
                WHERE source_name = ANY($1::text[])
                ORDER BY source_name, started_at DESC, id DESC
                """,
                list(OPERATIONAL_SOURCES),
            )
    finally:
        await connection.close()

    latest = {str(row["source_name"]): dict(row) for row in rows}
    sources: list[dict[str, object]] = []
    unhealthy: list[str] = []

    for source_name in OPERATIONAL_SOURCES:
        row = latest.get(source_name)
        blocked = source_name == "PARLIAMENT_ACTIVITY" and not parliament_ready
        observed_at = (row["finished_at"] or row["started_at"]) if row else None
        if observed_at is not None and observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        is_stale = observed_at is None or observed_at < cutoff
        last_run_status = str(row["status"]) if row else "MISSING"
        status = "SCHEMA_MIGRATION_REQUIRED" if blocked else last_run_status
        healthy = not blocked and last_run_status in {"SUCCEEDED", "PARTIAL"} and not is_stale
        if not healthy:
            unhealthy.append(source_name)

        sources.append(
            {
                "source_name": source_name,
                "status": status,
                "last_run_status": last_run_status,
                "observed_at": observed_at.isoformat() if observed_at else None,
                "stale": is_stale,
                "records_read": int(row["records_read"]) if row else 0,
                "records_written": int(row["records_written"]) if row else 0,
                # O texto original pode conter URLs, dados pessoais ou detalhes PostgreSQL.
                # Não é sequer selecionado: fica apenas no registo interno existente.
                "error": (
                    "A última execução registou um erro; diagnóstico interno reservado."
                    if row and row["has_error"]
                    else None
                ),
                "blocking_reason": "EXACT_VOTE_IDENTITY_SCHEMA_MISSING" if blocked else None,
                "required_migration": EXACT_VOTE_IDENTITY_MIGRATION if blocked else None,
                "ingestion_readiness": (
                    ("READY" if parliament_ready else "BLOCKED_SCHEMA")
                    if source_name == "PARLIAMENT_ACTIVITY"
                    else "NOT_CHECKED"
                ),
            }
        )

    return {
        "status": "HEALTHY" if not unhealthy else "ATTENTION_REQUIRED",
        "checked_at": checked_at.isoformat(),
        "max_age_hours": max_age_hours,
        "read_only": True,
        "publication": "NOT_ATTEMPTED",
        "unhealthy_sources": unhealthy,
        "sources": sources,
    }


async def main_async() -> None:
    try:
        report = await check_status()
    except Exception:
        # Fronteira CLI: nunca imprimir exceções que possam incluir a ligação ou parâmetros.
        # CHECK_FAILED não é ATTENTION_REQUIRED: um restauro não o pode aceitar como prova.
        print(
            json.dumps(
                {
                    "status": "CHECK_FAILED",
                    "error_code": "OPERATIONAL_CHECK_FAILED",
                    "message": "Não foi possível concluir a verificação operacional.",
                    "read_only": True,
                    "publication": "NOT_ATTEMPTED",
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if report["status"] != "HEALTHY":
        raise SystemExit(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
