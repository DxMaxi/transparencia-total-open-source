"""Recolha mínima de índices oficiais para fontes V4 sem promoção pública."""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.core.security import is_official_url, require_official_url
from app.models.archive import PrivateRawDocument
from app.services.http import OfficialHttpClient


@dataclass(frozen=True, slots=True)
class OfficialIndexResource:
    title: str
    url: HttpUrl


@dataclass(frozen=True, slots=True)
class CollectedOfficialIndex:
    source_name: str
    source_url: HttpUrl
    content_sha256: str
    raw_document: PrivateRawDocument
    resources: tuple[OfficialIndexResource, ...]
    publishable: bool = False


class OfficialIndexCollector:
    """Arquiva um índice oficial sem inferir factos a partir das ligações."""

    def __init__(self, http: OfficialHttpClient) -> None:
        self.http = http

    async def collect(self, *, source_name: str, index_url: str) -> CollectedOfficialIndex:
        require_official_url(index_url)
        response = await self.http.get(index_url)
        effective_url = require_official_url(str(response.url))
        content = response.content
        content_sha256 = hashlib.sha256(content).hexdigest()
        mime_type = response.headers.get("content-type")
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(effective_url),
            content_sha256=content_sha256,
            mime_type=mime_type,
            content=content,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        resources: dict[str, OfficialIndexResource] = {}
        for anchor in soup.find_all("a", href=True):
            title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            url = urljoin(effective_url, str(anchor["href"]))
            if not title or not is_official_url(url):
                continue
            resources[url] = OfficialIndexResource(title=title[:500], url=HttpUrl(url))
        return CollectedOfficialIndex(
            source_name=source_name,
            source_url=HttpUrl(effective_url),
            content_sha256=content_sha256,
            raw_document=raw_document,
            resources=tuple(sorted(resources.values(), key=lambda item: item.title.casefold())),
        )


TRIBUNAL_CONTAS_INDEX_URL = (
    "https://www.tcontas.pt/pt-pt/TribunalContas/Publicacoes/Pages/"
    "Publicacoes-do-Tribunal-de-Contas.aspx"
)
EUROPEAN_PARLIAMENT_INDEX_URL = "https://data.europarl.europa.eu/en/developer-corner/opendata-api"
SNS_TRANSPARENCY_INDEX_URL = "https://transparencia.sns.gov.pt/pages/home-page/"
