"""Projeções públicas V5.53; nunca incluem observações, HMAC ou IDs editoriais."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class PublicOrganisationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publisher: Literal["IRN"] = "IRN"
    title: str
    url: HttpUrl
    retrieved_at: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublishedOrganisationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^base_public_org_[0-9a-f]{32}$")
    legal_name: str
    kind: Literal["PUBLIC_BODY", "COMPANY", "NON_PROFIT", "EUROPEAN_BODY", "OTHER"]
    registry_record_id: str
    public_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: datetime


class PublishedOrganisationReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_reference: str
    original_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claimant_public_name: str
    claimant_role: str
    statement_text: str
    statement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    official_response_url: HttpUrl | None
    submitted_at: datetime


class PublishedOrganisation(PublishedOrganisationSummary):
    official_url: HttpUrl
    source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: PublicOrganisationSource
    replies: list[PublishedOrganisationReply]
    coverage_notice: str = (
        "Esta fotografia prova apenas a identificação pública revista. "
        "Não prova contratos, titulares, relações, conflitos ou irregularidades."
    )


class PublishedOrganisationList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PublishedOrganisationSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    coverage_notice: str = (
        "A lista inclui apenas fotografias publicadas neste circuito. "
        "Ausência não significa inexistência, incumprimento ou irregularidade."
    )


class PublishedOrganisationHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str = Field(pattern=r"^base_public_org_[0-9a-f]{32}$")
    action: Literal["PUBLISH", "WITHDRAW"]
    public_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_rationale: str
    actor_alias: str
    occurred_at: datetime


class PublishedOrganisationHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str = Field(pattern=r"^base_public_org_[0-9a-f]{32}$")
    items: list[PublishedOrganisationHistoryItem]
    replies: list[PublishedOrganisationReply]
    coverage_notice: str = (
        "O histórico conserva publicações, retiradas e direitos de resposta publicados ligados "
        "à fotografia exata. Os campos retirados não são republicados."
    )
