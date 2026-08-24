"""Arquivo privado de um único recurso parlamentar ainda não interpretado."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.official_index_staging import OfficialIndexItem
from app.repositories.parliament_resource_archive import (
    ParliamentResourceArchiveRepository,
    PrivateParliamentResourceCandidateProof,
)
from app.repositories.parliament_resource_manifest import require_official_index_snapshot_id
from app.services.http import OfficialHttpClient
from app.services.parliament_resource_manifest import (
    ParliamentResourceFormat,
    exact_parliament_resource_format,
    parliament_resource_manifest_source_name,
)
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    require_parliament_url,
    require_supported_parliament_legislature,
)

PARLIAMENT_RESOURCE_ARCHIVE_CODE_VERSION = "parliament-resource-archive-v1"
PARLIAMENT_RESOURCE_ARCHIVE_STATUS: Literal["ARCHIVED_UNPARSED"] = "ARCHIVED_UNPARSED"
PARLIAMENT_RESOURCE_ARCHIVE_COMPLETENESS: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


@dataclass(frozen=True, slots=True)
class CollectedParliamentResourceArchive:
    catalogue_kind: ParliamentCatalogueKind
    legislature: str
    resource_format: ParliamentResourceFormat
    parent_catalogue_snapshot_id: str
    parent_manifest_snapshot_id: str
    official_label: str
    requested_resource_url: HttpUrl
    source_name: str
    title: str
    source_url: HttpUrl
    content_sha256: str
    byte_size: int
    raw_document: PrivateRawDocument
    status: Literal["ARCHIVED_UNPARSED"] = PARLIAMENT_RESOURCE_ARCHIVE_STATUS
    historical_completeness: Literal["NOT_ASSERTED"] = PARLIAMENT_RESOURCE_ARCHIVE_COMPLETENESS
    publishable: bool = False
    records_normalised: int = 0
    editorial_cases_created: int = 0

    @property
    def private_category(self) -> str:
        return parliament_resource_archive_category(
            catalogue_kind=self.catalogue_kind,
            legislature=self.legislature,
            resource_format=self.resource_format,
            parent_manifest_snapshot_id=self.parent_manifest_snapshot_id,
        )


def parliament_resource_archive_source_name(
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
    resource_format: ParliamentResourceFormat,
) -> str:
    exact_legislature = require_supported_parliament_legislature(legislature)
    return (
        f"PARLIAMENT_RESOURCE_ARCHIVE_{catalogue_kind.value}_"
        f"{exact_legislature}_{resource_format.value}"
    )


def parliament_resource_archive_title(
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
    resource_format: ParliamentResourceFormat,
) -> str:
    exact_legislature = require_supported_parliament_legislature(legislature)
    return (
        "Assembleia da República — recurso parlamentar privado "
        f"{catalogue_kind.value.lower()} — {exact_legislature} — {resource_format.value}"
    )


def parliament_resource_archive_category(
    *,
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
    resource_format: ParliamentResourceFormat,
    parent_manifest_snapshot_id: str,
) -> str:
    return ":".join(
        (
            "PARLIAMENT_RESOURCE_ARCHIVE",
            catalogue_kind.value,
            require_supported_parliament_legislature(legislature),
            resource_format.value,
            PARLIAMENT_RESOURCE_ARCHIVE_STATUS,
            PARLIAMENT_RESOURCE_ARCHIVE_COMPLETENESS,
            f"PARENT={require_official_index_snapshot_id(parent_manifest_snapshot_id)}",
        )
    )


class ParliamentResourceArchiveCollector:
    """Descarrega um recurso já provado, sem interpretar o conteúdo."""

    def __init__(self, http: OfficialHttpClient, *, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("O limite do recurso parlamentar tem de ser positivo")
        self.http = http
        self.max_bytes = max_bytes

    async def collect(
        self,
        proof: PrivateParliamentResourceCandidateProof,
    ) -> CollectedParliamentResourceArchive:
        exact_legislature = require_supported_parliament_legislature(proof.legislature)
        require_official_index_snapshot_id(proof.parent_catalogue_snapshot_id)
        require_official_index_snapshot_id(proof.manifest_snapshot_id)
        requested_url = require_parliament_url(proof.resource_url)
        if (
            proof.source_name
            != parliament_resource_manifest_source_name(proof.catalogue_kind, exact_legislature)
            or not proof.manifest_archive_attested
            or proof.publishable
            or not proof.official_label.strip()
            or exact_parliament_resource_format(proof.official_label, requested_url)
            != proof.resource_format
        ):
            raise ValueError("A prova privada do recurso parlamentar é incoerente")
        response = await self.http.get(requested_url, max_bytes=self.max_bytes)
        effective_url = require_parliament_url(str(response.url))
        if effective_url != requested_url:
            raise ValueError("O URL efetivo do recurso diverge do manifesto parlamentar")
        mime_type = response.headers.get("content-type")
        normalised_mime_type = mime_type.split(";", 1)[0].strip().casefold() if mime_type else None
        if normalised_mime_type in {"text/html", "application/xhtml+xml"}:
            raise ValueError("O recurso parlamentar devolveu HTML em vez dos bytes inventariados")

        content = response.content
        retrieved_at = datetime.now(UTC)
        content_sha256 = hashlib.sha256(content).hexdigest()
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(effective_url),
            retrieved_at=retrieved_at,
            content_sha256=content_sha256,
            mime_type=mime_type,
            content=content,
        )
        return CollectedParliamentResourceArchive(
            catalogue_kind=proof.catalogue_kind,
            legislature=proof.legislature,
            resource_format=proof.resource_format,
            parent_catalogue_snapshot_id=proof.parent_catalogue_snapshot_id,
            parent_manifest_snapshot_id=proof.manifest_snapshot_id,
            official_label=proof.official_label,
            requested_resource_url=HttpUrl(requested_url),
            source_name=parliament_resource_archive_source_name(
                proof.catalogue_kind,
                proof.legislature,
                proof.resource_format,
            ),
            title=parliament_resource_archive_title(
                proof.catalogue_kind,
                proof.legislature,
                proof.resource_format,
            ),
            source_url=HttpUrl(effective_url),
            content_sha256=content_sha256,
            byte_size=len(content),
            raw_document=raw_document,
        )


class ParliamentResourceArchiveStager:
    """Persiste bytes privados só depois de repetir toda a cadeia de prova."""

    def __init__(
        self,
        settings: Settings,
        repository: ParliamentResourceArchiveRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def store(
        self,
        collection: CollectedParliamentResourceArchive,
        *,
        code_version: str = PARLIAMENT_RESOURCE_ARCHIVE_CODE_VERSION,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(
                "O arquivo parlamentar privado só pode ser persistido em test ou staging"
            )
        expected_source_name = parliament_resource_archive_source_name(
            collection.catalogue_kind,
            collection.legislature,
            collection.resource_format,
        )
        expected_title = parliament_resource_archive_title(
            collection.catalogue_kind,
            collection.legislature,
            collection.resource_format,
        )
        if collection.source_name != expected_source_name or collection.title != expected_title:
            raise ValueError("A identidade do arquivo parlamentar diverge do lote pedido")
        if (
            str(collection.requested_resource_url) != str(collection.source_url)
            or str(collection.source_url) != str(collection.raw_document.source_url)
            or collection.content_sha256 != collection.raw_document.content_sha256
            or collection.byte_size != len(collection.raw_document.content)
        ):
            raise ValueError("A prova do arquivo parlamentar diverge dos bytes recolhidos")
        if (
            collection.status != PARLIAMENT_RESOURCE_ARCHIVE_STATUS
            or collection.historical_completeness != PARLIAMENT_RESOURCE_ARCHIVE_COMPLETENESS
            or collection.publishable
            or collection.records_normalised
            or collection.editorial_cases_created
        ):
            raise ValueError("O arquivo parlamentar não pode normalizar, rever ou publicar")

        parent_proof = await self.repository.require_resource_candidate(
            catalogue_snapshot_id=collection.parent_catalogue_snapshot_id,
            manifest_snapshot_id=collection.parent_manifest_snapshot_id,
            catalogue_kind=collection.catalogue_kind,
            legislature=collection.legislature,
            resource_format=collection.resource_format,
            resource_url=str(collection.requested_resource_url),
        )
        if parent_proof.official_label != collection.official_label:
            raise ValueError("A etiqueta do recurso diverge do manifesto parlamentar")

        result = await self.repository.store_index(
            source_name=collection.source_name,
            publisher="PARLIAMENT",
            title=collection.title,
            raw_document=collection.raw_document,
            resources=[
                OfficialIndexItem(
                    title=collection.official_label,
                    url=str(collection.source_url),
                    category=collection.private_category,
                )
            ],
            code_version=code_version,
        )
        return {
            **result,
            "catalogue_kind": collection.catalogue_kind.value,
            "legislature": collection.legislature,
            "resource_format": collection.resource_format.value,
            "parent_catalogue_snapshot_id": parent_proof.parent_catalogue_snapshot_id,
            "parent_manifest_snapshot_id": parent_proof.manifest_snapshot_id,
            "parent_manifest_content_sha256": parent_proof.manifest_content_sha256,
            "byte_size": collection.byte_size,
            "resource_status": PARLIAMENT_RESOURCE_ARCHIVE_STATUS,
            "historical_completeness": PARLIAMENT_RESOURCE_ARCHIVE_COMPLETENESS,
            "records_normalised": 0,
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
