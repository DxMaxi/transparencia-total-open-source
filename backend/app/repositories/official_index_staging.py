"""Persistência privada e append-only de índices oficiais da V4."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.archive import PrivateRawDocument, RawArchiveReceipt
from app.repositories.postgres import PostgresRepository


@dataclass(frozen=True, slots=True)
class OfficialIndexItem:
    title: str
    url: str
    category: str | None = None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class OfficialIndexStagingRepository(PostgresRepository):
    """Guarda bytes e metadados sem criar qualquer projecção pública."""

    async def record_failed_index_refresh(
        self,
        *,
        source_name: str,
        dataset_url: str,
        code_version: str,
        error_message: str,
    ) -> str:
        """Regista uma recolha falhada, mesmo sem bytes disponíveis para arquivar."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if not source_name.strip() or len(source_name) > 100:
            raise ValueError("Nome da fonte inválido")

        sync_id = await self._start_sync_run(
            source_name=source_name,
            dataset_url=dataset_url,
            code_version=code_version,
        )
        await self._finish_sync_run(
            sync_id,
            status_value="FAILED",
            records_read=0,
            records_written=0,
            warnings=[],
            error_message=error_message[:2_000],
        )
        return sync_id

    async def archive_raw_document(
        self,
        *,
        raw_document: PrivateRawDocument,
    ) -> RawArchiveReceipt:
        """Preserva bytes oficiais em PostgreSQL sem os tornar publicáveis."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        observed_hash = hashlib.sha256(raw_document.content).hexdigest()
        if observed_hash != raw_document.content_sha256:
            raise ValueError("Os bytes recolhidos não correspondem ao SHA-256 declarado")

        storage_key = f"sha256/{raw_document.content_sha256[:2]}/{raw_document.content_sha256}"
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"raw-source-object:{raw_document.content_sha256}",
            )
            inserted_object = await connection.fetchval(
                """
                INSERT INTO raw_source_objects
                    (storage_key, content_sha256, byte_size, mime_type, content)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (storage_key) DO NOTHING
                RETURNING storage_key
                """,
                storage_key,
                raw_document.content_sha256,
                len(raw_document.content),
                raw_document.mime_type,
                raw_document.content,
            )
            existing = await connection.fetchrow(
                """
                SELECT content_sha256, byte_size, content
                FROM raw_source_objects
                WHERE storage_key = $1
                """,
                storage_key,
            )
            if existing is None:
                raise RuntimeError("O objecto bruto não foi criado nem encontrado")
            archived_bytes = bytes(existing["content"])
            if (
                hashlib.sha256(archived_bytes).hexdigest() != raw_document.content_sha256
                or str(existing["content_sha256"]) != raw_document.content_sha256
                or int(existing["byte_size"]) != len(raw_document.content)
                or archived_bytes != raw_document.content
            ):
                raise ValueError("O objecto bruto existente diverge dos bytes oficiais recolhidos")

        return RawArchiveReceipt(
            storage_backend="POSTGRES",
            storage_key=storage_key,
            content_sha256=raw_document.content_sha256,
            byte_size=len(raw_document.content),
            mime_type=raw_document.mime_type,
            source_url=raw_document.source_url,
            retrieved_at=raw_document.retrieved_at,
            recorded_at=datetime.now(UTC),
            object_created=inserted_object is not None,
        )

    async def attest_existing_source_bytes(
        self,
        *,
        source_document_id: str,
        raw_document: PrivateRawDocument,
        archived_by: str,
    ) -> dict[str, object]:
        """Reconstitui o arquivo apenas com bytes que coincidam com a fonte persistida."""

        receipt = await self.archive_raw_document(raw_document=raw_document)
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")

        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"source-archive-reattestation:{source_document_id}",
            )
            source = await connection.fetchrow(
                """
                SELECT id, url, content_sha256
                FROM source_documents
                WHERE id = $1
                FOR SHARE
                """,
                source_document_id,
            )
            if source is None:
                raise ValueError("Documento-fonte não encontrado")
            source_url = str(source["url"])
            source_sha256 = str(source["content_sha256"])
            if str(raw_document.source_url) != source_url:
                raise ValueError("A URL final reobtida diverge do documento-fonte persistido")
            if raw_document.content_sha256 != source_sha256:
                raise ValueError("O documento oficial actual diverge do snapshot persistido")

            attestation = await self._attest_source_archive(
                connection,
                source_document_id=source_document_id,
                receipt=receipt,
                archived_by=archived_by,
            )

        return {
            "source_document_id": source_document_id,
            "storage_key": receipt.storage_key,
            "content_sha256": source_sha256,
            "byte_size": receipt.byte_size,
            "object_created": receipt.object_created,
            "attestation_created": bool(attestation["created"]),
            "publishable": False,
        }

    async def store_index(
        self,
        *,
        source_name: str,
        publisher: str,
        title: str,
        raw_document: PrivateRawDocument,
        resources: list[OfficialIndexItem],
        code_version: str,
    ) -> dict[str, object]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if not source_name.strip() or len(source_name) > 100:
            raise ValueError("Nome da fonte inválido")

        sync_id = await self._start_sync_run(
            source_name=source_name,
            dataset_url=str(raw_document.source_url),
            code_version=code_version,
        )
        storage_key = f"sha256/{raw_document.content_sha256[:2]}/{raw_document.content_sha256}"
        unique_resources = {item.url: item for item in resources}
        ordered_resources = sorted(
            unique_resources.values(), key=lambda item: (item.title.casefold(), item.url)
        )

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"official-index:{source_name}",
                )
                inserted_object = await connection.fetchval(
                    """
                    INSERT INTO raw_source_objects
                        (storage_key, content_sha256, byte_size, mime_type, content)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (storage_key) DO NOTHING
                    RETURNING storage_key
                    """,
                    storage_key,
                    raw_document.content_sha256,
                    len(raw_document.content),
                    raw_document.mime_type,
                    raw_document.content,
                )
                existing = await connection.fetchrow(
                    """
                    SELECT content_sha256, byte_size, content
                    FROM raw_source_objects
                    WHERE storage_key = $1
                    """,
                    storage_key,
                )
                if existing is None:
                    raise RuntimeError("O objecto bruto não foi criado nem encontrado")
                observed_hash = hashlib.sha256(bytes(existing["content"])).hexdigest()
                if observed_hash != raw_document.content_sha256 or int(
                    existing["byte_size"]
                ) != len(raw_document.content):
                    raise ValueError("O objecto bruto existente diverge dos bytes recolhidos")

                source_document_id = await self._ensure_source_document(
                    connection,
                    publisher=publisher,
                    kind="OPEN_DATASET",
                    title=title,
                    url=str(raw_document.source_url),
                    retrieved_at=raw_document.retrieved_at,
                    content_sha256=raw_document.content_sha256,
                    mime_type=raw_document.mime_type,
                    parser_version=code_version,
                )
                receipt = RawArchiveReceipt(
                    storage_backend="POSTGRES",
                    storage_key=storage_key,
                    content_sha256=raw_document.content_sha256,
                    byte_size=len(raw_document.content),
                    mime_type=raw_document.mime_type,
                    source_url=raw_document.source_url,
                    retrieved_at=raw_document.retrieved_at,
                    recorded_at=datetime.now(UTC),
                    object_created=inserted_object is not None,
                )
                attestation = await self._attest_source_archive(
                    connection,
                    source_document_id=source_document_id,
                    receipt=receipt,
                    archived_by=f"sync:{code_version}",
                )

                existing_snapshot = await connection.fetchrow(
                    """
                    SELECT id, resource_count
                    FROM official_index_snapshots
                    WHERE source_document_id = $1
                    """,
                    source_document_id,
                )
                snapshot_created = existing_snapshot is None
                if existing_snapshot is None:
                    snapshot_id = _new_id("official_index")
                    await connection.execute(
                        """
                        INSERT INTO official_index_snapshots
                            (id, source_document_id, sync_run_id, source_name,
                             publisher, collected_at, resource_count, publishable)
                        VALUES ($1, $2, $3, $4, $5::"SourcePublisher", $6, $7, FALSE)
                        """,
                        snapshot_id,
                        source_document_id,
                        sync_id,
                        source_name,
                        publisher,
                        raw_document.retrieved_at.replace(tzinfo=None),
                        len(ordered_resources),
                    )
                    await connection.executemany(
                        """
                        INSERT INTO official_index_resources
                            (id, snapshot_id, ordinal, title, category, url)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        [
                            (
                                _new_id("official_resource"),
                                snapshot_id,
                                ordinal,
                                item.title[:500],
                                item.category[:500] if item.category else None,
                                item.url,
                            )
                            for ordinal, item in enumerate(ordered_resources)
                        ],
                    )
                else:
                    snapshot_id = str(existing_snapshot["id"])
                    if int(existing_snapshot["resource_count"]) != len(ordered_resources):
                        raise ValueError("O snapshot existente diverge da recolha com o mesmo hash")

                await connection.execute(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, 'OFFICIAL_INDEX_SNAPSHOT', $2, 'INGESTED', $3,
                            NULL, $4::jsonb,
                            'Índice oficial preservado sem autorização de publicação', NOW())
                    """,
                    _new_id("audit"),
                    snapshot_id,
                    f"sync:{code_version}",
                    json.dumps(
                        {
                            "source_name": source_name,
                            "content_sha256": raw_document.content_sha256,
                            "resource_count": len(ordered_resources),
                            "publishable": False,
                        },
                        ensure_ascii=False,
                    ),
                )

            await self._finish_sync_run(
                sync_id,
                status_value="SUCCEEDED",
                records_read=len(ordered_resources),
                records_written=len(ordered_resources) if snapshot_created else 0,
                warnings=[],
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=len(ordered_resources),
                records_written=0,
                warnings=[],
                error_message=str(exc),
            )
            raise

        return {
            "source_name": source_name,
            "source_document_id": source_document_id,
            "snapshot_id": snapshot_id,
            "content_sha256": raw_document.content_sha256,
            "resource_count": len(ordered_resources),
            "object_created": inserted_object is not None,
            "attestation_created": bool(attestation["created"]),
            "snapshot_created": snapshot_created,
            "publishable": False,
        }
