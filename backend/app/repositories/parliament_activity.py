from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg

from app.models.api import VoteActorType
from app.models.archive import RawArchiveReceipt
from app.models.parliamentary import ParliamentActivityDataset


@dataclass(frozen=True)
class ParliamentActivityPersistResult:
    source_document_id: str
    sessions_written: int
    initiatives_written: int
    vote_events_written: int
    vote_records_written: int
    archive_attestation_written: bool


def _database_timestamp(value: datetime) -> datetime:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.replace(tzinfo=None)


def _new_id(prefix: str, stable_value: str) -> str:
    digest = hashlib.sha256(stable_value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _attestation_digest(
    *,
    source_document_id: str,
    receipt: RawArchiveReceipt,
    archived_at: datetime,
    archived_by: str,
) -> str:
    canonical = json.dumps(
        {
            "source_document_id": source_document_id,
            "storage_backend": receipt.storage_backend,
            "storage_key": receipt.storage_key,
            "content_sha256": receipt.content_sha256,
            "byte_size": receipt.byte_size,
            "mime_type": receipt.mime_type,
            "retrieval_url": str(receipt.source_url),
            "retrieved_at": receipt.retrieved_at.astimezone(UTC).isoformat(),
            "archived_at": archived_at.astimezone(UTC).isoformat(),
            "archived_by": archived_by,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ParliamentActivityRepository:
    """Arquivo, atestação e persistência incremental da atividade parlamentar.

    A operação é atómica. Votos partidários permanecem partidários; apenas atores
    explicitamente nominais podem ser ligados a pessoas. Nada é publicado
    automaticamente.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def persist(
        self,
        dataset: ParliamentActivityDataset,
        *,
        archive_receipt: RawArchiveReceipt | None = None,
        archived_by: str = "parliament-activity-ingestion-v1",
    ) -> ParliamentActivityPersistResult:
        async with self.pool.acquire() as connection, connection.transaction():
            attestation_written = False
            if archive_receipt is not None:
                source_document_id, attestation_written = await self._register_attested_source(
                    connection,
                    dataset,
                    archive_receipt,
                    archived_by=archived_by,
                )
            else:
                source_document_id = await self._require_attested_source(connection, dataset)

            sessions_written = await self._upsert_sessions(connection, dataset, source_document_id)
            initiatives_written = await self._upsert_initiatives(
                connection, dataset, source_document_id
            )
            vote_events_written, vote_records_written = await self._upsert_votes(
                connection, dataset, source_document_id
            )
            return ParliamentActivityPersistResult(
                source_document_id=source_document_id,
                sessions_written=sessions_written,
                initiatives_written=initiatives_written,
                vote_events_written=vote_events_written,
                vote_records_written=vote_records_written,
                archive_attestation_written=attestation_written,
            )

    @staticmethod
    async def _register_attested_source(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        receipt: RawArchiveReceipt,
        *,
        archived_by: str,
    ) -> tuple[str, bool]:
        if receipt.content_sha256 != dataset.document_sha256:
            raise RuntimeError("O recibo de arquivo não corresponde ao SHA-256 do dataset")
        if str(receipt.source_url) != str(dataset.dataset_url):
            raise RuntimeError("O recibo de arquivo não corresponde à URL oficial do dataset")

        source_document_id = _new_id("source", f"{dataset.dataset_url}|{dataset.document_sha256}")
        await connection.execute(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, url, retrieved_at,
                 content_sha256, mime_type, raw_storage_key, parser_version, created_at)
            VALUES
                ($1, 'PARLIAMENT', 'OPEN_DATASET', $2, $3, $4,
                 $5, $6, $7, 'parliament-activity-v1', NOW())
            ON CONFLICT (url, content_sha256) DO UPDATE SET
                retrieved_at = EXCLUDED.retrieved_at,
                mime_type = EXCLUDED.mime_type,
                raw_storage_key = EXCLUDED.raw_storage_key,
                parser_version = EXCLUDED.parser_version
            """,
            source_document_id,
            f"Atividade parlamentar — {dataset.legislature}",
            str(dataset.dataset_url),
            _database_timestamp(receipt.retrieved_at),
            receipt.content_sha256,
            receipt.mime_type,
            receipt.storage_key,
        )
        actual_source_id = await connection.fetchval(
            "SELECT id FROM source_documents WHERE url = $1 AND content_sha256 = $2 LIMIT 1",
            str(dataset.dataset_url),
            dataset.document_sha256,
        )
        if actual_source_id is None:
            raise RuntimeError("Não foi possível registar o documento parlamentar")
        source_document_id = str(actual_source_id)

        archived_at = datetime.now(UTC)
        digest = _attestation_digest(
            source_document_id=source_document_id,
            receipt=receipt,
            archived_at=archived_at,
            archived_by=archived_by,
        )
        status = await connection.execute(
            """
            INSERT INTO source_archive_attestations
                (id, source_document_id, storage_backend, storage_key,
                 content_sha256, byte_size, mime_type, retrieval_url,
                 retrieved_at, archived_at, archived_by, attestation_sha256, created_at)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
            ON CONFLICT (source_document_id, storage_backend, storage_key) DO NOTHING
            """,
            _new_id("archive", digest),
            source_document_id,
            receipt.storage_backend,
            receipt.storage_key,
            receipt.content_sha256,
            receipt.byte_size,
            receipt.mime_type,
            str(receipt.source_url),
            _database_timestamp(receipt.retrieved_at),
            _database_timestamp(archived_at),
            archived_by,
            digest,
        )
        return source_document_id, status.endswith("1")

    @staticmethod
    async def _require_attested_source(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
    ) -> str:
        source_document_id = await connection.fetchval(
            """
            SELECT sd.id
            FROM source_documents sd
            WHERE sd.url = $1
              AND sd.content_sha256 = $2
              AND sd.publisher = 'PARLIAMENT'
              AND EXISTS (
                  SELECT 1 FROM source_archive_attestations attestation
                  WHERE attestation.source_document_id = sd.id
                    AND attestation.content_sha256 = sd.content_sha256
                    AND attestation.retrieval_url = sd.url
              )
            ORDER BY sd.retrieved_at DESC, sd.id DESC
            LIMIT 1
            """,
            str(dataset.dataset_url),
            dataset.document_sha256,
        )
        if source_document_id is None:
            raise RuntimeError(
                "A atividade parlamentar só pode ser persistida depois de os bytes "
                "oficiais estarem arquivados e atestados."
            )
        return str(source_document_id)

    @staticmethod
    async def _upsert_sessions(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
    ) -> int:
        written = 0
        for session in dataset.sessions:
            await connection.execute(
                """
                INSERT INTO parliamentary_sessions
                    (id, source_id, legislature, session_number, title,
                     starts_at, ends_at, source_document_id)
                VALUES ('session_' || md5($1), $1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (source_id) DO UPDATE SET
                    legislature = EXCLUDED.legislature,
                    session_number = EXCLUDED.session_number,
                    title = EXCLUDED.title,
                    starts_at = EXCLUDED.starts_at,
                    ends_at = EXCLUDED.ends_at,
                    source_document_id = EXCLUDED.source_document_id
                """,
                session.source_id,
                session.legislature,
                session.session_number,
                session.title,
                _database_timestamp(session.starts_at),
                _database_timestamp(session.ends_at) if session.ends_at else None,
                source_document_id,
            )
            written += 1
        return written

    @staticmethod
    async def _upsert_initiatives(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
    ) -> int:
        written = 0
        for initiative in dataset.initiatives:
            await connection.execute(
                """
                INSERT INTO parliamentary_initiatives
                    (id, source_id, legislature, number, type, title, description,
                     introduced_at, status, official_url, source_document_id,
                     created_at, updated_at)
                VALUES ('initiative_' || md5($1), $1, $2, $3, $4, $5, $6,
                        $7, $8, $9, $10, NOW(), NOW())
                ON CONFLICT (source_id) DO UPDATE SET
                    legislature = EXCLUDED.legislature,
                    number = EXCLUDED.number,
                    type = EXCLUDED.type,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    introduced_at = EXCLUDED.introduced_at,
                    status = EXCLUDED.status,
                    official_url = EXCLUDED.official_url,
                    source_document_id = EXCLUDED.source_document_id,
                    updated_at = NOW()
                """,
                initiative.source_id,
                initiative.legislature,
                initiative.number,
                initiative.initiative_type,
                initiative.title,
                initiative.description,
                _database_timestamp(initiative.introduced_at)
                if initiative.introduced_at
                else None,
                initiative.status,
                str(initiative.official_url),
                source_document_id,
            )
            written += 1
        return written

    @staticmethod
    async def _upsert_votes(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
    ) -> tuple[int, int]:
        events_written = 0
        records_written = 0
        for event in dataset.votes:
            initiative_id = None
            if event.initiative_number:
                initiative_id = await connection.fetchval(
                    """
                    SELECT id FROM parliamentary_initiatives
                    WHERE number = $1 AND legislature = $2
                    ORDER BY updated_at DESC, id DESC LIMIT 1
                    """,
                    event.initiative_number,
                    dataset.legislature,
                )
            event_id = _new_id("vote", event.source_id)
            await connection.execute(
                """
                INSERT INTO vote_events
                    (id, source_id, initiative_id, title, initiative_number,
                     voted_at, result, is_nominal, source_document_id,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
                ON CONFLICT (source_id) DO UPDATE SET
                    initiative_id = EXCLUDED.initiative_id,
                    title = EXCLUDED.title,
                    initiative_number = EXCLUDED.initiative_number,
                    voted_at = EXCLUDED.voted_at,
                    result = EXCLUDED.result,
                    is_nominal = EXCLUDED.is_nominal,
                    source_document_id = EXCLUDED.source_document_id,
                    updated_at = NOW()
                """,
                event_id,
                event.source_id,
                initiative_id,
                event.title,
                event.initiative_number,
                _database_timestamp(event.voted_at) if event.voted_at else None,
                event.result,
                event.is_nominal,
                source_document_id,
            )
            actual_event_id = await connection.fetchval(
                "SELECT id FROM vote_events WHERE source_id = $1 LIMIT 1",
                event.source_id,
            )
            if actual_event_id is None:
                raise RuntimeError("Não foi possível persistir a votação parlamentar")
            events_written += 1

            await connection.execute(
                "DELETE FROM vote_records WHERE vote_event_id = $1",
                actual_event_id,
            )
            for record in event.records:
                person_id = None
                party_id = None
                if record.actor_type is VoteActorType.PERSON:
                    if not event.is_nominal:
                        raise RuntimeError(
                            "Uma votação não nominal não pode conter votos atribuídos a pessoas"
                        )
                    if record.actor_source_id:
                        person_id = await connection.fetchval(
                            "SELECT id FROM people WHERE source_id = $1 LIMIT 1",
                            record.actor_source_id,
                        )
                elif record.actor_type is VoteActorType.PARTY:
                    party_id = await connection.fetchval(
                        """
                        SELECT id FROM parties
                        WHERE short_name = $1 OR source_id = $1
                        ORDER BY id LIMIT 1
                        """,
                        record.actor_label,
                    )

                await connection.execute(
                    """
                    INSERT INTO vote_records
                        (id, vote_event_id, actor_type, actor_label,
                         person_id, party_id, choice, source_document_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    _new_id(
                        "vote_record",
                        f"{actual_event_id}|{record.actor_type.value}|{record.actor_label}",
                    ),
                    actual_event_id,
                    record.actor_type.value,
                    record.actor_label,
                    person_id,
                    party_id,
                    record.choice.value,
                    source_document_id,
                )
                records_written += 1
        return events_written, records_written
