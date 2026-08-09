import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import is_official_url
from app.models.api import OfficialSource, SourcePublisher, TransparencyResource
from app.models.archive import PrivateRawDocument
from app.services.http import OfficialHttpClient

EPT_INDEX_URL = "https://www.tribunalconstitucional.pt/tc/ept/"
EPT_PORTAL_FALLBACK_URL = "https://entidadetransparencia.pt/"
EPT_PORTAL_FALLBACK_WARNING = (
    "Índice canónico da EPT indisponível; foi preservado apenas o portal oficial alternativo."
)
EPT_PORTAL_RATE_LIMIT_WARNING = (
    "Índice canónico da EPT respondeu HTTP 429; foi preservado apenas o portal oficial alternativo."
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TransparencyIndexCollection:
    resources: tuple[TransparencyResource, ...]
    raw_document: PrivateRawDocument
    canonical_index_available: bool
    warnings: tuple[str, ...] = ()


class TransparencyEntityCollector:
    """Indexa apenas recursos públicos da Entidade para a Transparência.

    Não contorna formulários, autenticação ou limites de acesso. Não recolhe o
    conteúdo de declarações nem transforma ausência de recursos em ausência de
    declaração.
    """

    def __init__(self, settings: Settings, http: OfficialHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def fetch_public_index(
        self,
        *,
        allow_portal_fallback: bool = False,
    ) -> TransparencyIndexCollection:
        canonical_index_available = True
        warnings: tuple[str, ...] = ()
        try:
            response = await self.http.get(EPT_INDEX_URL)
        except (
            httpx.NetworkError,
            httpx.TimeoutException,
            httpx.HTTPStatusError,
        ) as exc:
            is_rate_limited = (
                isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
            )
            if not allow_portal_fallback or (
                isinstance(exc, httpx.HTTPStatusError) and not is_rate_limited
            ):
                raise
            logger.warning("ept_canonical_index_unavailable_using_official_portal_fallback")
            response = await self.http.get(EPT_PORTAL_FALLBACK_URL)
            canonical_index_available = False
            warnings = (
                (EPT_PORTAL_RATE_LIMIT_WARNING,)
                if is_rate_limited
                else (EPT_PORTAL_FALLBACK_WARNING,)
            )
        retrieved_at = datetime.now(UTC)
        content_sha256 = hashlib.sha256(response.content).hexdigest()
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(str(response.url)),
            retrieved_at=retrieved_at,
            content_sha256=content_sha256,
            mime_type=response.headers.get("content-type"),
            content=response.content,
        )
        source = OfficialSource(
            publisher=SourcePublisher.TRANSPARENCY_ENTITY,
            label="Entidade para a Transparência — Tribunal Constitucional",
            url=raw_document.source_url,
            retrieved_at=retrieved_at,
            content_sha256=content_sha256,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        resources: dict[str, TransparencyResource] = {}
        for anchor in soup.find_all("a", href=True):
            title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            url = urljoin(str(response.url), str(anchor["href"]))
            if not title or not is_official_url(url):
                continue
            context = anchor.find_parent(["section", "article", "li", "div"])
            heading = context.find_previous(["h2", "h3", "h4"]) if context else None
            category = (
                re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
                if heading
                else "Recurso público"
            )
            resources[url] = TransparencyResource(
                title=title,
                url=HttpUrl(url),
                category=category,
                source=source,
            )
        return TransparencyIndexCollection(
            resources=tuple(sorted(resources.values(), key=lambda item: item.title.casefold())),
            raw_document=raw_document,
            canonical_index_available=canonical_index_available,
            warnings=warnings,
        )

    async def public_resources(self) -> list[TransparencyResource]:
        collection = await self.fetch_public_index()
        return list(collection.resources)
