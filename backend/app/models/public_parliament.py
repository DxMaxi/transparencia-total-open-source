from datetime import datetime

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


class PublishedParliamentActivity(BaseModel):
    sessions: list[PublishedParliamentarySession] = Field(default_factory=list)
    initiatives: list[PublishedParliamentaryInitiative] = Field(default_factory=list)
    votes: list[PublishedParliamentaryVote] = Field(default_factory=list)
    coverage_note: str = (
        "Só são apresentados registos provenientes de fotografias oficiais arquivadas, "
        "atestadas e aprovadas por revisão humana. Campos ausentes na fonte permanecem vazios."
    )
