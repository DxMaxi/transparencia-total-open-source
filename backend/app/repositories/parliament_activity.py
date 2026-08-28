from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg

from app.models.api import VoteActorType
from app.models.archive import RawArchiveReceipt
from app.models.parliamentary import ParliamentActivityDataset
from app.repositories.parliament_activity_bulk import append_activity_snapshot


@dataclass(frozen=True, slots=True)
class ParliamentActivityPersistResult:
    source_document_id: str
    snapshot_id: str
    snapshot_created: bool
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


def _dataset_digest(dataset: ParliamentActivityDataset) -> str:
    canonical = {
        "legislature": dataset.legislature,
        "parser_version": dataset.parser_version,
        "sessions": [item.model_dump(mode="json", exclude={"source"}) for item in dataset.sessions],
        "initiatives": [
            item.model_dump(mode="json", exclude={"source"}) for item in dataset.initiatives
        ],
        "votes": [item.model_dump(mode="json", exclude={"source"}) for item in dataset.votes],
    }
    serialised = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


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
    """Persiste fotografias parlamentares imutáveis sem as publicar.

    A identidade de cada fotografia inclui documento, legislatura e versão do
    parser. Repetir exatamente a mesma recolha é idempotente; corrigir o parser
    exige uma nova versão e conserva integralmente a normalização anterior.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def persist(
        self,
        dataset: ParliamentActivityDataset,
        *,
        archive_receipt: RawArchiveReceipt | None = None,
        archived_by: str = "parliament-activity-v6",
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

            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                (
                    "parliament-activity-snapshot:"
                    f"{source_document_id}:{dataset.legislature}:{dataset.parser_version}"
                ),
            )
            snapshot_id, snapshot_created = await self._ensure_snapshot(
                connection,
                dataset,
                source_document_id,
            )
            (
                sessions_written,
                initiatives_written,
                vote_events_written,
                vote_records_written,
            ) = await append_activity_snapshot(
                connection,
                dataset,
                source_document_id,
                snapshot_id,
            )
            await self._validate_materialised_snapshot(connection, snapshot_id)
            if snapshot_created:
                await self._record_ingestion_audit(
                    connection,
                    dataset=dataset,
                    source_document_id=source_document_id,
                    snapshot_id=snapshot_id,
                    actor_alias=archived_by,
                )

            return ParliamentActivityPersistResult(
                source_document_id=source_document_id,
                snapshot_id=snapshot_id,
                snapshot_created=snapshot_created,
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

        proposed_source_id = _new_id(
            "source",
            f"{dataset.dataset_url}|{dataset.document_sha256}",
        )
        await connection.execute(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, url, retrieved_at,
                 content_sha256, mime_type, raw_storage_key, parser_version, created_at)
            VALUES
                ($1, 'PARLIAMENT', 'OPEN_DATASET', $2, $3, $4,
                 $5, $6, $7, 'parliament-raw-v1', NOW())
            ON CONFLICT (url, content_sha256) DO NOTHING
            """,
            proposed_source_id,
            f"Atividade parlamentar — {dataset.legislature}",
            str(dataset.dataset_url),
            _database_timestamp(receipt.retrieved_at),
            receipt.content_sha256,
            receipt.mime_type,
            receipt.storage_key,
        )
        source = await connection.fetchrow(
            """
            SELECT id, publisher::text AS publisher, url, content_sha256
            FROM source_documents
            WHERE url = $1 AND content_sha256 = $2
            LIMIT 1
            """,
            str(dataset.dataset_url),
            dataset.document_sha256,
        )
        if source is None:
            raise RuntimeError("Não foi possível registar o documento parlamentar")
        if str(source["publisher"]) != "PARLIAMENT":
            raise RuntimeError("O documento existente não pertence à fonte parlamentar")
        source_document_id = str(source["id"])

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
    async def _ensure_snapshot(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
    ) -> tuple[str, bool]:
        snapshot_key = f"{source_document_id}|{dataset.legislature}|{dataset.parser_version}"
        snapshot_id = _new_id("parliament_snapshot", snapshot_key)
        normalised_sha256 = _dataset_digest(dataset)
        vote_record_count = sum(len(event.records) for event in dataset.votes)
        inserted = await connection.fetchval(
            """
            INSERT INTO parliament_activity_snapshots
                (id, source_document_id, legislature, parser_version,
                 normalised_sha256, collected_at, session_count,
                 initiative_count, vote_count, vote_record_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (source_document_id, legislature, parser_version) DO NOTHING
            RETURNING id
            """,
            snapshot_id,
            source_document_id,
            dataset.legislature,
            dataset.parser_version,
            normalised_sha256,
            _database_timestamp(dataset.collected_at),
            len(dataset.sessions),
            len(dataset.initiatives),
            len(dataset.votes),
            vote_record_count,
        )
        existing = await connection.fetchrow(
            """
            SELECT id, normalised_sha256, session_count, initiative_count,
                   vote_count, vote_record_count
            FROM parliament_activity_snapshots
            WHERE source_document_id = $1 AND legislature = $2 AND parser_version = $3
            """,
            source_document_id,
            dataset.legislature,
            dataset.parser_version,
        )
        if existing is None:
            raise RuntimeError("Não foi possível criar nem recuperar a fotografia parlamentar")
        expected = (
            normalised_sha256,
            len(dataset.sessions),
            len(dataset.initiatives),
            len(dataset.votes),
            vote_record_count,
        )
        observed = (
            str(existing["normalised_sha256"]),
            int(existing["session_count"]),
            int(existing["initiative_count"]),
            int(existing["vote_count"]),
            int(existing["vote_record_count"]),
        )
        if observed != expected:
            raise ValueError(
                "O mesmo documento e versão de parser produziram uma normalização diferente; "
                "corrija o parser e incremente a sua versão."
            )
        return str(existing["id"]), inserted is not None

    @staticmethod
    async def _append_sessions(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
        snapshot_id: str,
    ) -> int:
        written = 0
        for session in dataset.sessions:
            inserted = await connection.fetchval(
                """
                INSERT INTO parliamentary_sessions
                    (id, source_id, legislature, session_number, title,
                     starts_at, ends_at, snapshot_id, source_document_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (source_id, snapshot_id) DO NOTHING
                RETURNING id
                """,
                _new_id("session", f"{snapshot_id}|{session.source_id}"),
                session.source_id,
                session.legislature,
                session.session_number,
                session.title,
                _database_timestamp(session.starts_at),
                _database_timestamp(session.ends_at) if session.ends_at else None,
                snapshot_id,
                source_document_id,
            )
            written += inserted is not None
        return written

    @staticmethod
    async def _append_initiatives(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
        snapshot_id: str,
    ) -> int:
        written = 0
        for initiative in dataset.initiatives:
            inserted = await connection.fetchval(
                """
                INSERT INTO parliamentary_initiatives
                    (id, source_id, legislature, number, type, title, description,
                     introduced_at, status, official_url, snapshot_id,
                     source_document_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, NOW(), NOW())
                ON CONFLICT (source_id, snapshot_id) DO NOTHING
                RETURNING id
                """,
                _new_id("initiative", f"{snapshot_id}|{initiative.source_id}"),
                initiative.source_id,
                initiative.legislature,
                initiative.number,
                initiative.initiative_type,
                initiative.title,
                initiative.description,
                (
                    _database_timestamp(initiative.introduced_at)
                    if initiative.introduced_at
                    else None
                ),
                initiative.status,
                str(initiative.official_url),
                snapshot_id,
                source_document_id,
            )
            written += inserted is not None
        return written

    @staticmethod
    async def _append_votes(
        connection: asyncpg.Connection,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
        snapshot_id: str,
    ) -> tuple[int, int]:
        events_written = 0
        records_written = 0
        for event in dataset.votes:
            initiative_id = None
            if event.initiative_number:
                initiative_id = await connection.fetchval(
                    """
                    SELECT id FROM parliamentary_initiatives
                    WHERE number = $1 AND snapshot_id = $2
                    ORDER BY id LIMIT 1
                    """,
                    event.initiative_number,
                    snapshot_id,
                )
            event_id = _new_id("vote", f"{snapshot_id}|{event.source_id}")
            inserted_event_id = await connection.fetchval(
                """
                INSERT INTO vote_events
                    (id, source_id, legislature, initiative_id, title,
                     initiative_number, voted_at, result, is_nominal,
                     snapshot_id, source_document_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())
                ON CONFLICT (source_id, snapshot_id) DO NOTHING
                RETURNING id
                """,
                event_id,
                event.source_id,
                dataset.legislature,
                initiative_id,
                event.title,
                event.initiative_number,
                _database_timestamp(event.voted_at) if event.voted_at else None,
                event.result,
                event.is_nominal,
                snapshot_id,
                source_document_id,
            )
            actual_event_id = inserted_event_id or await connection.fetchval(
                """
                SELECT id FROM vote_events
                WHERE source_id = $1 AND snapshot_id = $2
                LIMIT 1
                """,
                event.source_id,
                snapshot_id,
            )
            if actual_event_id is None:
                raise RuntimeError("Não foi possível persistir a votação parlamentar")
            events_written += inserted_event_id is not None

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
                elif record.actor_type is VoteActorType.PARTY and record.actor_source_id:
                    party_id = await connection.fetchval(
                        "SELECT id FROM parties WHERE source_id = $1 LIMIT 1",
                        record.actor_source_id,
                    )

                inserted_record_id = await connection.fetchval(
                    """
                    INSERT INTO vote_records
                        (id, vote_event_id, actor_type, actor_label, actor_source_id,
                         person_id, party_id, choice, source_document_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (vote_event_id, actor_type, actor_label) DO NOTHING
                    RETURNING id
                    """,
                    _new_id(
                        "vote_record",
                        f"{actual_event_id}|{record.actor_type.value}|{record.actor_label}",
                    ),
                    actual_event_id,
                    record.actor_type.value,
                    record.actor_label,
                    record.actor_source_id,
                    person_id,
                    party_id,
                    record.choice.value,
                    source_document_id,
                )
                records_written += inserted_record_id is not None
        return events_written, records_written

    @staticmethod
    async def _validate_materialised_snapshot(
        connection: asyncpg.Connection,
        snapshot_id: str,
    ) -> None:
        row = await connection.fetchrow(
            """
            SELECT snapshot.session_count, snapshot.initiative_count,
                   snapshot.vote_count, snapshot.vote_record_count,
                   (SELECT COUNT(*) FROM parliamentary_sessions session
                    WHERE session.snapshot_id = snapshot.id) AS actual_sessions,
                   (SELECT COUNT(*) FROM parliamentary_initiatives initiative
                    WHERE initiative.snapshot_id = snapshot.id) AS actual_initiatives,
                   (SELECT COUNT(*) FROM vote_events event
                    WHERE event.snapshot_id = snapshot.id) AS actual_votes,
                   (SELECT COUNT(*) FROM vote_records record
                    JOIN vote_events event ON event.id = record.vote_event_id
                    WHERE event.snapshot_id = snapshot.id
                       AND record.source_document_id = snapshot.source_document_id)
                        AS actual_vote_records,
                   (SELECT COUNT(*) FROM vote_records record
                    JOIN vote_events event ON event.id = record.vote_event_id
                    WHERE event.snapshot_id = snapshot.id
                      AND record.actor_type = 'PERSON'
                      AND record.actor_source_id IS NULL) AS person_records_without_official_id,
                   (SELECT COUNT(*) FROM vote_records record
                    JOIN vote_events event ON event.id = record.vote_event_id
                    JOIN people person ON person.id = record.person_id
                    WHERE event.snapshot_id = snapshot.id
                      AND record.actor_type = 'PERSON'
                      AND record.actor_source_id IS DISTINCT FROM person.source_id)
                        AS mismatched_person_links
            FROM parliament_activity_snapshots snapshot
            WHERE snapshot.id = $1
            """,
            snapshot_id,
        )
        if row is None:
            raise RuntimeError("Fotografia parlamentar não encontrada após persistência")
        expected = (
            int(row["session_count"]),
            int(row["initiative_count"]),
            int(row["vote_count"]),
            int(row["vote_record_count"]),
        )
        actual = (
            int(row["actual_sessions"]),
            int(row["actual_initiatives"]),
            int(row["actual_votes"]),
            int(row["actual_vote_records"]),
        )
        if actual != expected:
            raise RuntimeError(
                "A materialização parlamentar não coincide com o manifesto imutável "
                f"(esperado={expected}, observado={actual})."
            )
        if int(row["person_records_without_official_id"]):
            raise RuntimeError(
                "Uma posição PERSON não preserva o identificador oficial; "
                "é necessária uma nova versão do parser."
            )
        if int(row["mismatched_person_links"]):
            raise RuntimeError(
                "Uma posição PERSON está ligada a um identificador oficial diferente."
            )

    @staticmethod
    async def _record_ingestion_audit(
        connection: asyncpg.Connection,
        *,
        dataset: ParliamentActivityDataset,
        source_document_id: str,
        snapshot_id: str,
        actor_alias: str,
    ) -> None:
        after = {
            "source_document_id": source_document_id,
            "source_sha256": dataset.document_sha256,
            "normalised_sha256": _dataset_digest(dataset),
            "legislature": dataset.legislature,
            "parser_version": dataset.parser_version,
            "session_count": len(dataset.sessions),
            "initiative_count": len(dataset.initiatives),
            "vote_count": len(dataset.votes),
            "vote_record_count": sum(len(event.records) for event in dataset.votes),
            "publishable": False,
        }
        await connection.execute(
            """
            INSERT INTO audit_events
                (id, entity_type, entity_id, action, actor_alias,
                 before_json, after_json, reason, created_at)
            VALUES ($1, 'PARLIAMENT_ACTIVITY_SNAPSHOT', $2, 'INGESTED', $3,
                    NULL, $4::jsonb,
                    'Fotografia oficial preservada; publicação exige revisão humana', NOW())
            """,
            _new_id("audit", f"{snapshot_id}|INGESTED"),
            snapshot_id,
            actor_alias,
            json.dumps(after, ensure_ascii=False),
        )
