from datetime import datetime
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
    person_id: str | None = None
    party_id: str | None = None


class PublishedParliamentaryVote(BaseModel):
    id: str
    source_id: str
    legislature: str
    title: str
    initiative_number: str | None = None
    voted_at: datetime | None = None
    result: str | None = None
    is_nominal: bool
    records: list[PublishedVoteRecord] = Field(default_factory=list)
    verified_at: datetime
    source: OfficialSource


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
