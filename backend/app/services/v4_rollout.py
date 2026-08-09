"""Operações controladas para activar a cobertura pública da V4."""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.official_index_staging import (
    OfficialIndexItem,
    OfficialIndexStagingRepository,
)
from app.services.http import OfficialHttpClient
from app.services.official_index import (
    EUROPEAN_PARLIAMENT_INDEX_URL,
    SNS_TRANSPARENCY_INDEX_URL,
    TRIBUNAL_CONTAS_INDEX_URL,
    OfficialIndexCollector,
)
from app.services.transparency_entity import EPT_INDEX_URL, TransparencyEntityCollector

logger = logging.getLogger(__name__)

DEFAULT_V4_ROLLOUT_CODE_VERSION = "v4-public-rollout-v4"

RolloutSource = Literal[
    "BASE_CONTRACTS",
    "DRE",
    "TRANSPARENCY_ENTITY",
    "COURT_OF_AUDIT",
    "EUROPEAN_PARLIAMENT",
    "LOCAL_SNS",
]


@dataclass(frozen=True, slots=True)
class RolloutSourceConfig:
    publisher: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class CollectedRolloutSource:
    raw_document: PrivateRawDocument
    items: tuple[OfficialIndexItem, ...]
    title: str
    status: Literal["SUCCEEDED", "PARTIAL"] = "SUCCEEDED"
    warnings: tuple[str, ...] = ()


SOURCE_CONFIGS: dict[RolloutSource, RolloutSourceConfig] = {
    "BASE_CONTRACTS": RolloutSourceConfig(
        publisher="BASE_GOV",
        title="Portal BASE — catálogo oficial de contratos",
        url="https://dados.gov.pt/api/1/datasets/66d72d488ca4b7cb2de28712/",
    ),
    "DRE": RolloutSourceConfig(
        publisher="DRE",
        title="Diário da República — índice oficial",
        url="https://diariodarepublica.pt/",
    ),
    "COURT_OF_AUDIT": RolloutSourceConfig(
        publisher="COURT_OF_AUDIT",
        title="Tribunal de Contas — índice oficial",
        url=TRIBUNAL_CONTAS_INDEX_URL,
    ),
    "EUROPEAN_PARLIAMENT": RolloutSourceConfig(
        publisher="EUROPEAN_PARLIAMENT",
        title="Parlamento Europeu — portal de dados abertos",
        url=EUROPEAN_PARLIAMENT_INDEX_URL,
    ),
    "LOCAL_SNS": RolloutSourceConfig(
        publisher="SNS",
        title="Portal da Transparência do SNS — índice oficial",
        url=SNS_TRANSPARENCY_INDEX_URL,
    ),
    "TRANSPARENCY_ENTITY": RolloutSourceConfig(
        publisher="TRANSPARENCY_ENTITY",
        title="Entidade para a Transparência — índice público",
        url=EPT_INDEX_URL,
    ),
}

DEFAULT_ROLLOUT_SOURCES: tuple[RolloutSource, ...] = (
    "BASE_CONTRACTS",
    "DRE",
    "TRANSPARENCY_ENTITY",
    "COURT_OF_AUDIT",
    "EUROPEAN_PARLIAMENT",
    "LOCAL_SNS",
)


class V4RolloutService:
    def __init__(
        self,
        settings: Settings,
        repository: OfficialIndexStagingRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def sync_source(
        self,
        source_name: RolloutSource,
        *,
        code_version: str = DEFAULT_V4_ROLLOUT_CODE_VERSION,
    ) -> dict[str, object]:
        config = SOURCE_CONFIGS[source_name]
        try:
            collection = await self._collect_source(source_name)
        except Exception as exc:
            try:
                await self.repository.record_failed_index_refresh(
                    source_name=source_name,
                    dataset_url=config.url,
                    code_version=code_version,
                    error_message=str(exc),
                )
            except Exception:
                logger.exception(
                    "v4_official_index_failure_recording_failed source_name=%s",
                    source_name,
                )
            raise

        return await self.repository.store_index(
            source_name=source_name,
            publisher=config.publisher,
            title=collection.title,
            raw_document=collection.raw_document,
            resources=list(collection.items),
            code_version=code_version,
            status_value=collection.status,
            warnings=list(collection.warnings),
        )

    async def _collect_source(
        self,
        source_name: RolloutSource,
    ) -> CollectedRolloutSource:
        config = SOURCE_CONFIGS[source_name]
        status: Literal["SUCCEEDED", "PARTIAL"] = "SUCCEEDED"
        warnings: tuple[str, ...] = ()
        title = config.title
        async with OfficialHttpClient(self.settings) as http:
            if source_name == "TRANSPARENCY_ENTITY":
                ept_collection = await TransparencyEntityCollector(
                    self.settings, http
                ).fetch_public_index(allow_portal_fallback=True)
                raw_document = ept_collection.raw_document
                items = [
                    OfficialIndexItem(
                        title=resource.title,
                        url=str(resource.url),
                        category=resource.category,
                    )
                    for resource in ept_collection.resources
                ]
                if not ept_collection.canonical_index_available:
                    status = "PARTIAL"
                    warnings = ept_collection.warnings
                    title = "Entidade para a Transparência — portal oficial de contingência"
            elif source_name == "BASE_CONTRACTS":
                response = await http.get(config.url)
                retrieved_at = datetime.now(UTC)
                raw_document = PrivateRawDocument(
                    source_url=HttpUrl(str(response.url)),
                    retrieved_at=retrieved_at,
                    content_sha256=hashlib.sha256(response.content).hexdigest(),
                    mime_type=response.headers.get("content-type"),
                    content=response.content,
                )
                items = [
                    OfficialIndexItem(
                        title="Catálogo oficial do conjunto de contratos públicos",
                        url=str(response.url),
                        category="Catálogo de dados",
                    )
                ]
            else:
                official_collection = await OfficialIndexCollector(http).collect(
                    source_name=source_name,
                    index_url=config.url,
                )
                raw_document = official_collection.raw_document
                items = [
                    OfficialIndexItem(title=resource.title, url=str(resource.url))
                    for resource in official_collection.resources
                ]

        return CollectedRolloutSource(
            raw_document=raw_document,
            items=tuple(items),
            title=title,
            status=status,
            warnings=warnings,
        )

    async def sync_sources(
        self,
        sources: list[RolloutSource],
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for source in sources:
            try:
                results.append(await self.sync_source(source))
            except Exception as exc:
                logger.exception(
                    "v4_official_index_source_refresh_failed source_name=%s",
                    source,
                )
                results.append(
                    {
                        "source_name": source,
                        "status": "FAILED",
                        "publication_performed": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
        return results
