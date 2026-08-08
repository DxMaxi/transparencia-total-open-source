"""Recolhe, arquiva e persiste a fotografia parlamentar completa.

A operação não publica dados. Apenas cria prova, staging factual e SyncRun auditável.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime

from app.core.config import get_settings
from app.models.parliamentary import ParliamentActivityDataset
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.parliament_activity import ParliamentActivityRepository
from app.services.http import OfficialHttpClient
from app.services.parlamento import ParlamentoCollector
from app.services.parliamentary_activity import normalise_initiatives, normalise_sessions

CODE_VERSION = "parliament-activity-v4"
SOURCE_NAME = "PARLIAMENT_ACTIVITY"
MAX_SNAPSHOT_RECORDS = 250_000


async def run(legislature: str) -> dict[str, object]:
    settings = get_settings()
    repository = OfficialIndexStagingRepository(settings)
    await repository.connect()
    pool = repository.pool
    if pool is None:
        raise RuntimeError("Base de dados não configurada")

    started_at = datetime.now(UTC)
    sync_id = f"sync_parliament_activity_{started_at:%Y%m%d%H%M%S%f}"
    dataset_url: str | None = None
    try:
        print(f"[atividade] início da execução {sync_id}", flush=True)
        async with pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE sync_runs
                SET status = 'FAILED', finished_at = $1,
                    error_message = COALESCE(
                        error_message,
                        'Execução anterior interrompida antes da conclusão'
                    )
                WHERE source_name = $2 AND status = 'RUNNING'
                """,
                started_at.replace(tzinfo=None),
                SOURCE_NAME,
            )
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

        print("[atividade] a descobrir e descarregar a fonte oficial", flush=True)
        async with OfficialHttpClient(settings) as http:
            collector = ParlamentoCollector(settings, http)
            discovered_url = str(settings.parlamento_votes_url or "")
            if not discovered_url:
                discovered_url = await collector.discover_dataset_url(
                    settings.parlamento_initiatives_catalogue_path,
                    legislature,
                )
            payload, raw_document = await collector.fetch_json(
                discovered_url,
                max_bytes=settings.parlamento_votes_max_bytes,
            )
            dataset_url = str(raw_document.source_url)

        print(
            f"[atividade] fonte recebida: {len(raw_document.content)} bytes; "
            f"sha256={raw_document.content_sha256}",
            flush=True,
        )
        print("[atividade] a normalizar sessões, iniciativas e votações", flush=True)
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
        votes = collector.normalise_votes(
            payload,
            source_url=dataset_url,
            document_sha256=raw_document.content_sha256,
            retrieved_at=raw_document.retrieved_at,
        )
        if not sessions:
            raise ValueError("Fotografia rejeitada: nenhuma sessão oficial normalizável")
        if not initiatives:
            raise ValueError("Fotografia rejeitada: nenhuma iniciativa oficial normalizável")
        if not votes:
            raise ValueError("Fotografia rejeitada: nenhuma votação oficial normalizável")
        total_records = (
            len(sessions)
            + len(initiatives)
            + len(votes)
            + sum(len(event.records) for event in votes)
        )
        if total_records > MAX_SNAPSHOT_RECORDS:
            raise ValueError(
                "Fotografia rejeitada: dimensão acima do limite operacional "
                f"({total_records} > {MAX_SNAPSHOT_RECORDS})"
            )
        print(
            "[atividade] normalização concluída: "
            f"{len(sessions)} sessões, {len(initiatives)} iniciativas, "
            f"{len(votes)} votações e "
            f"{sum(len(event.records) for event in votes)} posições",
            flush=True,
        )

        warnings: list[str] = []
        votes_without_positions = sum(not event.records for event in votes)
        if votes_without_positions:
            warnings.append(
                f"{votes_without_positions} votações não incluem posições normalizáveis; "
                "o resultado oficial é preservado sem inventar atores."
            )
        unknown_positions = sum(
            record.actor_type.value == "UNKNOWN" for event in votes for record in event.records
        )
        if unknown_positions:
            warnings.append(
                f"{unknown_positions} posições conservam ator UNKNOWN e não foram "
                "atribuídas a pessoas ou partidos."
            )

        dataset = ParliamentActivityDataset(
            legislature=legislature,
            dataset_url=dataset_url,
            document_sha256=raw_document.content_sha256,
            parser_version=CODE_VERSION,
            sessions=sessions,
            initiatives=initiatives,
            votes=votes,
            warnings=warnings,
            collected_at=raw_document.retrieved_at,
            raw_document=raw_document,
        )
        print("[atividade] a arquivar os bytes oficiais", flush=True)
        receipt = await repository.archive_raw_document(raw_document=raw_document)
        print("[atividade] a persistir a fotografia em lotes", flush=True)
        result = await ParliamentActivityRepository(pool).persist(
            dataset,
            archive_receipt=receipt,
            archived_by=CODE_VERSION,
        )
        print(
            f"[atividade] fotografia persistida: snapshot={result.snapshot_id}",
            flush=True,
        )
        records_read = total_records
        records_written = (
            result.sessions_written
            + result.initiatives_written
            + result.vote_events_written
            + result.vote_records_written
        )
        status = "PARTIAL" if warnings else "SUCCEEDED"

        async with pool.acquire() as connection:
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
            "normalised_snapshot_id": result.snapshot_id,
            "snapshot_created": result.snapshot_created,
            "sessions": result.sessions_written,
            "initiatives": result.initiatives_written,
            "votes": result.vote_events_written,
            "vote_records": result.vote_records_written,
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
