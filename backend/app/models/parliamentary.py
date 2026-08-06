from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.api import OfficialSource, VoteEvent
from app.models.archive import PrivateRawDocument


class ParliamentarySessionRecord(BaseModel):
    """Sessão oficial tal como observada numa fonte da Assembleia da República."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, max_length=200)
    legislature: str = Field(min_length=1, max_length=20)
    session_number: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=1000)
    starts_at: datetime
    ends_at: datetime | None = None
    source: OfficialSource

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalise_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ParliamentaryInitiativeRecord(BaseModel):
    """Iniciativa parlamentar sem inferir estado, autoria ou resultado ausentes da fonte."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, max_length=200)
    legislature: str = Field(min_length=1, max_length=20)
    number: str = Field(min_length=1, max_length=200)
    initiative_type: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=4000)
    description: str | None = Field(default=None, max_length=20_000)
    introduced_at: datetime | None = None
    status: str | None = Field(default=None, max_length=500)
    official_url: HttpUrl
    source: OfficialSource

    @field_validator("introduced_at")
    @classmethod
    def normalise_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ParliamentActivityDataset(BaseModel):
    """Fotografia privada de atividade parlamentar; recolha nunca equivale a publicação."""

    model_config = ConfigDict(frozen=True)

    legislature: str
    dataset_url: HttpUrl
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sessions: list[ParliamentarySessionRecord] = Field(default_factory=list)
    initiatives: list[ParliamentaryInitiativeRecord] = Field(default_factory=list)
    votes: list[VoteEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_document: PrivateRawDocument | None = Field(default=None, exclude=True, repr=False)
