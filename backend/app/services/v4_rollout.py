"""Operações controladas para activar a cobertura pública da V4."""

import hashlib
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
    SNS_RADAR_INDEX_URL,
    TRIBUNAL_CONTAS_INDEX_URL,
    OfficialIndexCollector,
)
from app.services.transparency_entity import TransparencyEntityCollector

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
        title="Serviço Nacional de Saúde — índice oficial",
        url=SNS_RADAR_INDEX_URL,
    ),
    "TRANSPARENCY_ENTITY": RolloutSourceConfig(
        publisher="TRANSPARENCY_ENTITY",
        title="Entidade para a Transparência — índice público",
        url="https://www.tribunalconstitucional.pt/tc/ept/",
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
        code_version: str = "v4-public-rollout-v1",
    ) -> dict[str, object]:
        config = SOURCE_CONFIGS[source_name]
        async with OfficialHttpClient(self.settings) as http:
            if source_name == "TRANSPARENCY_ENTITY":
                resources, raw_document = await TransparencyEntityCollector(
                    self.settings, http
                ).fetch_public_index()
                items = [
                    OfficialIndexItem(
                        title=resource.title,
                        url=str(resource.url),
                        category=resource.category,
                    )
                    for resource in resources
                ]
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
                collection = await OfficialIndexCollector(http).collect(
                    source_name=source_name,
                    index_url=config.url,
                )
                raw_document = collection.raw_document
                items = [
                    OfficialIndexItem(title=resource.title, url=str(resource.url))
                    for resource in collection.resources
                ]

        return await self.repository.store_index(
            source_name=source_name,
            publisher=config.publisher,
            title=config.title,
            raw_document=raw_document,
            resources=items,
            code_version=code_version,
        )

    async def sync_sources(
        self,
        sources: list[RolloutSource],
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for source in sources:
            results.append(await self.sync_source(source))
        return results
