"""Porta privada entre um manifesto parlamentar e o arquivo de um recurso."""

from dataclasses import dataclass

from app.repositories.parliament_resource_manifest import (
    ParliamentResourceManifestRepository,
    require_official_index_snapshot_id,
)
from app.services.parliament_resource_manifest import (
    ParliamentResourceFormat,
    parliament_resource_candidate_category,
    parliament_resource_manifest_source_name,
)
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    require_parliament_url,
    require_supported_parliament_legislature,
)


@dataclass(frozen=True, slots=True)
class PrivateParliamentResourceCandidateProof:
    manifest_snapshot_id: str
    manifest_source_document_id: str
    parent_catalogue_snapshot_id: str
    source_name: str
    catalogue_kind: ParliamentCatalogueKind
    legislature: str
    resource_format: ParliamentResourceFormat
    official_label: str
    resource_url: str
    manifest_source_url: str
    manifest_content_sha256: str
    manifest_archive_attested: bool
    catalogue_content_sha256: str
    publishable: bool = False


class ParliamentResourceArchiveRepository(ParliamentResourceManifestRepository):
    """Exige a cadeia catálogo-manifesto antes de arquivar um único ficheiro."""

    async def require_resource_candidate(
        self,
        *,
        catalogue_snapshot_id: str,
        manifest_snapshot_id: str,
        catalogue_kind: ParliamentCatalogueKind,
        legislature: str,
        resource_format: ParliamentResourceFormat,
        resource_url: str,
    ) -> PrivateParliamentResourceCandidateProof:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        exact_catalogue_snapshot_id = require_official_index_snapshot_id(catalogue_snapshot_id)
        exact_manifest_snapshot_id = require_official_index_snapshot_id(manifest_snapshot_id)
        exact_legislature = require_supported_parliament_legislature(legislature)
        exact_resource_url = require_parliament_url(resource_url)
        expected_source_name = parliament_resource_manifest_source_name(
            catalogue_kind,
            exact_legislature,
        )
        expected_category = parliament_resource_candidate_category(
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            resource_format=resource_format,
            parent_catalogue_snapshot_id=exact_catalogue_snapshot_id,
        )

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT snapshot.id AS manifest_snapshot_id,
                       snapshot.source_document_id AS manifest_source_document_id,
                       snapshot.source_name,
                       snapshot.publisher::text AS snapshot_publisher,
                       snapshot.parser_version AS snapshot_parser_version,
                       snapshot.publishable,
                       resource.title AS official_label,
                       resource.category,
                       resource.url AS resource_url,
                       source.url AS manifest_source_url,
                       source.content_sha256 AS manifest_content_sha256,
                       EXISTS (
                           SELECT 1
                           FROM source_archive_attestations AS archive
                           WHERE archive.source_document_id = source.id
                             AND archive.retrieval_url = source.url
                             AND archive.content_sha256 = source.content_sha256
                       ) AS manifest_archive_attested
                FROM official_index_snapshots AS snapshot
                JOIN official_index_resources AS resource
                  ON resource.snapshot_id = snapshot.id
                JOIN source_documents AS source
                  ON source.id = snapshot.source_document_id
                WHERE snapshot.id = $1
                  AND resource.url = $2
                """,
                exact_manifest_snapshot_id,
                exact_resource_url,
            )

        if row is None:
            raise LookupError("Recurso parlamentar exato não encontrado no manifesto privado")
        snapshot_parser_version = str(row["snapshot_parser_version"])
        if (
            str(row["source_name"]) != expected_source_name
            or str(row["snapshot_publisher"]) != "PARLIAMENT"
            or bool(row["publishable"])
            or str(row["category"]) != expected_category
            or not snapshot_parser_version.startswith("parliament-resource-manifest-")
            or not bool(row["manifest_archive_attested"])
        ):
            raise ValueError("O recurso parlamentar não cumpre a prova privada do manifesto")

        catalogue_proof = await self.require_catalogue_candidate(
            snapshot_id=exact_catalogue_snapshot_id,
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            candidate_url=str(row["manifest_source_url"]),
        )
        return PrivateParliamentResourceCandidateProof(
            manifest_snapshot_id=str(row["manifest_snapshot_id"]),
            manifest_source_document_id=str(row["manifest_source_document_id"]),
            parent_catalogue_snapshot_id=exact_catalogue_snapshot_id,
            source_name=str(row["source_name"]),
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            resource_format=resource_format,
            official_label=str(row["official_label"]),
            resource_url=str(row["resource_url"]),
            manifest_source_url=str(row["manifest_source_url"]),
            manifest_content_sha256=str(row["manifest_content_sha256"]),
            manifest_archive_attested=True,
            catalogue_content_sha256=catalogue_proof.catalogue_content_sha256,
        )
