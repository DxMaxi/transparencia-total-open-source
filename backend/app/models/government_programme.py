"""Contratos do catálogo privado do Programa do Governo."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationInfo, field_validator


class GovernmentProgrammeCatalogueBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    block_id: str = Field(min_length=3, max_length=100)
    part: str = Field(min_length=3, max_length=80)
    area: str = Field(min_length=2, max_length=160)
    section_path: str = Field(min_length=2, max_length=300)
    start_page: int = Field(ge=1, le=2_000)
    start_anchor: str = Field(min_length=2, max_length=300)
    end_page: int = Field(ge=1, le=2_000)
    end_anchor: str | None = Field(default=None, min_length=2, max_length=300)
    expected_candidate_count: int = Field(ge=1, le=10_000)
    expected_block_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("end_page")
    @classmethod
    def _end_page_not_before_start(cls, value: int, info: ValidationInfo) -> int:
        start_page = info.data.get("start_page")
        if isinstance(start_page, int) and value < start_page:
            raise ValueError("A página final do bloco não pode preceder a página inicial")
        return value


class GovernmentProgrammeCatalogueManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    government_number: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=3, max_length=300)
    source_url: HttpUrl
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_byte_size: int = Field(ge=100_000, le=50_000_000)
    source_page_count: int = Field(ge=1, le=2_000)
    source_retrieved_at: datetime
    methodology_version: str = Field(min_length=3, max_length=100)
    parser_version: str = Field(min_length=3, max_length=100)
    scope_statement: str = Field(min_length=20, max_length=1_000)
    expected_candidate_count: int = Field(ge=1, le=10_000)
    expected_catalogue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    blocks: tuple[GovernmentProgrammeCatalogueBlock, ...] = Field(min_length=1, max_length=500)

    @field_validator("source_url")
    @classmethod
    def _official_government_source(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.host != "portugal.gov.pt":
            raise ValueError("O catálogo exige uma fonte HTTPS oficial em portugal.gov.pt")
        return value

    @field_validator("blocks")
    @classmethod
    def _unique_blocks(
        cls,
        value: tuple[GovernmentProgrammeCatalogueBlock, ...],
    ) -> tuple[GovernmentProgrammeCatalogueBlock, ...]:
        identifiers = [block.block_id for block in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Os identificadores dos blocos têm de ser únicos")
        return value


class GovernmentPromiseCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_key: str = Field(min_length=16, max_length=100)
    block_id: str
    ordinal: int = Field(ge=1)
    parent_ordinal: int | None = Field(default=None, ge=1)
    hierarchy_level: int = Field(ge=1, le=3)
    source_marker: str = Field(min_length=1, max_length=20)
    area: str
    section_path: str
    programme_page_start: int = Field(ge=1)
    programme_page_end: int = Field(ge=1)
    statement_text: str = Field(min_length=3, max_length=12_000)
    statement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_locator_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentProgrammeCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    block_id: str
    part: str
    area: str
    section_path: str
    start_page: int
    end_page: int
    start_anchor: str
    end_anchor: str | None
    candidate_count: int = Field(ge=1)
    block_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GovernmentProgrammeCatalogue(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_byte_size: int
    source_page_count: int
    layout_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalogue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[GovernmentPromiseCandidate, ...]
    coverage: tuple[GovernmentProgrammeCoverage, ...]
