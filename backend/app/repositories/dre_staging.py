"""Persistência privada e append-only de documentos do Diário da República.

O módulo reutiliza SourceDocument, SourceArchiveAttestation e SyncRun. Nunca
escreve em Law, CitizenAlert ou noutra tabela pública; ingestão não é revisão.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.core.security import require_official_url, sha256_text
from app.models.api import LegalDocument
from app.models.archive import RawArchiveReceipt
from app.repositories.postgres import PostgresRepository

DRE_STAGING_ONLY_MESSAGE = (
    "A persistência DRE só é permitida em test/staging, com arquivo prévio dos "
    "bytes oficiais; ingestão não constitui revisão nem publicação."
)


def _stable_id(prefix: str, *parts: str) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:32]}"


def _database_timestamp(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _document_kind(document: LegalDocument) -> str:
    searchable = f"{document.official_identifier or ''} {document.title}".casefold()
    if any(token in searchable for token in ("portaria", "regulamento")):
        return "REGULATION"
    return "LAW"


def _validate_dre_staging_input(
    document: LegalDocument,
    *,
    archive_receipt: RawArchiveReceipt | None,
    code_version: str,
) -> None:
    if archive_receipt is None:
        raise ValueError("A persistência DRE exige arquivo prévio dos bytes oficiais")
    if not code_version.strip() or len(code_version) > 200:
        raise ValueError("A versão do parser DRE é inválida")
    if len(document.title.strip()) > 500:
        raise ValueError("O título DRE excede o limite seguro")
    if (
        document.official_identifier is not None
        and len(document.official_identifier.strip()) > 500
    ):
        raise ValueError("O identificador oficial DRE excede o limite seguro")
    if not 100 <= len(document.text) <= 5_000_000:
        raise ValueError("O texto jurídico DRE está vazio ou excede o limite seguro")
    if sha256_text(document.text) != document.normalised_text_sha256:
        raise ValueError("O hash do texto normalizado DRE é incoerente")
    effective_url = require_official_url(str(document.source_url))
    if archive_receipt.content_sha256 != document.content_sha256:
        raise ValueError("O recibo de arquivo não corresponde ao hash bruto DRE")
    if str(archive_receipt.source_url) != effective_url:
        raise ValueError("O recibo de arquivo não corresponde ao URL efetivo DRE")
    raw_document = document.raw_document
    if raw_document is None:
        raise ValueError("O documento DRE não transporta os bytes oficiais privados")
    if raw_document.content_sha256 != document.content_sha256:
        raise ValueError("Os bytes privados DRE não correspondem ao hash do documento")
    if (
        raw_document.retrieved_at.astimezone(UTC)
        != archive_receipt.retrieved_at.astimezone(UTC)
    ):
        raise ValueError("O recibo DRE não corresponde à data de recolha dos bytes")


class DreStagingRepository(PostgresRepository):
    """Repositório DRE que não cria projeções nem invoca promoção pública."""

    async def store_dre_document(
        self,
        document: LegalDocument,
        *,
        code_version: str,
        archive_receipt: RawArchiveReceipt | None = None,
    ) -> dict[str, Any]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(DRE_STAGING_ONLY_MESSAGE)
        _validate_dre_staging_input(
            document,
            archive_receipt=archive_receipt,
            code_version=code_version,
        )
        assert archive_receipt is not None
        assert document.raw_document is not None
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")

        kind = _document_kind(document)
        sync_id = await self._start_sync_run(
            source_name="DRE",
            dataset_url=str(document.source_url),
            code_version=code_version,
        )
        snapshot_created = False
        attestation: dict[str, Any] = {"created": False}
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                source_document_id = await self._ensure_source_document(
                    connection,
                    publisher="DRE",
                    kind=kind,
                    title=document.title,
                    url=str(document.source_url),
                    retrieved_at=document.raw_document.retrieved_at,
                    content_sha256=document.content_sha256,
                    mime_type=archive_receipt.mime_type,
                    parser_version=code_version,
                )
                attestation = await self._attest_source_archive(
                    connection,
                    source_document_id=source_document_id,
                    receipt=archive_receipt,
                    archived_by=f"sync:{code_version}",
                )
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"dre:{source_document_id}:{code_version}",
                )
                snapshot_id = _stable_id("dre_snapshot", source_document_id, code_version)
                inserted = await connection.fetchrow(
                    """
                    INSERT INTO dre_document_snapshots
                        (id, source_document_id, sync_run_id, official_identifier,
                         title, document_kind, published_at, parser_version,
                         normalised_text_sha256, extracted_text, text_length,
                         collected_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6::"DocumentKind", $7, $8,
                            $9, $10, $11, $12, NOW())
                    ON CONFLICT (source_document_id, parser_version) DO NOTHING
                    RETURNING id
                    """,
                    snapshot_id,
                    source_document_id,
                    sync_id,
                    document.official_identifier,
                    document.title,
                    kind,
                    _database_timestamp(document.published_at),
                    code_version,
                    document.normalised_text_sha256,
                    document.text,
                    len(document.text),
                    _database_timestamp(document.raw_document.retrieved_at),
                )
                snapshot_created = inserted is not None
                if not snapshot_created:
                    existing = await connection.fetchrow(
                        """
                        SELECT id, official_identifier, title, document_kind::text,
                               published_at, normalised_text_sha256, text_length
                        FROM dre_document_snapshots
                        WHERE source_document_id = $1 AND parser_version = $2
                        """,
                        source_document_id,
                        code_version,
                    )
                    if existing is None:
                        raise RuntimeError("O snapshot DRE não foi criado nem encontrado")
                    expected = {
                        "official_identifier": document.official_identifier,
                        "title": document.title,
                        "document_kind": kind,
                        "published_at": _database_timestamp(document.published_at),
                        "normalised_text_sha256": document.normalised_text_sha256,
                        "text_length": len(document.text),
                    }
                    observed = {key: existing[key] for key in expected}
                    if observed != expected:
                        raise ValueError(
                            "O snapshot DRE existente diverge da normalização atual; "
                            "é necessária uma nova versão do parser"
                        )
                    snapshot_id = str(existing["id"])
                else:
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'DRE_DOCUMENT_SNAPSHOT', $2,
                                'INGESTED_OFFICIAL_SNAPSHOT', $3, NULL, $4::jsonb,
                                'Snapshot DRE privado; sem revisão ou publicação', NOW())
                        """,
                        _stable_id("audit", snapshot_id, "ingested"),
                        snapshot_id,
                        f"sync:{code_version}",
                        json.dumps(
                            {
                                "source_document_id": source_document_id,
                                "archive_attestation_id": attestation["id"],
                                "official_identifier": document.official_identifier,
                                "document_kind": kind,
                                "normalised_text_sha256": document.normalised_text_sha256,
                                "text_length": len(document.text),
                                "publishable": False,
                            },
                            ensure_ascii=False,
                        ),
                    )

            await self._finish_sync_run(
                sync_id,
                status_value="SUCCEEDED",
                records_read=1,
                records_written=int(snapshot_created),
                warnings=[],
            )
        except Exception:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=1,
                records_written=0,
                warnings=[],
                error_message="Persistência DRE interrompida; os dados continuam indisponíveis",
            )
            raise

        return {
            "snapshot_id": snapshot_id,
            "snapshot_created": snapshot_created,
            "archive_attestation_created": bool(attestation["created"]),
            "document_kind": kind,
        }

    async def inspect_dre_staging(
        self,
        *,
        official_identifier: str | None = None,
    ) -> dict[str, Any]:
        """Devolve apenas metadados e verificações; nunca o texto jurídico."""
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT snapshot.id AS snapshot_id, snapshot.official_identifier,
                       snapshot.title, snapshot.document_kind::text,
                       snapshot.published_at, snapshot.parser_version,
                       snapshot.normalised_text_sha256, snapshot.text_length,
                       snapshot.collected_at, snapshot.created_at,
                       source.id AS source_document_id,
                       source.publisher::text AS source_publisher,
                       source.kind::text AS source_kind, source.url AS source_url,
                       source.retrieved_at, source.content_sha256, source.mime_type,
                       run.id AS sync_run_id, run.status::text AS sync_status,
                       run.started_at, run.finished_at, run.records_read,
                       run.records_written, run.code_version,
                       archive.id AS archive_attestation_id,
                       archive.storage_backend, archive.storage_key,
                       archive.content_sha256 AS archive_content_sha256,
                       archive.byte_size, archive.retrieval_url,
                       archive.retrieved_at AS archive_retrieved_at,
                       archive.archived_at
                FROM dre_document_snapshots snapshot
                JOIN source_documents source ON source.id = snapshot.source_document_id
                JOIN sync_runs run ON run.id = snapshot.sync_run_id
                JOIN LATERAL (
                    SELECT candidate.*
                    FROM source_archive_attestations candidate
                    WHERE candidate.source_document_id = source.id
                    ORDER BY candidate.archived_at DESC, candidate.id DESC
                    LIMIT 1
                ) archive ON TRUE
                WHERE ($1::text IS NULL OR snapshot.official_identifier = $1)
                  AND run.status = 'SUCCEEDED'
                  AND run.finished_at IS NOT NULL
                ORDER BY snapshot.collected_at DESC, snapshot.id DESC
                LIMIT 1
                """,
                official_identifier,
            )
        if row is None:
            raise ValueError("Não existe snapshot DRE persistido e concluído; dados indisponíveis")
        report = dict(row)
        report["checks"] = {
            "publisher_is_dre": row["source_publisher"] == "DRE",
            "kind_matches_snapshot": row["source_kind"] == row["document_kind"],
            "parser_matches_sync": row["parser_version"] == row["code_version"],
            "archive_hash_matches_source": (
                row["archive_content_sha256"] == row["content_sha256"]
            ),
            "archive_url_matches_source": row["retrieval_url"] == row["source_url"],
            "archive_retrieved_at_matches_source": (
                row["archive_retrieved_at"] == row["retrieved_at"]
            ),
            "sync_counts_are_coherent": (
                row["records_read"] == 1 and row["records_written"] in {0, 1}
            ),
        }
        report["publishable"] = False
        report["extracted_text_included"] = False
        return report
