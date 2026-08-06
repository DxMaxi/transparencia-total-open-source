import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import is_official_url
from app.models.api import OfficialSource, SourcePublisher, TransparencyResource
from app.models.archive import PrivateRawDocument
from app.services.http import OfficialHttpClient

EPT_INDEX_URL = "https://www.tribunalconstitucional.pt/tc/ept/"


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
    ) -> tuple[list[TransparencyResource], PrivateRawDocument]:
        response = await self.http.get(EPT_INDEX_URL)
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
        return sorted(resources.values(), key=lambda item: item.title.casefold()), raw_document

    async def public_resources(self) -> list[TransparencyResource]:
        resources, _ = await self.fetch_public_index()
        return resources
