from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.api import OfficialSource, VoteActorType, VoteChoice


class PublishedParliamentarySession(BaseModel):
    id: str
    source_id: str
    legislature: str
    session_number: str | None = None
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    verified_at: datetime
    source: OfficialSource


class PublishedParliamentaryInitiative(BaseModel):
    id: str
    source_id: str
    legislature: str
    number: str
    initiative_type: str
    title: str
    description: str | None = None
    introduced_at: datetime | None = None
    status: str | None = None
    official_url: str
    verified_at: datetime
    source: OfficialSource


class PublishedVoteRecord(BaseModel):
    actor_label: str
    actor_type: VoteActorType
    choice: VoteChoice
    person_source_id: str | None = None
    party_source_id: str | None = None


class PublishedParliamentaryVote(BaseModel):
    id: str
    source_id: str
    legislature: str
    title: str
    initiative_number: str | None = None
    voted_at: datetime | None = None
    result: str | None = None
    is_nominal: bool
    initiative_type: str | None = None
    initiative_title: str | None = None
    initiative_status: str | None = None
    initiative_official_url: str | None = None
    records: list[PublishedVoteRecord] = Field(default_factory=list)
    verified_at: datetime
    source: OfficialSource


class PublishedParliamentFacetOption(BaseModel):
    value: str
    label: str
    count: int = Field(ge=0)


class PublishedParliamentPartyFacet(PublishedParliamentFacetOption):
    """Grupo com identificador oficial exato; nunca nasce de comparação textual."""

    value: str = Field(min_length=1, max_length=200)


class PublishedParliamentFacets(BaseModel):
    legislatures: list[str] = Field(default_factory=list)
    initiative_types: list[PublishedParliamentFacetOption] = Field(default_factory=list)
    initiative_statuses: list[PublishedParliamentFacetOption] = Field(default_factory=list)
    vote_results: list[PublishedParliamentFacetOption] = Field(default_factory=list)
    parties: list[PublishedParliamentPartyFacet] = Field(default_factory=list)
    topics_available: Literal[False] = False
    topics_note: str = (
        "A fotografia oficial publicada não fornece um tema estruturado. "
        "A plataforma não o deduz por palavras-chave nem por inteligência artificial."
    )


class PublishedParliamentExplorer(BaseModel):
    kind: Literal["sessions", "initiatives", "votes"]
    legislature: str
    query: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    sessions: list[PublishedParliamentarySession] = Field(default_factory=list)
    initiatives: list[PublishedParliamentaryInitiative] = Field(default_factory=list)
    votes: list[PublishedParliamentaryVote] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    facets: PublishedParliamentFacets
    explanation_rule: str = (
        "Os explicadores distinguem o resultado registado do impacto jurídico ou material. "
        "Sem prova oficial adicional, o impacto permanece como dados indisponíveis."
    )


class PublishedParliamentCoverageRow(BaseModel):
    legislature: str
    scope: Literal["activity", "votes"]
    record_kind: Literal["sessions", "initiatives", "votes", "vote_records"]
    record_label: str
    published_count: int = Field(ge=0)
    count_is_exact: Literal[True] = True
    observed_from: date | None = None
    observed_through: date | None = None
    collected_at: datetime
    verified_at: datetime
    source: OfficialSource
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical_completeness: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    limitation: str


class PublishedParliamentPublicationCounts(BaseModel):
    sessions: int = Field(ge=0)
    initiatives: int = Field(ge=0)
    votes: int = Field(ge=0)
    vote_records: int = Field(ge=0)


class PublishedParliamentPublicEffect(BaseModel):
    kind: Literal["DATA_UNAVAILABLE", "FALLBACK_TO_PREVIOUS_SNAPSHOT"]
    scope: Literal["activity", "votes"]
    legislature: str
    message: str
    snapshot_reference_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    collected_at: datetime | None = None
    source_url: str | None = None
    source_retrieved_at: datetime | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verified_at: datetime | None = None


class PublishedParliamentPublicationHistoryItem(BaseModel):
    event_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["PUBLISHED", "WITHDRAWN"]
    scope: Literal["activity", "votes"]
    scope_label: str
    legislature: str
    target_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decided_at: datetime
    actor_alias: str
    public_rationale: str
    reason_category: str | None = None
    source: OfficialSource
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_counts: PublishedParliamentPublicationCounts
    public_effect: PublishedParliamentPublicEffect | None = None
    public_effect_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class PublishedParliamentActivity(BaseModel):
    sessions: list[PublishedParliamentarySession] = Field(default_factory=list)
    initiatives: list[PublishedParliamentaryInitiative] = Field(default_factory=list)
    votes: list[PublishedParliamentaryVote] = Field(default_factory=list)
    coverage_note: str = (
        "Só são apresentados registos provenientes de fotografias oficiais arquivadas, "
        "atestadas e aprovadas por revisão humana. Campos ausentes na fonte permanecem vazios."
    )
