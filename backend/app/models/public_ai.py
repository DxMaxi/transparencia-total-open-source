"""Contratos públicos das explicações DRE produzidas por IA e revistas por humanos."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from app.models.api import CitizenSummary


class PublishedAiSource(BaseModel):
    publisher: Literal["DRE"] = "DRE"
    label: str = "Diário da República — fonte oficial"
    title: str
    official_identifier: str | None = None
    url: HttpUrl
    retrieved_at: datetime
    published_at: datetime | None = None
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalised_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublishedAiGenerationDisclosure(BaseModel):
    provider: str
    model: str
    prompt_version: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    source_characters: int = Field(ge=1)
    processed_characters: int = Field(ge=1)
    source_truncated: bool
    provider_store: Literal[False] = False


class PublishedAiEditorialProof(BaseModel):
    human_reviewed: Literal[True] = True
    reviewed_by: str
    published_at: datetime
    editorial_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_event_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublishedAiExplanation(BaseModel):
    id: str = Field(pattern=r"^dre-[0-9a-f]{64}$")
    content_kind: Literal["AI_EXPLANATION"] = "AI_EXPLANATION"
    label: Literal["Explicação gerada por IA — revista por humano"] = (
        "Explicação gerada por IA — revista por humano"
    )
    ai_generated: Literal[True] = True
    ai_is_source: Literal[False] = False
    human_review_required: Literal[True] = True
    not_prediction: Literal[True] = True
    no_voting_recommendation: Literal[True] = True
    abstained: bool
    summary: CitizenSummary
    source: PublishedAiSource
    generation: PublishedAiGenerationDisclosure
    editorial: PublishedAiEditorialProof
    limitations: list[str] = Field(min_length=3, max_length=8)


class PublishedAiExplanationList(BaseModel):
    items: list[PublishedAiExplanation] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    query: str | None = None
    total_is_exact: Literal[True] = True
    publication_rule: str


class PublishedAiPublicEffect(BaseModel):
    kind: Literal["DATA_UNAVAILABLE"] = "DATA_UNAVAILABLE"
    public_id: str = Field(pattern=r"^dre-[0-9a-f]{64}$")
    message: str


class PublishedAiPublicationHistoryItem(BaseModel):
    event_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["PUBLISHED", "WITHDRAWN"]
    public_id: str = Field(pattern=r"^dre-[0-9a-f]{64}$")
    title: str
    decided_at: datetime
    actor_alias: str
    public_rationale: str
    reason_category: str | None = None
    source: PublishedAiSource
    editorial_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_proof_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_effect: PublishedAiPublicEffect | None = None
    public_effect_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
