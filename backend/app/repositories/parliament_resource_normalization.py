"""Prova e persistência privada de um recurso parlamentar já arquivado."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.archive import PrivateRawDocument
from app.models.parliamentary import ParliamentActivityDataset
from app.repositories.parliament_activity import ParliamentActivityRepository
from app.repositories.parliament_resource_archive import ParliamentResourceArchiveRepository
from app.repositories.parliament_resource_manifest import require_official_index_snapshot_id
from app.services.parliament_resource_archive import (
    parliament_resource_archive_category,
    parliament_resource_archive_source_name,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    require_parliament_url,
    require_supported_parliament_legislature,
)

PARLIAMENT_HISTORICAL_INITIATIVES_PARSER_VERSION = "parliament-historical-initiatives-v1"
PARLIAMENT_HISTORICAL_INITIATIVES_SOURCE_NAME = "PARLIAMENT_HISTORICAL_INITIATIVES"
PARLIAMENT_HISTORICAL_VOTES_PARSER_VERSION = "parliament-historical-votes-v2"
PARLIAMENT_HISTORICAL_VOTES_SOURCE_NAME = "PARLIAMENT_HISTORICAL_VOTES"


@dataclass(frozen=True, slots=True)
class PrivateParliamentArchivedResourceProof:
    archive_snapshot_id: str
    archive_source_document_id: str
    parent_manifest_snapshot_id: str
    parent_catalogue_snapshot_id: str
    catalogue_kind: ParliamentCatalogueKind
    legislature: str
    resource_format: ParliamentResourceFormat
    official_label: str
    resource_url: str
    content_sha256: str
    byte_size: int
    raw_document: PrivateRawDocument
    manifest_content_sha256: str
    catalogue_content_sha256: str
    archive_attested: bool
    publishable: bool = False


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ParliamentResourceNormalizationRepository(ParliamentResourceArchiveRepository):
    """Lê bytes atestados e acrescenta uma fotografia normalizada não publicável."""

    async def require_archived_resource(
        self,
        *,
        catalogue_snapshot_id: str,
        manifest_snapshot_id: str,
        archive_snapshot_id: str,
        catalogue_kind: ParliamentCatalogueKind,
        legislature: str,
        resource_format: ParliamentResourceFormat,
        resource_url: str,
    ) -> PrivateParliamentArchivedResourceProof:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        exact_catalogue_snapshot_id = require_official_index_snapshot_id(catalogue_snapshot_id)
        exact_manifest_snapshot_id = require_official_index_snapshot_id(manifest_snapshot_id)
        exact_archive_snapshot_id = require_official_index_snapshot_id(archive_snapshot_id)
        exact_legislature = require_supported_parliament_legislature(legislature)
        exact_resource_url = require_parliament_url(resource_url)
        expected_source_name = parliament_resource_archive_source_name(
            catalogue_kind,
            exact_legislature,
            resource_format,
        )
        expected_category = parliament_resource_archive_category(
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            resource_format=resource_format,
            parent_manifest_snapshot_id=exact_manifest_snapshot_id,
        )

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT snapshot.id AS archive_snapshot_id,
                       snapshot.source_document_id AS archive_source_document_id,
                       snapshot.source_name,
                       snapshot.publisher::text AS publisher,
                       snapshot.parser_version,
                       snapshot.publishable,
                       resource.title AS official_label,
                       resource.category,
                       resource.url AS resource_url,
                       source.url AS source_url,
                       source.retrieved_at,
                       source.content_sha256,
                       source.mime_type,
                       archive.storage_backend,
                       archive.storage_key,
                       archive.retrieval_url,
                       archive.content_sha256 AS archive_content_sha256,
                       archive.byte_size AS archive_byte_size,
                       raw.content_sha256 AS raw_content_sha256,
                       raw.byte_size AS raw_byte_size,
                       raw.content AS raw_content
                FROM official_index_snapshots AS snapshot
                JOIN official_index_resources AS resource
                  ON resource.snapshot_id = snapshot.id
                JOIN source_documents AS source
                  ON source.id = snapshot.source_document_id
                JOIN source_archive_attestations AS archive
                  ON archive.source_document_id = source.id
                 AND archive.retrieval_url = source.url
                 AND archive.content_sha256 = source.content_sha256
                 AND archive.storage_backend = 'POSTGRES'
                JOIN raw_source_objects AS raw
                  ON raw.storage_key = archive.storage_key
                 AND raw.content_sha256 = archive.content_sha256
                WHERE snapshot.id = $1
                  AND resource.url = $2
                ORDER BY archive.archived_at DESC, archive.id DESC
                LIMIT 1
                """,
                exact_archive_snapshot_id,
                exact_resource_url,
            )

        if row is None:
            raise LookupError("Recurso parlamentar arquivado não encontrado com prova PostgreSQL")
        parser_version = str(row["parser_version"])
        raw_content = bytes(row["raw_content"])
        observed_sha256 = hashlib.sha256(raw_content).hexdigest()
        content_sha256 = str(row["content_sha256"])
        expected_storage_key = f"sha256/{content_sha256[:2]}/{content_sha256}"
        if (
            str(row["source_name"]) != expected_source_name
            or str(row["publisher"]) != "PARLIAMENT"
            or bool(row["publishable"])
            or str(row["category"]) != expected_category
            or not parser_version.startswith("parliament-resource-archive-")
            or str(row["resource_url"]) != exact_resource_url
            or str(row["source_url"]) != exact_resource_url
            or str(row["retrieval_url"]) != exact_resource_url
            or str(row["storage_backend"]) != "POSTGRES"
            or str(row["storage_key"]) != expected_storage_key
            or str(row["archive_content_sha256"]) != content_sha256
            or str(row["raw_content_sha256"]) != content_sha256
            or observed_sha256 != content_sha256
            or int(row["archive_byte_size"]) != len(raw_content)
            or int(row["raw_byte_size"]) != len(raw_content)
        ):
            raise ValueError("O recurso parlamentar arquivado não cumpre a cadeia privada")

        parent_proof = await self.require_resource_candidate(
            catalogue_snapshot_id=exact_catalogue_snapshot_id,
            manifest_snapshot_id=exact_manifest_snapshot_id,
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            resource_format=resource_format,
            resource_url=exact_resource_url,
        )
        raw_document = PrivateRawDocument(
            source_url=exact_resource_url,
            retrieved_at=_utc(row["retrieved_at"]),
            content_sha256=content_sha256,
            mime_type=str(row["mime_type"]) if row["mime_type"] is not None else None,
            content=raw_content,
        )
        return PrivateParliamentArchivedResourceProof(
            archive_snapshot_id=exact_archive_snapshot_id,
            archive_source_document_id=str(row["archive_source_document_id"]),
            parent_manifest_snapshot_id=exact_manifest_snapshot_id,
            parent_catalogue_snapshot_id=exact_catalogue_snapshot_id,
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            resource_format=resource_format,
            official_label=str(row["official_label"]),
            resource_url=exact_resource_url,
            content_sha256=content_sha256,
            byte_size=len(raw_content),
            raw_document=raw_document,
            manifest_content_sha256=parent_proof.manifest_content_sha256,
            catalogue_content_sha256=parent_proof.catalogue_content_sha256,
            archive_attested=True,
        )

    async def persist_private_initiatives(
        self,
        dataset: ParliamentActivityDataset,
    ) -> dict[str, object]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if dataset.parser_version != PARLIAMENT_HISTORICAL_INITIATIVES_PARSER_VERSION:
            raise ValueError("Versão do normalizador histórico parlamentar inválida")
        if dataset.sessions or dataset.votes or not dataset.initiatives:
            raise ValueError("O lote histórico privado só pode conter iniciativas")

        sync_id = await self._start_sync_run(
            source_name=PARLIAMENT_HISTORICAL_INITIATIVES_SOURCE_NAME,
            dataset_url=str(dataset.dataset_url),
            code_version=dataset.parser_version,
        )
        try:
            result = await ParliamentActivityRepository(self.pool).persist(
                dataset,
                archived_by=dataset.parser_version,
            )
            await self._finish_sync_run(
                sync_id,
                status_value="PARTIAL",
                records_read=len(dataset.initiatives),
                records_written=result.initiatives_written,
                warnings=list(dataset.warnings),
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=len(dataset.initiatives),
                records_written=0,
                warnings=list(dataset.warnings),
                error_message=str(exc),
            )
            raise

        return {
            "sync_run_id": sync_id,
            "source_document_id": result.source_document_id,
            "normalised_snapshot_id": result.snapshot_id,
            "snapshot_created": result.snapshot_created,
            "initiative_count": len(dataset.initiatives),
            "initiatives_written": result.initiatives_written,
            "sync_status": "PARTIAL",
            "publishable": False,
        }

    async def persist_private_votes(
        self,
        dataset: ParliamentActivityDataset,
    ) -> dict[str, object]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if dataset.parser_version != PARLIAMENT_HISTORICAL_VOTES_PARSER_VERSION:
            raise ValueError("Versão do normalizador histórico de votações inválida")
        if dataset.sessions or dataset.initiatives or not dataset.votes:
            raise ValueError("O lote histórico privado só pode conter votações")

        vote_record_count = sum(len(event.records) for event in dataset.votes)
        records_read = len(dataset.votes) + vote_record_count
        sync_id = await self._start_sync_run(
            source_name=PARLIAMENT_HISTORICAL_VOTES_SOURCE_NAME,
            dataset_url=str(dataset.dataset_url),
            code_version=dataset.parser_version,
        )
        try:
            result = await ParliamentActivityRepository(self.pool).persist(
                dataset,
                archived_by=dataset.parser_version,
            )
            records_written = result.vote_events_written + result.vote_records_written
            await self._finish_sync_run(
                sync_id,
                status_value="PARTIAL",
                records_read=records_read,
                records_written=records_written,
                warnings=list(dataset.warnings),
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=records_read,
                records_written=0,
                warnings=list(dataset.warnings),
                error_message=str(exc),
            )
            raise

        return {
            "sync_run_id": sync_id,
            "source_document_id": result.source_document_id,
            "normalised_snapshot_id": result.snapshot_id,
            "snapshot_created": result.snapshot_created,
            "vote_count": len(dataset.votes),
            "vote_record_count": vote_record_count,
            "votes_written": result.vote_events_written,
            "vote_records_written": result.vote_records_written,
            "sync_status": "PARTIAL",
            "publishable": False,
        }
