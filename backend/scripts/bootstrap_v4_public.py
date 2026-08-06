"""Aplica o schema de rollout e publica apenas o snapshot AR previamente auditado."""

import asyncio
from pathlib import Path

import asyncpg

from app.core.config import get_settings
from app.repositories.official_index_staging import OfficialIndexStagingRepository

EXPECTED_PARLIAMENT_SHA256 = (
    "e54b30869212ea3d50a401637a31847339e29dcfdac9ec7b66e51c0def0cd9b9"
)
EXPECTED_PARLIAMENT_COUNT = 286
REVIEWER_ALIAS = "project-owner-v4-rollout"
RATIONALE = (
    "Fotografia factual da XVII Legislatura confirmada pelo proprietário do projecto "
    "contra a fonte oficial, o SHA-256 e a contagem auditada no repositório."
)


async def apply_rollout_schema(database_url: str) -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "prisma"
        / "migrations"
        / "20260806020000_v4_public_rollout"
        / "migration.sql"
    )
    sql = migration.read_text(encoding="utf-8")
    connection = await asyncpg.connect(database_url)
    try:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                "v4-public-rollout-schema",
            )
            await connection.execute(sql)
    finally:
        await connection.close()


async def bootstrap() -> None:
    settings = get_settings()
    if settings.environment != "production":
        raise RuntimeError("O bootstrap público V4 só pode correr em production")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")
    database_url = settings.database_url.get_secret_value()
    await apply_rollout_schema(database_url)

    repository = OfficialIndexStagingRepository(settings)
    await repository.connect()
    try:
        snapshot = await repository.inspect_parliament_people_publication(
            legislature="XVII"
        )
        if snapshot["source_sha256"] != EXPECTED_PARLIAMENT_SHA256:
            raise RuntimeError("O SHA-256 parlamentar diverge da fotografia auditada")
        if snapshot["candidate_count"] != EXPECTED_PARLIAMENT_COUNT:
            raise RuntimeError("A contagem parlamentar diverge da fotografia auditada")
        if not snapshot["archive_attested"]:
            raise RuntimeError("O original parlamentar não está atestado no arquivo privado")
        if snapshot["already_published"] == EXPECTED_PARLIAMENT_COUNT:
            return
        await repository.publish_parliament_people_snapshot(
            legislature="XVII",
            expected_source_sha256=EXPECTED_PARLIAMENT_SHA256,
            expected_count=EXPECTED_PARLIAMENT_COUNT,
            reviewer_alias=REVIEWER_ALIAS,
            rationale=RATIONALE,
        )
    finally:
        await repository.close()


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
