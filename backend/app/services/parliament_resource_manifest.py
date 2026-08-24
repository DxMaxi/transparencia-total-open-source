"""Manifesto privado de ficheiros parlamentares descobertos num candidato exato."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.official_index_staging import OfficialIndexItem
from app.repositories.parliament_resource_manifest import (
    ParliamentResourceManifestRepository,
    require_official_index_snapshot_id,
)
from app.services.http import OfficialHttpClient
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    require_parliament_url,
    require_supported_parliament_legislature,
)

PARLIAMENT_RESOURCE_MANIFEST_CODE_VERSION = "parliament-resource-manifest-v1"
PARLIAMENT_RESOURCE_STATUS: Literal["PENDING_DOWNLOAD"] = "PENDING_DOWNLOAD"
PARLIAMENT_RESOURCE_COMPLETENESS: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"

_JSON_RESOURCE_NAME = re.compile(r"(?:\.json(?:\.txt)?|_json\.txt)$", re.IGNORECASE)
_XML_RESOURCE_NAME = re.compile(r"\.xml$", re.IGNORECASE)


class ParliamentResourceFormat(StrEnum):
    JSON = "JSON"
    XML = "XML"


@dataclass(frozen=True, slots=True)
class ParliamentResourceCandidate:
    catalogue_kind: ParliamentCatalogueKind
    legislature: str
    official_label: str
    url: HttpUrl
    resource_format: ParliamentResourceFormat
    parent_catalogue_snapshot_id: str
    status: Literal["PENDING_DOWNLOAD"] = PARLIAMENT_RESOURCE_STATUS
    historical_completeness: Literal["NOT_ASSERTED"] = PARLIAMENT_RESOURCE_COMPLETENESS
    publishable: bool = False

    @property
    def private_category(self) -> str:
        return parliament_resource_candidate_category(
            catalogue_kind=self.catalogue_kind,
            legislature=self.legislature,
            resource_format=self.resource_format,
            parent_catalogue_snapshot_id=self.parent_catalogue_snapshot_id,
        )


@dataclass(frozen=True, slots=True)
class CollectedParliamentResourceManifest:
    catalogue_kind: ParliamentCatalogueKind
    legislature: str
    parent_catalogue_snapshot_id: str
    requested_candidate_url: HttpUrl
    source_name: str
    title: str
    source_url: HttpUrl
    content_sha256: str
    raw_document: PrivateRawDocument
    resources: tuple[ParliamentResourceCandidate, ...]
    publishable: bool = False
    editorial_cases_created: int = 0


def parliament_resource_manifest_source_name(
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
) -> str:
    exact_legislature = require_supported_parliament_legislature(legislature)
    return f"PARLIAMENT_RESOURCE_MANIFEST_{catalogue_kind.value}_{exact_legislature}"


def parliament_resource_manifest_title(
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
) -> str:
    exact_legislature = require_supported_parliament_legislature(legislature)
    return (
        "Assembleia da República — manifesto privado "
        f"{catalogue_kind.value.lower()} — {exact_legislature}"
    )


def parliament_resource_candidate_category(
    *,
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
    resource_format: ParliamentResourceFormat,
    parent_catalogue_snapshot_id: str,
) -> str:
    return ":".join(
        (
            "PARLIAMENT_RESOURCE_CANDIDATE",
            catalogue_kind.value,
            require_supported_parliament_legislature(legislature),
            resource_format.value,
            PARLIAMENT_RESOURCE_STATUS,
            PARLIAMENT_RESOURCE_COMPLETENESS,
            f"PARENT={require_official_index_snapshot_id(parent_catalogue_snapshot_id)}",
        )
    )


def _format_from_name(value: str) -> ParliamentResourceFormat | None:
    name = unquote(value).strip()
    if _JSON_RESOURCE_NAME.search(name):
        return ParliamentResourceFormat.JSON
    if _XML_RESOURCE_NAME.search(name):
        return ParliamentResourceFormat.XML
    return None


def exact_parliament_resource_format(
    label: str,
    href: str,
) -> ParliamentResourceFormat | None:
    parsed = urlparse(href)
    href_names = [unquote(parsed.path.rsplit("/", 1)[-1])]
    for key, values in parse_qs(parsed.query).items():
        if key.casefold() in {"fich", "file", "filename"}:
            href_names.extend(values)

    href_formats = {item for name in href_names if (item := _format_from_name(name)) is not None}
    if len(href_formats) == 1:
        return next(iter(href_formats))
    if href_formats:
        return None
    return _format_from_name(label)


class ParliamentResourceManifestCollector:
    """Arquiva uma pasta oficial e inventaria só ligações XML/JSON inequívocas."""

    def __init__(self, http: OfficialHttpClient) -> None:
        self.http = http

    async def collect(
        self,
        *,
        catalogue_kind: ParliamentCatalogueKind,
        legislature: str,
        parent_catalogue_snapshot_id: str,
        candidate_url: str,
    ) -> CollectedParliamentResourceManifest:
        exact_legislature = require_supported_parliament_legislature(legislature)
        exact_snapshot_id = require_official_index_snapshot_id(parent_catalogue_snapshot_id)
        requested_url = require_parliament_url(candidate_url)
        response = await self.http.get(requested_url)
        effective_url = require_parliament_url(str(response.url))
        if effective_url != requested_url:
            raise ValueError("O URL efetivo da pasta diverge do candidato parlamentar arquivado")
        content = response.content
        mime_type = response.headers.get("content-type")
        if not mime_type or mime_type.split(";", 1)[0].strip().casefold() != "text/html":
            raise ValueError("A pasta parlamentar oficial não devolveu HTML")

        retrieved_at = datetime.now(UTC)
        content_sha256 = hashlib.sha256(content).hexdigest()
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(effective_url),
            retrieved_at=retrieved_at,
            content_sha256=content_sha256,
            mime_type=mime_type,
            content=content,
        )
        soup = BeautifulSoup(content, "html.parser")
        resources_by_url: dict[str, ParliamentResourceCandidate] = {}
        for anchor in soup.find_all("a", href=True):
            official_label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            resource_url = urljoin(effective_url, str(anchor["href"]))
            resource_format = exact_parliament_resource_format(official_label, resource_url)
            if not official_label or resource_format is None:
                continue
            try:
                require_parliament_url(resource_url)
            except ValueError:
                continue
            resources_by_url.setdefault(
                resource_url,
                ParliamentResourceCandidate(
                    catalogue_kind=catalogue_kind,
                    legislature=exact_legislature,
                    official_label=official_label,
                    url=HttpUrl(resource_url),
                    resource_format=resource_format,
                    parent_catalogue_snapshot_id=exact_snapshot_id,
                ),
            )

        if not resources_by_url:
            raise ValueError("A pasta parlamentar não contém recursos XML ou JSON inequívocos")

        return CollectedParliamentResourceManifest(
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            parent_catalogue_snapshot_id=exact_snapshot_id,
            requested_candidate_url=HttpUrl(requested_url),
            source_name=parliament_resource_manifest_source_name(
                catalogue_kind,
                exact_legislature,
            ),
            title=parliament_resource_manifest_title(catalogue_kind, exact_legislature),
            source_url=HttpUrl(effective_url),
            content_sha256=content_sha256,
            raw_document=raw_document,
            resources=tuple(resources_by_url.values()),
        )


class ParliamentResourceManifestStager:
    """Grava o manifesto depois de revalidar a prova privada do catálogo pai."""

    def __init__(
        self,
        settings: Settings,
        repository: ParliamentResourceManifestRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def store(
        self,
        collection: CollectedParliamentResourceManifest,
        *,
        code_version: str = PARLIAMENT_RESOURCE_MANIFEST_CODE_VERSION,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(
                "O manifesto parlamentar privado só pode ser persistido em test ou staging"
            )
        expected_source_name = parliament_resource_manifest_source_name(
            collection.catalogue_kind,
            collection.legislature,
        )
        expected_title = parliament_resource_manifest_title(
            collection.catalogue_kind,
            collection.legislature,
        )
        if collection.source_name != expected_source_name or collection.title != expected_title:
            raise ValueError("A identidade do manifesto parlamentar diverge do lote pedido")
        if (
            str(collection.requested_candidate_url) != str(collection.source_url)
            or str(collection.source_url) != str(collection.raw_document.source_url)
            or collection.content_sha256 != collection.raw_document.content_sha256
        ):
            raise ValueError("A prova do manifesto parlamentar diverge da pasta candidata")
        if not collection.resources:
            raise ValueError("O manifesto parlamentar não pode ser persistido sem recursos")
        if collection.publishable or collection.editorial_cases_created:
            raise ValueError("O manifesto parlamentar não pode autorizar revisão ou publicação")

        parent_proof = await self.repository.require_catalogue_candidate(
            snapshot_id=collection.parent_catalogue_snapshot_id,
            catalogue_kind=collection.catalogue_kind,
            legislature=collection.legislature,
            candidate_url=str(collection.requested_candidate_url),
        )
        for resource in collection.resources:
            if (
                resource.catalogue_kind != collection.catalogue_kind
                or resource.legislature != collection.legislature
                or resource.parent_catalogue_snapshot_id != collection.parent_catalogue_snapshot_id
                or resource.status != PARLIAMENT_RESOURCE_STATUS
                or resource.historical_completeness != PARLIAMENT_RESOURCE_COMPLETENESS
                or resource.publishable
            ):
                raise ValueError("Um recurso parlamentar diverge do contrato privado do manifesto")
            require_parliament_url(str(resource.url))

        result = await self.repository.store_index(
            source_name=collection.source_name,
            publisher="PARLIAMENT",
            title=collection.title,
            raw_document=collection.raw_document,
            resources=[
                OfficialIndexItem(
                    title=resource.official_label,
                    url=str(resource.url),
                    category=resource.private_category,
                )
                for resource in collection.resources
            ],
            code_version=code_version,
        )
        return {
            **result,
            "catalogue_kind": collection.catalogue_kind.value,
            "legislature": collection.legislature,
            "parent_catalogue_snapshot_id": parent_proof.snapshot_id,
            "parent_catalogue_content_sha256": parent_proof.catalogue_content_sha256,
            "resource_count": len(collection.resources),
            "resource_status": PARLIAMENT_RESOURCE_STATUS,
            "historical_completeness": PARLIAMENT_RESOURCE_COMPLETENESS,
            "resources_downloaded": 0,
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
