"""Recolhe, arquiva e persiste sessões e iniciativas parlamentares.

A operação não publica dados. Apenas cria prova, staging factual e SyncRun auditável.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime

from app.core.config import get_settings
from app.models.parliamentary import ParliamentActivityDataset
from app.repositories.parliament_activity import ParliamentActivityRepository
from app.repositories.postgres import PostgresRepository
from app.services.http import OfficialHttpClient
from app.services.parlamento import ParlamentoCollector
from app.services.parliamentary_activity import normalise_initiatives, normalise_sessions
from app.services.raw_archive import ContentAddressedFileArchive

CODE_VERSION = "parliament-activity-ingestion-v1"
SOURCE_NAME = "PARLIAMENT_ACTIVITY"


async def run(legislature: str) -> dict[str, object]:
    settings = get_settings()
    archive = ContentAddressedFileArchive.from_settings(settings)
    repository = PostgresRepository(settings)
    await repository.connect()
    if repository.pool is None:
        raise RuntimeError("Base de dados não configurada")

    started_at = datetime.now(UTC)
    sync_id = f"sync_parliament_activity_{started_at:%Y%m%d%H%M%S%f}"
    dataset_url: str | None = None
    try:
        async with repository.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO sync_runs
                    (id, source_name, status, started_at, records_read,
                     records_written, warnings, code_version)
                VALUES ($1, $2, 'RUNNING', $3, 0, 0, '[]'::jsonb, $4)
                """,
                sync_id,
                SOURCE_NAME,
                started_at.replace(tzinfo=None),
                CODE_VERSION,
            )

        async with OfficialHttpClient(settings) as http:
            collector = ParlamentoCollector(settings, http)
            dataset_url = await collector.discover_dataset_url(
                settings.parlamento_initiatives_catalogue_path,
                legislature,
            )
            payload, raw_document = await collector.fetch_json(
                dataset_url,
                max_bytes=settings.parlamento_votes_max_bytes,
            )

        sessions = normalise_sessions(
            payload,
            legislature=legislature,
            source_url=dataset_url,
            document_sha256=raw_document.content_sha256,
            retrieved_at=raw_document.retrieved_at,
        )
        initiatives = normalise_initiatives(
            payload,
            legislature=legislature,
            source_url=dataset_url,
            document_sha256=raw_document.content_sha256,
            retrieved_at=raw_document.retrieved_at,
            parliament_base_url=str(settings.parlamento_base_url),
        )
        warnings: list[str] = []
        if not sessions:
            warnings.append("A fonte não produziu sessões normalizáveis.")
        if not initiatives:
            warnings.append("A fonte não produziu iniciativas normalizáveis.")

        dataset = ParliamentActivityDataset(
            legislature=legislature,
            dataset_url=dataset_url,
            document_sha256=raw_document.content_sha256,
            sessions=sessions,
            initiatives=initiatives,
            warnings=warnings,
            raw_document=raw_document,
        )
        receipt = archive.archive(raw_document)
        result = await ParliamentActivityRepository(repository.pool).persist(
            dataset,
            archive_receipt=receipt,
            archived_by=CODE_VERSION,
        )
        records_read = len(sessions) + len(initiatives)
        records_written = result.sessions_written + result.initiatives_written
        status = "PARTIAL" if warnings else "SUCCEEDED"

        async with repository.pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE sync_runs
                SET dataset_url = $2, status = $3, finished_at = $4,
                    records_read = $5, records_written = $6, warnings = $7::jsonb
                WHERE id = $1
                """,
                sync_id,
                dataset_url,
                status,
                datetime.now(UTC).replace(tzinfo=None),
                records_read,
                records_written,
                json.dumps(warnings, ensure_ascii=False),
            )
        return {
            "sync_id": sync_id,
            "status": status,
            "dataset_url": dataset_url,
            "document_sha256": raw_document.content_sha256,
            "sessions": result.sessions_written,
            "initiatives": result.initiatives_written,
            "archive_attestation_written": result.archive_attestation_written,
            "warnings": warnings,
            "publication": "PENDING_HUMAN_REVIEW",
        }
    except Exception as exc:
        if repository.pool is not None:
            async with repository.pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE sync_runs
                    SET dataset_url = $2, status = 'FAILED', finished_at = $3,
                        error_message = $4
                    WHERE id = $1
                    """,
                    sync_id,
                    dataset_url,
                    datetime.now(UTC).replace(tzinfo=None),
                    str(exc)[:4000],
                )
        raise
    finally:
        await repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legislature", default="XVII")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.legislature)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
