"""Modelos privados e imutáveis para presenças em reuniões plenárias."""

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.models.archive import PrivateRawDocument


class ParliamentAttendanceStatus(StrEnum):
    """Leitura conservadora dos estados escritos pela Assembleia da República."""

    PRESENT = "PRESENT"
    JUSTIFIED_ABSENCE = "JUSTIFIED_ABSENCE"
    UNJUSTIFIED_ABSENCE = "UNJUSTIFIED_ABSENCE"
    UNKNOWN = "UNKNOWN"


class ParliamentAttendanceObservation(BaseModel):
    """Registo privado ligado apenas ao BID oficial da biografia do deputado."""

    model_config = ConfigDict(frozen=True)

    official_deputy_id: str = Field(min_length=1, max_length=200)
    parliamentary_name: str = Field(min_length=1, max_length=500)
    parliamentary_group_label: str | None = Field(default=None, max_length=200)
    status: ParliamentAttendanceStatus
    source_status_label: str = Field(min_length=1, max_length=300)
    source_status_code: str | None = Field(default=None, max_length=30)
    absence_reason: str | None = Field(default=None, max_length=1000)


class ParliamentAttendanceDataset(BaseModel):
    """Fotografia privada de uma reunião; não cria presenças públicas por si só."""

    model_config = ConfigDict(frozen=True)

    legislature: str = Field(min_length=1, max_length=20)
    official_meeting_id: str = Field(min_length=1, max_length=200)
    meeting_date: date
    meeting_type: str = Field(min_length=1, max_length=200)
    session_number: str | None = Field(default=None, max_length=50)
    source_url: HttpUrl
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str = Field(min_length=3, max_length=100)
    observations: tuple[ParliamentAttendanceObservation, ...]
    warnings: tuple[str, ...] = ()
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_document: PrivateRawDocument | None = Field(default=None, exclude=True, repr=False)

    @field_validator("collected_at")
    @classmethod
    def normalise_collected_at(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_single_official_meeting(self) -> "ParliamentAttendanceDataset":
        if not self.observations:
            raise ValueError("A fotografia de presenças não pode estar vazia")
        official_ids = [item.official_deputy_id for item in self.observations]
        if len(set(official_ids)) != len(official_ids):
            raise ValueError("Uma reunião não pode repetir o mesmo BID oficial de deputado")
        if self.raw_document is not None:
            if self.raw_document.content_sha256 != self.document_sha256:
                raise ValueError("Os bytes de presenças divergem do SHA-256 declarado")
            if str(self.raw_document.source_url) != str(self.source_url):
                raise ValueError("Os bytes de presenças divergem do URL oficial declarado")
        return self
