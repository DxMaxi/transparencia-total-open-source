from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Transparência Total / Fator Cívico API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    admin_api_key: SecretStr | None = None
    database_url: SecretStr | None = None

    official_user_agent: str = (
        "TransparenciaTotal/0.3 (+https://github.com/SEU_UTILIZADOR/transparencia-total; "
        "contacto: dados@transparencia-total.pt)"
    )
    http_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    http_trust_env: bool = False
    source_requests_per_second: float = Field(default=0.5, gt=0, le=5)
    source_max_bytes: int = Field(default=60_000_000, ge=10_000, le=200_000_000)

    base_dataset_catalog_url: AnyHttpUrl = AnyHttpUrl(
        "https://dados.gov.pt/api/1/datasets/66d72d488ca4b7cb2de28712/"
    )
    base_resource_url: AnyHttpUrl | None = None
    base_max_bytes: int = Field(default=200_000_000, ge=1_000_000, le=500_000_000)
    base_max_uncompressed_bytes: int = Field(
        default=750_000_000,
        ge=1_000_000,
        le=2_000_000_000,
    )
    protected_identifier_pepper: SecretStr | None = None
    open_data_max_rows: int = Field(default=10_000, ge=100, le=100_000)

    parlamento_base_url: AnyHttpUrl = AnyHttpUrl("https://www.parlamento.pt")
    parlamento_deputies_catalogue_path: str = "/Cidadania/Paginas/DAInformacaoBase.aspx"
    parlamento_activity_catalogue_path: str = "/Cidadania/Paginas/DAatividadeDeputado.aspx"
    parlamento_initiatives_catalogue_path: str = "/Cidadania/Paginas/DAIniciativas.aspx"
    parlamento_deputies_url: AnyHttpUrl | None = None
    parlamento_votes_url: AnyHttpUrl | None = None

    dre_rss_url: AnyHttpUrl | None = None

    ai_provider: Literal["disabled", "openai"] = "disabled"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6"
    openai_store: bool = False
    ai_max_source_chars: int = 220_000
    ai_chunk_chars: int = 48_000

    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = None
    vapid_subject: str = "mailto:admin@transparencia-total.pt"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "base_resource_url",
        "parlamento_deputies_url",
        "parlamento_votes_url",
        "dre_rss_url",
        "openai_api_key",
        "protected_identifier_pepper",
        "vapid_private_key",
        mode="before",
    )
    @classmethod
    def blank_optional_values(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            parsed = urlparse(origin)
            local_http = parsed.scheme == "http" and parsed.hostname in {
                "localhost",
                "127.0.0.1",
                "terminal.local",
            }
            if parsed.scheme != "https" and not local_http:
                raise ValueError("CORS_ORIGINS exige HTTPS, exceto em desenvolvimento local")
            if (
                not parsed.hostname
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Cada origem CORS deve conter apenas esquema, anfitrião e porta")
        return value

    @field_validator("admin_api_key")
    @classmethod
    def validate_admin_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("ADMIN_API_KEY deve ter pelo menos 32 caracteres")
        return value

    @field_validator("protected_identifier_pepper")
    @classmethod
    def validate_identifier_pepper(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("PROTECTED_IDENTIFIER_PEPPER deve ter pelo menos 32 caracteres")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
