"""Porta privada entre um catálogo parlamentar arquivado e o seu manifesto."""

import re
from dataclasses import dataclass

from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.parliament_source_catalogue import (
    PARLIAMENT_CATALOGUES,
    ParliamentCatalogueKind,
    parliament_legislature_label,
    parliament_source_candidate_category,
    require_parliament_url,
    require_supported_parliament_legislature,
)

_SNAPSHOT_ID = re.compile(r"^official_index_[0-9a-f]{32}$")


def require_official_index_snapshot_id(value: str) -> str:
    if _SNAPSHOT_ID.fullmatch(value) is None:
        raise ValueError("Identificador de fotografia de catálogo inválido")
    return value


@dataclass(frozen=True, slots=True)
class PrivateParliamentCatalogueCandidateProof:
    snapshot_id: str
    source_document_id: str
    source_name: str
    catalogue_kind: ParliamentCatalogueKind
    legislature: str
    official_label: str
    candidate_url: str
    catalogue_source_url: str
    catalogue_content_sha256: str
    archive_attested: bool
    publishable: bool = False


class ParliamentResourceManifestRepository(OfficialIndexStagingRepository):
    """Exige um candidato exato e atestado antes de criar outro índice privado."""

    async def require_catalogue_candidate(
        self,
        *,
        snapshot_id: str,
        catalogue_kind: ParliamentCatalogueKind,
        legislature: str,
        candidate_url: str,
    ) -> PrivateParliamentCatalogueCandidateProof:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        exact_snapshot_id = require_official_index_snapshot_id(snapshot_id)

        exact_legislature = require_supported_parliament_legislature(legislature)
        exact_candidate_url = require_parliament_url(candidate_url)
        expected_source_name = PARLIAMENT_CATALOGUES[catalogue_kind].source_name
        expected_label = parliament_legislature_label(exact_legislature)
        expected_category = parliament_source_candidate_category(
            catalogue_kind,
            exact_legislature,
        )

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT snapshot.id AS snapshot_id,
                       snapshot.source_document_id,
                       snapshot.source_name,
                       snapshot.publisher::text AS publisher,
                       snapshot.publishable,
                       resource.title AS official_label,
                       resource.category,
                       resource.url AS candidate_url,
                       source.url AS catalogue_source_url,
                       source.content_sha256 AS catalogue_content_sha256,
                       EXISTS (
                           SELECT 1
                           FROM source_archive_attestations AS archive
                           WHERE archive.source_document_id = source.id
                             AND archive.retrieval_url = source.url
                             AND archive.content_sha256 = source.content_sha256
                       ) AS archive_attested
                FROM official_index_snapshots AS snapshot
                JOIN official_index_resources AS resource
                  ON resource.snapshot_id = snapshot.id
                JOIN source_documents AS source
                  ON source.id = snapshot.source_document_id
                WHERE snapshot.id = $1
                  AND resource.url = $2
                """,
                exact_snapshot_id,
                exact_candidate_url,
            )

        if row is None:
            raise LookupError("Candidato parlamentar exato não encontrado no catálogo privado")
        if (
            str(row["source_name"]) != expected_source_name
            or str(row["publisher"]) != "PARLIAMENT"
            or bool(row["publishable"])
            or str(row["official_label"]) != expected_label
            or str(row["category"]) != expected_category
            or not bool(row["archive_attested"])
        ):
            raise ValueError("O candidato parlamentar não cumpre a prova privada do catálogo")

        return PrivateParliamentCatalogueCandidateProof(
            snapshot_id=str(row["snapshot_id"]),
            source_document_id=str(row["source_document_id"]),
            source_name=str(row["source_name"]),
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            official_label=str(row["official_label"]),
            candidate_url=str(row["candidate_url"]),
            catalogue_source_url=str(row["catalogue_source_url"]),
            catalogue_content_sha256=str(row["catalogue_content_sha256"]),
            archive_attested=True,
        )
