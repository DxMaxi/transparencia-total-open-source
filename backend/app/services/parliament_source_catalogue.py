"""Inventário privado de fontes parlamentares históricas.

O catálogo identifica apenas pastas de legislatura que a Assembleia da República
publica com uma etiqueta exata. Uma ligação encontrada continua a ser um candidato
privado: não é descarregada, normalizada, revista ou publicada por este módulo.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.official_index_staging import (
    OfficialIndexItem,
    OfficialIndexStagingRepository,
)
from app.services.http import OfficialHttpClient

PARLIAMENT_CATALOGUE_CODE_VERSION = "parliament-source-catalogue-v1"
PARLIAMENT_CATALOGUE_HOSTS = frozenset({"parlamento.pt", "www.parlamento.pt", "app.parlamento.pt"})
PARLIAMENT_CANDIDATE_STATUS: Literal["PENDING_INSPECTION"] = "PENDING_INSPECTION"
PARLIAMENT_HISTORICAL_COMPLETENESS: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"

_SUPPORTED_ROMAN_LEGISLATURES = frozenset(
    {
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
        "XI",
        "XII",
        "XIII",
        "XIV",
        "XV",
        "XVI",
        "XVII",
    }
)
_LEGISLATURE_LABEL = re.compile(r"^(?P<legislature>[IVXLCDM]+) Legislatura$")


class ParliamentCatalogueKind(StrEnum):
    INITIATIVES = "INITIATIVES"
    ACTIVITIES = "ACTIVITIES"
    DEPUTY_ACTIVITY = "DEPUTY_ACTIVITY"


@dataclass(frozen=True, slots=True)
class ParliamentCatalogueConfig:
    source_name: str
    title: str
    url: str


PARLIAMENT_CATALOGUES: dict[ParliamentCatalogueKind, ParliamentCatalogueConfig] = {
    ParliamentCatalogueKind.INITIATIVES: ParliamentCatalogueConfig(
        source_name="PARLIAMENT_CATALOGUE_INITIATIVES",
        title="Assembleia da República — catálogo de iniciativas por legislatura",
        url="https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx",
    ),
    ParliamentCatalogueKind.ACTIVITIES: ParliamentCatalogueConfig(
        source_name="PARLIAMENT_CATALOGUE_ACTIVITIES",
        title="Assembleia da República — catálogo de atividades por legislatura",
        url="https://www.parlamento.pt/Cidadania/Paginas/DAatividades.aspx",
    ),
    ParliamentCatalogueKind.DEPUTY_ACTIVITY: ParliamentCatalogueConfig(
        source_name="PARLIAMENT_CATALOGUE_DEPUTY_ACTIVITY",
        title="Assembleia da República — catálogo de atividade dos deputados por legislatura",
        url="https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx",
    ),
}


@dataclass(frozen=True, slots=True)
class ParliamentSourceCandidate:
    catalogue_kind: ParliamentCatalogueKind
    legislature: str
    official_label: str
    url: HttpUrl
    status: Literal["PENDING_INSPECTION"] = PARLIAMENT_CANDIDATE_STATUS
    historical_completeness: Literal["NOT_ASSERTED"] = PARLIAMENT_HISTORICAL_COMPLETENESS
    publishable: bool = False

    @property
    def private_category(self) -> str:
        return ":".join(
            (
                "PARLIAMENT_SOURCE_CANDIDATE",
                self.catalogue_kind.value,
                self.legislature,
                self.status,
                self.historical_completeness,
            )
        )


@dataclass(frozen=True, slots=True)
class CollectedParliamentCatalogue:
    catalogue_kind: ParliamentCatalogueKind
    source_name: str
    title: str
    source_url: HttpUrl
    content_sha256: str
    raw_document: PrivateRawDocument
    candidates: tuple[ParliamentSourceCandidate, ...]
    publishable: bool = False
    editorial_proposals_created: int = 0


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parliament_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ValueError(f"URL parlamentar inválido: {value}") from exc
    host = (parsed.hostname or "").strip().rstrip(".").casefold()
    if (
        parsed.scheme != "https"
        or host not in PARLIAMENT_CATALOGUE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"URL parlamentar não autorizada: {value}")
    return value


def _exact_legislature(label: str) -> str | None:
    normalised = _normalise_space(label)
    if normalised == "Constituinte":
        return "CONSTITUINTE"
    match = _LEGISLATURE_LABEL.fullmatch(normalised)
    if match is None:
        return None
    legislature = match.group("legislature")
    return legislature if legislature in _SUPPORTED_ROMAN_LEGISLATURES else None


class ParliamentSourceCatalogueCollector:
    """Arquiva uma página de catálogo e extrai só legislaturas explícitas."""

    def __init__(self, http: OfficialHttpClient) -> None:
        self.http = http

    async def collect(
        self,
        catalogue_kind: ParliamentCatalogueKind,
    ) -> CollectedParliamentCatalogue:
        config = PARLIAMENT_CATALOGUES[catalogue_kind]
        requested_url = _parliament_url(config.url)
        response = await self.http.get(requested_url)
        effective_url = _parliament_url(str(response.url))
        content = response.content
        mime_type = response.headers.get("content-type")
        if not mime_type or mime_type.split(";", 1)[0].strip().casefold() != "text/html":
            raise ValueError("O catálogo parlamentar oficial não devolveu HTML")
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
        candidates_by_url: dict[str, ParliamentSourceCandidate] = {}
        for anchor in soup.find_all("a", href=True):
            official_label = _normalise_space(anchor.get_text(" ", strip=True))
            legislature = _exact_legislature(official_label)
            if legislature is None:
                continue
            candidate_url = urljoin(effective_url, str(anchor["href"]))
            try:
                _parliament_url(candidate_url)
            except ValueError:
                continue
            candidates_by_url.setdefault(
                candidate_url,
                ParliamentSourceCandidate(
                    catalogue_kind=catalogue_kind,
                    legislature=legislature,
                    official_label=official_label,
                    url=HttpUrl(candidate_url),
                ),
            )

        if not candidates_by_url:
            raise ValueError(
                "O catálogo parlamentar não contém pastas com etiquetas exatas de legislatura"
            )

        return CollectedParliamentCatalogue(
            catalogue_kind=catalogue_kind,
            source_name=config.source_name,
            title=config.title,
            source_url=HttpUrl(effective_url),
            content_sha256=content_sha256,
            raw_document=raw_document,
            candidates=tuple(candidates_by_url.values()),
        )


class ParliamentSourceCatalogueStager:
    """Persiste o catálogo exclusivamente em test ou staging privado."""

    def __init__(
        self,
        settings: Settings,
        repository: OfficialIndexStagingRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def store(
        self,
        collection: CollectedParliamentCatalogue,
        *,
        code_version: str = PARLIAMENT_CATALOGUE_CODE_VERSION,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(
                "O catálogo parlamentar privado só pode ser persistido em test ou staging"
            )
        config = PARLIAMENT_CATALOGUES[collection.catalogue_kind]
        if collection.source_name != config.source_name or collection.title != config.title:
            raise ValueError("A identidade do catálogo parlamentar diverge da configuração")
        if (
            str(collection.source_url) != str(collection.raw_document.source_url)
            or collection.content_sha256 != collection.raw_document.content_sha256
        ):
            raise ValueError("A prova do catálogo parlamentar diverge dos bytes recolhidos")
        if not collection.candidates:
            raise ValueError(
                "O catálogo parlamentar privado não pode ser persistido sem candidatos"
            )
        if collection.publishable or collection.editorial_proposals_created:
            raise ValueError("O inventário parlamentar não pode autorizar publicação ou propostas")
        for candidate in collection.candidates:
            if (
                candidate.catalogue_kind != collection.catalogue_kind
                or candidate.status != PARLIAMENT_CANDIDATE_STATUS
                or candidate.historical_completeness != PARLIAMENT_HISTORICAL_COMPLETENESS
                or candidate.publishable
            ):
                raise ValueError("Um candidato parlamentar diverge do contrato privado")
            _parliament_url(str(candidate.url))

        result = await self.repository.store_index(
            source_name=collection.source_name,
            publisher="PARLIAMENT",
            title=collection.title,
            raw_document=collection.raw_document,
            resources=[
                OfficialIndexItem(
                    title=candidate.official_label,
                    url=str(candidate.url),
                    category=candidate.private_category,
                )
                for candidate in collection.candidates
            ],
            code_version=code_version,
        )
        return {
            **result,
            "catalogue_kind": collection.catalogue_kind.value,
            "candidate_count": len(collection.candidates),
            "candidate_status": PARLIAMENT_CANDIDATE_STATUS,
            "historical_completeness": PARLIAMENT_HISTORICAL_COMPLETENESS,
            "editorial_proposals_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
