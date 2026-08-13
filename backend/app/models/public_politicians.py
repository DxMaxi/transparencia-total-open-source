from typing import Literal

from pydantic import BaseModel, Field

from app.models.api import PublishedPersonSummary


class PublishedPoliticianFacet(BaseModel):
    value: str
    label: str
    count: int = Field(ge=0)


class PublishedPoliticianDirectory(BaseModel):
    items: list[PublishedPersonSummary] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    next_cursor: str | None = None
    query: str | None = None
    party_short: str | None = None
    parties: list[PublishedPoliticianFacet] = Field(default_factory=list)
    total_is_exact: Literal[True] = True
    pagination: Literal["CURSOR"] = "CURSOR"
    search_rule: str = (
        "A pesquisa limita apenas o diretório de identidades já publicadas. Não cria, aproxima "
        "nem confirma correspondências entre pessoas."
    )
