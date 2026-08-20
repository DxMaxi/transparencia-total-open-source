"""Contrato da pesquisa global sobre projeções públicas já revistas."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.api import SourcePublisher

PublicSearchKind = Literal[
    "politicians",
    "parliament_sessions",
    "parliament_initiatives",
    "parliament_votes",
    "promises",
    "ai_explanations",
]


class PublishedGlobalSearchSource(BaseModel):
    """A pesquisa exige a prova completa, mesmo quando outros contratos a tornam opcional."""

    model_config = ConfigDict(frozen=True)

    publisher: SourcePublisher
    label: str
    url: HttpUrl
    retrieved_at: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublishedGlobalSearchItem(BaseModel):
    id: str
    kind: PublicSearchKind
    title: str
    description: str
    href: str = Field(pattern=r"^/")
    source: PublishedGlobalSearchSource
    verified_at: datetime
    observed_at: datetime | None = None
    coverage_state: Literal["AVAILABLE"] = "AVAILABLE"
    coverage_note: str


class PublishedGlobalSearchSection(BaseModel):
    kind: PublicSearchKind
    label: str
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    total: int | None = Field(default=None, ge=0)
    total_is_exact: bool
    items: list[PublishedGlobalSearchItem] = Field(default_factory=list)
    view_all_href: str = Field(pattern=r"^/")
    coverage_note: str

    @model_validator(mode="after")
    def availability_is_consistent(self) -> Self:
        if self.availability == "AVAILABLE":
            if self.total is None or not self.total_is_exact:
                raise ValueError("Uma secção disponível exige uma contagem exata")
        elif self.total is not None or self.total_is_exact or self.items:
            raise ValueError("Uma secção indisponível não pode apresentar contagens ou resultados")
        if any(item.kind != self.kind for item in self.items):
            raise ValueError("Um resultado não pode mudar de secção")
        return self


class PublishedGlobalSearch(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    legislature: str
    section_limit: int = Field(ge=1, le=20)
    total_results: int = Field(ge=0)
    available_sections: int = Field(ge=1, le=6)
    unavailable_sections: int = Field(ge=0, le=5)
    sections: list[PublishedGlobalSearchSection] = Field(min_length=6, max_length=6)
    publication_rule: str = (
        "A pesquisa consulta exclusivamente projeções públicas com fonte oficial arquivada, "
        "hash e revisão exigidos pelo respetivo circuito editorial."
    )
    search_rule: str = (
        "Pesquisar não cria associações, correspondências de identidade, conclusões, previsões "
        "nem novo conteúdo de inteligência artificial."
    )

    @model_validator(mode="after")
    def section_manifest_is_consistent(self) -> Self:
        expected = {
            "politicians",
            "parliament_sessions",
            "parliament_initiatives",
            "parliament_votes",
            "promises",
            "ai_explanations",
        }
        kinds = {section.kind for section in self.sections}
        if kinds != expected:
            raise ValueError("A pesquisa pública exige exatamente as seis secções declaradas")
        available = [section for section in self.sections if section.availability == "AVAILABLE"]
        if self.available_sections != len(available):
            raise ValueError("A contagem de secções disponíveis é inconsistente")
        if self.unavailable_sections != len(self.sections) - len(available):
            raise ValueError("A contagem de secções indisponíveis é inconsistente")
        if self.total_results != sum(section.total or 0 for section in available):
            raise ValueError("O total global não corresponde às contagens das secções")
        if any(len(section.items) > self.section_limit for section in available):
            raise ValueError("Uma secção ultrapassa o limite de resultados")
        return self
