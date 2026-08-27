"""Fotografia privada das relações de autoria individual declaradas pela AR."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.models.archive import PrivateRawDocument

PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION = "parliament-initiative-authorship-v1"


class ParliamentInitiativeAuthorRelation(StrEnum):
    """Relação literal atualmente distinguida pelo ficheiro oficial de iniciativas."""

    AUTHOR = "AUTHOR"


class ParliamentInitiativeAuthorObservation(BaseModel):
    """Uma ligação fonte-iniciativa-deputado, sem associação por nome."""

    model_config = ConfigDict(frozen=True)

    initiative_source_id: str = Field(min_length=1, max_length=200)
    official_deputy_id: str = Field(min_length=1, max_length=200)
    parliamentary_name: str = Field(min_length=1, max_length=500)
    parliamentary_group_label: str | None = Field(default=None, max_length=300)
    relation: ParliamentInitiativeAuthorRelation = ParliamentInitiativeAuthorRelation.AUTHOR

    @field_validator("initiative_source_id", "official_deputy_id", "parliamentary_name")
    @classmethod
    def strip_required_source_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("O identificador ou nome oficial não pode estar vazio")
        return stripped

    @field_validator("parliamentary_group_label")
    @classmethod
    def strip_optional_source_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ParliamentInitiativeAuthorshipDataset(BaseModel):
    """Manifesto append-only de autorias individuais observadas num único recurso."""

    model_config = ConfigDict(frozen=True)

    legislature: str = Field(min_length=1, max_length=20)
    dataset_url: HttpUrl
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str = Field(
        default=PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION,
        min_length=3,
        max_length=100,
    )
    observations: tuple[ParliamentInitiativeAuthorObservation, ...]
    warnings: tuple[str, ...] = ()
    collected_at: datetime
    raw_document: PrivateRawDocument | None = Field(default=None, exclude=True, repr=False)

    @field_validator("collected_at")
    @classmethod
    def normalise_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_exact_private_snapshot(self) -> "ParliamentInitiativeAuthorshipDataset":
        if not self.observations:
            raise ValueError("A fotografia não contém autorias individuais com idCadastro")
        if len(self.observations) > 100_000:
            raise ValueError("A fotografia excede o limite de autorias individuais")
        keys = [(item.initiative_source_id, item.official_deputy_id) for item in self.observations]
        if len(set(keys)) != len(keys):
            raise ValueError("A fotografia contém a mesma autoria individual mais do que uma vez")
        if self.raw_document is None:
            raise ValueError("Os bytes oficiais arquivados são obrigatórios")
        if (
            self.raw_document.content_sha256 != self.document_sha256
            or str(self.raw_document.source_url) != str(self.dataset_url)
            or self.raw_document.retrieved_at != self.collected_at
        ):
            raise ValueError("Os bytes privados divergem do manifesto de autorias")
        return self
