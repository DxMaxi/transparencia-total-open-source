import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import is_official_url, sha256_text
from app.models.api import OfficialSource, SourcePublisher, TransparencyResource
from app.services.http import OfficialHttpClient

EPT_INDEX_URL = "https://www.tribunalconstitucional.pt/tc/ept/"


class TransparencyEntityCollector:
    """Indexa apenas recursos que a Entidade para a Transparência publica abertamente.

    O coletor não tenta contornar formulários, autenticação ou limites de acesso e não
    transforma a existência de uma declaração em alegações sobre o seu conteúdo.
    """

    def __init__(self, settings: Settings, http: OfficialHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def public_resources(self) -> list[TransparencyResource]:
        response = await self.http.get(EPT_INDEX_URL)
        document_hash = sha256_text(response.text)
        source = OfficialSource(
            publisher=SourcePublisher.TRANSPARENCY_ENTITY,
            label="Entidade para a Transparência — Tribunal Constitucional",
            url=HttpUrl(str(response.url)),
            content_sha256=document_hash,
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
        return sorted(resources.values(), key=lambda item: item.title.casefold())
