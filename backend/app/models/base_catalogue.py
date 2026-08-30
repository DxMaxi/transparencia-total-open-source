"""Modelos privados do âmbito temporal dos contratos do Portal BASE."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
DATASET_ID_PATTERN = r"^[0-9a-f]{24}$"
RESOURCE_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class BaseCatalogueCoverageState(StrEnum):
    HISTORICAL_CLOSED_YEAR = "HISTORICAL_CLOSED_YEAR"
    CURRENT_ROLLING_YEAR = "CURRENT_ROLLING_YEAR"


class BaseCatalogueScopeManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    manifest_schema: Literal["base-contracts-temporal-scope-manifest-v1"] = Field(alias="schema")
    dataset_id: str = Field(pattern=DATASET_ID_PATTERN)
    catalogue_api_url: HttpUrl
    public_dataset_url: HttpUrl
    producer_id: str = Field(pattern=DATASET_ID_PATTERN)
    producer_name: str = Field(min_length=3, max_length=300)
    licence_code: Literal["other-pd"]
    update_frequency: Literal["weekly"]
    first_year: Literal[2012]
    resource_format: Literal["ZIP"]
    parser_version: Literal["base-contracts-catalogue-v1"]
    policy_version: Literal["base-temporal-scope-v1"]
    source_name: Literal["BASE_CONTRACTS_CATALOGUE_PRIVATE"]
    closed_year_rule: str = Field(min_length=20, max_length=500)
    rolling_year_rule: str = Field(min_length=20, max_length=500)

    @model_validator(mode="after")
    def validate_catalogue_identity(self) -> Self:
        if self.catalogue_api_url.host != "dados.gov.pt":
            raise ValueError("O catálogo BASE tem de usar o domínio oficial dados.gov.pt")
        if self.catalogue_api_url.query or self.catalogue_api_url.fragment:
            raise ValueError("O URL do catálogo BASE não pode conter parâmetros ou fragmentos")
        catalogue_path = self.catalogue_api_url.path or ""
        if f"/datasets/{self.dataset_id}/" not in catalogue_path:
            raise ValueError("O URL do catálogo não corresponde ao identificador revisto")
        if self.public_dataset_url.host != "dados.gov.pt":
            raise ValueError("A página pública BASE tem de usar o domínio oficial dados.gov.pt")
        return self


class BaseCatalogueResourceScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=0)
    source_resource_id: str = Field(pattern=RESOURCE_ID_PATTERN)
    resource_year: int = Field(ge=2012, le=2100)
    coverage_state: BaseCatalogueCoverageState
    title: str = Field(min_length=1, max_length=500)
    resource_format: Literal["ZIP"]
    versioned_url: HttpUrl
    stable_url: HttpUrl
    source_modified_at: datetime
    byte_size: int = Field(gt=0, le=500_000_000)
    metadata_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("source_modified_at")
    @classmethod
    def normalise_modified_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("A atualização do recurso BASE tem de incluir fuso horário")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_official_urls(self) -> Self:
        if self.versioned_url.host != "dados.gov.pt" or self.stable_url.host != "dados.gov.pt":
            raise ValueError("Os recursos BASE têm de permanecer no domínio oficial dados.gov.pt")
        if (
            self.versioned_url.query
            or self.versioned_url.fragment
            or self.stable_url.query
            or self.stable_url.fragment
        ):
            raise ValueError("Os URLs dos recursos BASE não podem conter parâmetros ou fragmentos")
        expected_stable_path = f"/api/1/datasets/r/{self.source_resource_id}"
        stable_path = (self.stable_url.path or "").rstrip("/")
        versioned_path = self.versioned_url.path or ""
        if stable_path != expected_stable_path:
            raise ValueError("O URL estável não corresponde ao identificador do recurso BASE")
        if not versioned_path.endswith(f"/contratos{self.resource_year}.zip"):
            raise ValueError("O URL versionado não corresponde ao ano do recurso BASE")
        if self.title.casefold() != f"contratos{self.resource_year}.zip":
            raise ValueError("O título do recurso BASE não corresponde ao respetivo ano")
        return self


class BaseCatalogueTemporalScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(pattern=DATASET_ID_PATTERN)
    dataset_title: str = Field(min_length=10, max_length=500)
    producer_id: str = Field(pattern=DATASET_ID_PATTERN)
    producer_name: str = Field(min_length=3, max_length=300)
    licence_code: Literal["other-pd"]
    update_frequency: Literal["weekly"]
    catalogue_url: HttpUrl
    public_dataset_url: HttpUrl
    catalogue_updated_at: datetime
    retrieved_at: datetime
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    source_byte_size: int = Field(gt=0, le=10_000_000)
    parser_version: Literal["base-contracts-catalogue-v1"]
    policy_version: Literal["base-temporal-scope-v1"]
    first_year: Literal[2012]
    closed_through_year: int = Field(ge=2012, le=2100)
    rolling_year: int = Field(ge=2013, le=2100)
    resource_count: int = Field(gt=0, le=100)
    scope_sha256: str = Field(pattern=SHA256_PATTERN)
    resources: list[BaseCatalogueResourceScope] = Field(min_length=1, max_length=100)

    @field_validator("catalogue_updated_at", "retrieved_at")
    @classmethod
    def normalise_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("As datas do âmbito BASE têm de incluir fuso horário")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_temporal_sequence(self) -> Self:
        expected_years = list(range(self.first_year, self.rolling_year + 1))
        observed_years = [resource.resource_year for resource in self.resources]
        if observed_years != expected_years:
            raise ValueError("O âmbito BASE tem anos em falta, duplicados ou fora de ordem")
        if self.closed_through_year != self.rolling_year - 1:
            raise ValueError("O ano corrente BASE nunca pode ser classificado como fechado")
        if self.resource_count != len(self.resources):
            raise ValueError("A contagem do âmbito BASE não corresponde aos recursos")
        for resource in self.resources:
            expected_state = (
                BaseCatalogueCoverageState.CURRENT_ROLLING_YEAR
                if resource.resource_year == self.rolling_year
                else BaseCatalogueCoverageState.HISTORICAL_CLOSED_YEAR
            )
            if resource.coverage_state is not expected_state:
                raise ValueError("O estado temporal de um recurso BASE é incoerente")
            if resource.source_modified_at > self.retrieved_at:
                raise ValueError("A atualização declarada de um recurso BASE não pode ser futura")
        if self.catalogue_updated_at > self.retrieved_at:
            raise ValueError("A atualização declarada do catálogo não pode ser futura")
        return self
