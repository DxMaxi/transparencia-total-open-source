import hashlib
import re
from datetime import UTC, datetime

import feedparser
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import require_official_url, sha256_text
from app.models.api import LegalDocument
from app.models.archive import PrivateRawDocument
from app.services.http import OfficialHttpClient


class DreCollector:
    def __init__(self, settings: Settings, http: OfficialHttpClient) -> None:
        self.settings = settings
        self.http = http

    async def fetch_document(self, source_url: str) -> LegalDocument:
        require_official_url(source_url)
        response = await self.http.get(source_url)
        retrieved_at = datetime.now(UTC)
        raw_sha256 = hashlib.sha256(response.content).hexdigest()
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(str(response.url)),
            retrieved_at=retrieved_at,
            content_sha256=raw_sha256,
            mime_type=response.headers.get("content-type"),
            content=response.content,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup.select("script, style, nav, header, footer, form, noscript"):
            element.decompose()

        title = self._extract_title(soup)
        main = soup.select_one("main, article, #content, .document-content, .conteudo") or soup.body
        text = main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) < 100:
            raise ValueError("Não foi possível extrair texto jurídico suficiente da fonte oficial")

        identifier = self._extract_identifier(title, text)
        return LegalDocument(
            title=title,
            source_url=HttpUrl(str(response.url)),
            official_identifier=identifier,
            text=text,
            content_sha256=raw_sha256,
            normalised_text_sha256=sha256_text(text),
            raw_document=raw_document,
        )

    async def read_rss(self) -> list[dict[str, str | None]]:
        if self.settings.dre_rss_url is None:
            raise ValueError(
                "DRE_RSS_URL não configurado; não é assumido um endpoint não documentado"
            )
        response = await self.http.get(str(self.settings.dre_rss_url))
        parsed = feedparser.loads(response.content)
        items: list[dict[str, str | None]] = []
        for entry in parsed.entries:
            link = str(entry.get("link") or "")
            if not link:
                continue
            require_official_url(link)
            items.append(
                {
                    "title": str(entry.get("title") or "Sem título"),
                    "url": link,
                    "published": str(entry.get("published") or "") or None,
                    "summary": BeautifulSoup(
                        str(entry.get("summary") or ""), "html.parser"
                    ).get_text(" ", strip=True),
                }
            )
        return items

    @staticmethod
    def build_eli_url(
        document_type: str,
        number: str,
        year: int,
        month: int,
        day: int,
    ) -> str:
        safe_type = re.sub(r"[^a-z-]", "", document_type.lower())
        safe_number = re.sub(r"[^0-9a-z-]", "", number.lower())
        url = (
            f"https://data.dre.pt/eli/{safe_type}/{safe_number}/{year}/"
            f"{month:02d}/{day:02d}/p/dre/pt/html"
        )
        require_official_url(url)
        return url

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        heading = soup.find(["h1", "h2"])
        if heading:
            return re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
        if soup.title:
            return re.sub(r"\s+", " ", soup.title.get_text(" ", strip=True)).strip()
        return "Diploma sem título extraído"

    @staticmethod
    def _extract_identifier(title: str, text: str) -> str | None:
        match = re.search(
            r"((?:Decreto-Lei|Lei|Portaria|Resolução|Regulamento)\s+n[.ºo]*\s*[\w./-]+)",
            f"{title}\n{text[:2000]}",
            re.IGNORECASE,
        )
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else None
