"""Atualiza índices oficiais da V4 fora do ciclo de vida da API."""

import asyncio
import json

from app.core.config import get_settings
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.v4_rollout import DEFAULT_ROLLOUT_SOURCES, V4RolloutService


async def refresh() -> None:
    settings = get_settings()
    if settings.environment not in {"staging", "production"}:
        raise RuntimeError("A atualização V4 só pode correr em staging ou production")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")

    repository = OfficialIndexStagingRepository(settings)
    await repository.connect()
    try:
        results = await V4RolloutService(settings, repository).sync_sources(
            list(DEFAULT_ROLLOUT_SOURCES)
        )
    finally:
        await repository.close()

    failed = [result for result in results if result.get("status") == "FAILED"]
    partial = [result for result in results if result.get("status") == "PARTIAL"]
    print(
        json.dumps(
            {
                "status": "PARTIAL" if failed or partial else "SUCCEEDED",
                "sources": results,
                "failed_sources": [result.get("source_name") for result in failed],
                "partial_sources": [result.get("source_name") for result in partial],
            },
            ensure_ascii=False,
            default=str,
        )
    )
    if failed:
        raise RuntimeError("Uma ou mais fontes oficiais falharam; consultar o relatório do job")


def main() -> None:
    asyncio.run(refresh())


if __name__ == "__main__":
    main()
