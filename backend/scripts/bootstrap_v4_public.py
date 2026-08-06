"""Aplica o schema de rollout e publica apenas o snapshot AR previamente auditado."""

import asyncio
from pathlib import Path

import asyncpg

from app.core.config import get_settings
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.http import OfficialHttpClient
from app.services.parlamento import ParlamentoCollector

EXPECTED_PARLIAMENT_SHA256 = "e54b30869212ea3d50a401637a31847339e29dcfdac9ec7b66e51c0def0cd9b9"
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


async def restore_exact_parliament_archive(
    repository: OfficialIndexStagingRepository,
    *,
    snapshot: dict[str, object],
) -> dict[str, object]:
    """Reobtém e atesta apenas o mesmo documento oficial, byte por byte."""

    settings = repository.settings
    source_url = str(snapshot["source_url"])
    source_document_id = str(snapshot["source_document_id"])
    async with OfficialHttpClient(settings) as http:
        collector = ParlamentoCollector(settings, http)
        _, raw_document = await collector.fetch_json(source_url)

    if raw_document.content_sha256 != EXPECTED_PARLIAMENT_SHA256:
        raise RuntimeError(
            "O documento parlamentar actual diverge do SHA-256 auditado; "
            "a publicação foi bloqueada"
        )
    if str(raw_document.source_url) != source_url:
        raise RuntimeError(
            "A URL final do documento parlamentar diverge da fonte persistida; "
            "a publicação foi bloqueada"
        )

    return await repository.attest_existing_source_bytes(
        source_document_id=source_document_id,
        raw_document=raw_document,
        archived_by="bootstrap:v4-exact-reattestation",
    )


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
        snapshot = await repository.inspect_parliament_people_publication(legislature="XVII")
        if snapshot["source_sha256"] != EXPECTED_PARLIAMENT_SHA256:
            raise RuntimeError("O SHA-256 parlamentar diverge da fotografia auditada")
        if snapshot["candidate_count"] != EXPECTED_PARLIAMENT_COUNT:
            raise RuntimeError("A contagem parlamentar diverge da fotografia auditada")
        if not snapshot["archive_attested"]:
            await restore_exact_parliament_archive(repository, snapshot=snapshot)
            snapshot = await repository.inspect_parliament_people_publication(
                legislature="XVII"
            )
        if not snapshot["archive_attested"]:
            raise RuntimeError(
                "O original parlamentar continua sem uma atestação de arquivo válida"
            )
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
