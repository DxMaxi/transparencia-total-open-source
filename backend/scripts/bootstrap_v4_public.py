"""Aplica o schema V4 e publica apenas uma fotografia parlamentar já auditada."""

import asyncio
import json
from pathlib import Path

import asyncpg

from app.core.config import get_settings
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.http import OfficialHttpClient
from app.services.parlamento import ParlamentoCollector

EXPECTED_PARLIAMENT_SHA256 = "e54b30869212ea3d50a401637a31847339e29dcfdac9ec7b66e51c0def0cd9b9"
EXPECTED_PARLIAMENT_COUNT = 286
PARLIAMENT_CODE_VERSION = "parliament-ingestion-v12"
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


async def restore_or_stage_parliament_source(
    repository: OfficialIndexStagingRepository,
    *,
    audited_snapshot: dict[str, object],
) -> dict[str, object]:
    """Restaura a versão auditada ou guarda uma versão nova para revisão humana."""

    settings = repository.settings
    async with OfficialHttpClient(settings) as http:
        current_dataset = await ParlamentoCollector(settings, http).collect_deputies("XVII")

    raw_document = current_dataset.raw_document
    if raw_document is None:
        raise RuntimeError("A recolha parlamentar não conservou os bytes oficiais")

    if raw_document.content_sha256 != EXPECTED_PARLIAMENT_SHA256:
        receipt = await repository.archive_raw_document(raw_document=raw_document)
        persistence = await repository.store_parliament_dataset(
            current_dataset,
            kind="deputies",
            code_version=PARLIAMENT_CODE_VERSION,
            archive_receipt=receipt,
        )
        return {
            "status": "REVIEW_REQUIRED",
            "publication_performed": False,
            "reason": "A fonte oficial mudou após a auditoria; a nova fotografia foi preservada em staging.",
            "audited_source_sha256": EXPECTED_PARLIAMENT_SHA256,
            "current_source_sha256": raw_document.content_sha256,
            "current_candidate_count": len(current_dataset.deputies),
            "storage_key": receipt.storage_key,
            "persistence": persistence,
        }

    source_url = str(audited_snapshot["source_url"])
    if str(raw_document.source_url) != source_url:
        raise RuntimeError(
            "O SHA-256 coincide, mas a URL final diverge da fonte auditada; "
            "a publicação permanece bloqueada"
        )

    restoration = await repository.attest_existing_source_bytes(
        source_document_id=str(audited_snapshot["source_document_id"]),
        raw_document=raw_document,
        archived_by="bootstrap:v4-exact-reattestation",
    )
    return {
        "status": "RESTORED",
        "publication_performed": False,
        "restoration": restoration,
    }


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
            result = {
                "status": "REVIEW_REQUIRED",
                "publication_performed": False,
                "reason": "A fotografia mais recente em staging não é a fotografia auditada no rollout.",
                "audited_source_sha256": EXPECTED_PARLIAMENT_SHA256,
                "current_source_sha256": snapshot["source_sha256"],
                "current_candidate_count": snapshot["candidate_count"],
            }
            print(json.dumps(result, ensure_ascii=False, default=str))
            return
        if snapshot["candidate_count"] != EXPECTED_PARLIAMENT_COUNT:
            raise RuntimeError("A contagem parlamentar diverge da fotografia auditada")
        if not snapshot["archive_attested"]:
            result = await restore_or_stage_parliament_source(
                repository,
                audited_snapshot=snapshot,
            )
            print(json.dumps(result, ensure_ascii=False, default=str))
            if result["status"] == "REVIEW_REQUIRED":
                return
            snapshot = await repository.inspect_parliament_people_publication(
                legislature="XVII"
            )
        if not snapshot["archive_attested"]:
            raise RuntimeError(
                "O original parlamentar continua sem uma atestação de arquivo válida"
            )
        if snapshot["already_published"] == EXPECTED_PARLIAMENT_COUNT:
            print(
                json.dumps(
                    {
                        "status": "ALREADY_PUBLISHED",
                        "publication_performed": False,
                        "source_sha256": EXPECTED_PARLIAMENT_SHA256,
                        "candidate_count": EXPECTED_PARLIAMENT_COUNT,
                    },
                    ensure_ascii=False,
                )
            )
            return
        publication = await repository.publish_parliament_people_snapshot(
            legislature="XVII",
            expected_source_sha256=EXPECTED_PARLIAMENT_SHA256,
            expected_count=EXPECTED_PARLIAMENT_COUNT,
            reviewer_alias=REVIEWER_ALIAS,
            rationale=RATIONALE,
        )
        print(
            json.dumps(
                {
                    "status": "PUBLISHED",
                    "publication_performed": True,
                    "publication": publication,
                },
                ensure_ascii=False,
                default=str,
            )
        )
    finally:
        await repository.close()


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
