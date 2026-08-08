"""Verifica se as fontes públicas da V4 estão recentes e operacionais."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import asyncpg

from app.core.config import get_settings
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

    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    connection = await asyncpg.connect(settings.database_url.get_secret_value())
    try:
        rows = await connection.fetch(
            """
            SELECT DISTINCT ON (source_name)
                source_name, status::text AS status, started_at, finished_at,
                records_read, records_written, error_message
            FROM sync_runs
            WHERE source_name = ANY($1::text[])
            ORDER BY source_name, started_at DESC
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
        if row is None:
            sources.append({"source_name": source_name, "status": "MISSING"})
            unhealthy.append(source_name)
            continue

        observed_at = row["finished_at"] or row["started_at"]
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        is_stale = observed_at < cutoff
        status = str(row["status"])
        healthy = status in {"SUCCEEDED", "PARTIAL"} and not is_stale
        if not healthy:
            unhealthy.append(source_name)

        sources.append(
            {
                "source_name": source_name,
                "status": status,
                "observed_at": observed_at.isoformat(),
                "stale": is_stale,
                "records_read": int(row["records_read"]),
                "records_written": int(row["records_written"]),
                "error": row["error_message"],
            }
        )

    return {
        "status": "HEALTHY" if not unhealthy else "ATTENTION_REQUIRED",
        "checked_at": datetime.now(UTC).isoformat(),
        "max_age_hours": max_age_hours,
        "unhealthy_sources": unhealthy,
        "sources": sources,
    }


async def main_async() -> None:
    report = await check_status()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if report["status"] != "HEALTHY":
        raise SystemExit(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
