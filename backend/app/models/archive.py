import hashlib
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
STORAGE_KEY_PATTERN = r"^sha256/[0-9a-f]{2}/[0-9a-f]{64}$"
STORAGE_BACKEND_PATTERN = r"^[A-Z][A-Z0-9_]{1,63}$"


class PrivateRawDocument(BaseModel):
    """Bytes oficiais mantidos apenas dentro do processo de ingestão.

    O conteúdo é deliberadamente excluído de serialização e de ``repr``. O
    modelo só é construído quando o SHA-256 declarado corresponde aos bytes
    exatos recebidos.
    """

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    source_url: HttpUrl
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    mime_type: str | None = Field(default=None, max_length=255)
    content: bytes = Field(min_length=1, exclude=True, repr=False)

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("A data de recolha do original deve incluir fuso horário")
        return value.astimezone(UTC)

    @field_validator("mime_type")
    @classmethod
    def normalise_mime_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        mime_type = value.split(";", 1)[0].strip().lower()
        if not mime_type or any(ord(character) < 32 for character in mime_type):
            raise ValueError("O tipo MIME do original é inválido")
        return mime_type

    @model_validator(mode="after")
    def verify_exact_hash(self) -> Self:
        observed = hashlib.sha256(self.content).hexdigest()
        if observed != self.content_sha256:
            raise ValueError("O SHA-256 declarado não corresponde aos bytes oficiais recebidos")
        return self


class RawArchiveReceipt(BaseModel):
    """Recibo privado de uma escrita ou verificação no arquivo imutável."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    storage_backend: str = Field(default="FILESYSTEM", pattern=STORAGE_BACKEND_PATTERN)
    storage_key: str = Field(pattern=STORAGE_KEY_PATTERN)
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(ge=1)
    mime_type: str | None = Field(default=None, max_length=255)
    source_url: HttpUrl
    retrieved_at: datetime
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    object_created: bool

    @field_validator("retrieved_at", "recorded_at")
    @classmethod
    def normalise_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("As datas do recibo de arquivo devem incluir fuso horário")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def storage_key_matches_hash(self) -> Self:
        expected = f"sha256/{self.content_sha256[:2]}/{self.content_sha256}"
        if self.storage_key != expected:
            raise ValueError("A chave do arquivo não corresponde ao SHA-256 do conteúdo")
        if self.recorded_at < self.retrieved_at:
            raise ValueError("A atestação não pode anteceder a recolha dos bytes oficiais")
        return self


class RawArchiveVerification(BaseModel):
    """Resultado estritamente de leitura da verificação de um objeto privado."""

    model_config = ConfigDict(frozen=True)

    status: Literal["VERIFIED", "UNAVAILABLE", "CORRUPT"]
    storage_backend: str = Field(default="FILESYSTEM", pattern=STORAGE_BACKEND_PATTERN)
    storage_key: str = Field(pattern=STORAGE_KEY_PATTERN)
    expected_sha256: str = Field(pattern=SHA256_PATTERN)
    observed_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    expected_byte_size: int = Field(ge=1)
    observed_byte_size: int | None = Field(default=None, ge=0)
    detail: str
