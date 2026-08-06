from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg

from app.models.parliamentary import ParliamentActivityDataset


@dataclass(frozen=True)
class ParliamentActivityPersistResult:
    source_document_id: str
    sessions_written: int
    initiatives_written: int


class ParliamentActivityRepository:
    """Persistência incremental de atividade parlamentar já arquivada e atestada.

    Esta classe não cria nem publica prova. Exige que o SourceDocument e a respetiva
    atestação append-only já existam. Assim, uma recolha nunca se transforma
    silenciosamente em publicação.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def persist(self, dataset: ParliamentActivityDataset) -> ParliamentActivityPersistResult:
        async with self.pool.acquire() as connection, connection.transaction():
            source_document_id = await self._require_attested_source(connection, dataset)
            sessions_written = await self._upsert_sessions(
                connection, dataset, source_document_id
            )
            initiatives_written = await self._upsert_initiatives(
                connection, dataset, source_document_id
            )
            return ParliamentActivityPersistResult(
                source_document_id=source_document_id,
                sessions_written=sessions_written,
                initiatives_written=initiatives_written,
            )

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
                  SELECT 1
                  FROM source_archive_attestations attestation
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
                VALUES
                    ('session_' || md5($1), $1, $2, $3, $4, $5, $6, $7)
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
                session.starts_at.replace(tzinfo=None),
                session.ends_at.replace(tzinfo=None) if session.ends_at else None,
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
                VALUES
                    ('initiative_' || md5($1), $1, $2, $3, $4, $5, $6,
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
                initiative.introduced_at.replace(tzinfo=None)
                if initiative.introduced_at
                else None,
                initiative.status,
                str(initiative.official_url),
                source_document_id,
            )
            written += 1
        return written
