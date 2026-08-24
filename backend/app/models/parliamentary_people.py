"""Modelos privados e versionados para observações oficiais de deputados."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.models.api import OfficialSource
from app.models.archive import PrivateRawDocument


class ParliamentaryGroupObservation(BaseModel):
    """Período de grupo parlamentar tal como declarado pela fonte oficial."""

    model_config = ConfigDict(frozen=True)

    source_id: str | None = Field(default=None, min_length=1, max_length=200)
    short_name: str = Field(min_length=1, max_length=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalise_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ParliamentarySituationObservation(BaseModel):
    """Situação do deputado; não equivale automaticamente a um mandato jurídico."""

    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1, max_length=300)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalise_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ParliamentaryOfficeObservation(BaseModel):
    """Cargo parlamentar observado, mantendo o identificador oficial quando existe."""

    model_config = ConfigDict(frozen=True)

    source_id: str | None = Field(default=None, min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def normalise_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ParliamentaryDeputyObservation(BaseModel):
    """Ficha privada ligada apenas ao ``DepId`` explícito da Assembleia da República."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, max_length=200)
    candidate_source_id: str | None = Field(default=None, min_length=1, max_length=200)
    legislature: str = Field(min_length=1, max_length=20)
    parliamentary_name: str = Field(min_length=1, max_length=500)
    full_name: str | None = Field(default=None, max_length=1000)
    constituency_source_id: str | None = Field(default=None, min_length=1, max_length=200)
    constituency_label: str | None = Field(default=None, max_length=300)
    parliamentary_groups: tuple[ParliamentaryGroupObservation, ...] = ()
    mandate_situations: tuple[ParliamentarySituationObservation, ...] = ()
    offices: tuple[ParliamentaryOfficeObservation, ...] = ()
    source: OfficialSource


class ParliamentDeputyObservationDataset(BaseModel):
    """Fotografia privada que nunca cria identidades ou perfis públicos por si só."""

    model_config = ConfigDict(frozen=True)

    legislature: str = Field(min_length=1, max_length=20)
    dataset_url: HttpUrl
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str = Field(min_length=3, max_length=100)
    observations: tuple[ParliamentaryDeputyObservation, ...]
    warnings: tuple[str, ...] = ()
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_document: PrivateRawDocument | None = Field(default=None, exclude=True, repr=False)

    @field_validator("collected_at")
    @classmethod
    def normalise_collected_at(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_single_official_snapshot(self) -> "ParliamentDeputyObservationDataset":
        expected_url = str(self.dataset_url)
        if not self.observations:
            raise ValueError("A fotografia de deputados não pode estar vazia")
        for observation in self.observations:
            if observation.legislature != self.legislature:
                raise ValueError("Todas as observações têm de pertencer à mesma legislatura")
            if observation.source.content_sha256 != self.document_sha256:
                raise ValueError("Todas as observações têm de pertencer ao SHA-256 do dataset")
            if str(observation.source.url) != expected_url:
                raise ValueError("Todas as observações têm de pertencer ao URL efetivo do dataset")
        return self
