from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

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
    parser_version: str = Field(default="parliament-activity-v2", min_length=3, max_length=100)
    sessions: list[ParliamentarySessionRecord] = Field(default_factory=list)
    initiatives: list[ParliamentaryInitiativeRecord] = Field(default_factory=list)
    votes: list[VoteEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_document: PrivateRawDocument | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_single_official_snapshot(self) -> "ParliamentActivityDataset":
        expected_url = str(self.dataset_url)
        for session in self.sessions:
            if session.source.content_sha256 != self.document_sha256:
                raise ValueError("Todos os registos têm de pertencer ao SHA-256 do dataset")
            if str(session.source.url) != expected_url:
                raise ValueError("Todos os registos têm de pertencer ao URL efetivo do dataset")
        for initiative in self.initiatives:
            if initiative.source.content_sha256 != self.document_sha256:
                raise ValueError("Todos os registos têm de pertencer ao SHA-256 do dataset")
            if str(initiative.source.url) != expected_url:
                raise ValueError("Todos os registos têm de pertencer ao URL efetivo do dataset")
        for vote in self.votes:
            if vote.source.content_sha256 != self.document_sha256:
                raise ValueError("Todos os registos têm de pertencer ao SHA-256 do dataset")
            if str(vote.source.url) != expected_url:
                raise ValueError("Todos os registos têm de pertencer ao URL efetivo do dataset")
        if any(record.legislature != self.legislature for record in self.sessions):
            raise ValueError("As sessões têm de pertencer à legislatura do dataset")
        if any(record.legislature != self.legislature for record in self.initiatives):
            raise ValueError("As iniciativas têm de pertencer à legislatura do dataset")
        return self
