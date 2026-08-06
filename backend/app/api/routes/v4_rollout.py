"""Controlos administrativos do rollout V4, sempre fail-closed."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import get_repository
from app.core.config import get_settings
from app.core.security import require_admin_key
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.postgres import PostgresRepository
from app.services.v4_rollout import RolloutSource, V4RolloutService

router = APIRouter(
    prefix="/admin/v4-rollout",
    tags=["Rollout V4"],
    dependencies=[Depends(require_admin_key)],
)


class IndexSyncRequest(BaseModel):
    sources: list[RolloutSource] = Field(min_length=1, max_length=6)

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, value: list[RolloutSource]) -> list[RolloutSource]:
        return list(dict.fromkeys(value))


class ParliamentPublicationRequest(BaseModel):
    legislature: str = Field(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_count: int = Field(ge=100, le=500)
    reviewer_alias: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=20, max_length=2_000)
    confirm_source_reviewed: bool


@router.get("/parliament/preview")
async def parliament_preview(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    legislature: str = "XVII",
) -> dict[str, object]:
    return await repository.inspect_parliament_people_publication(legislature=legislature)


@router.post("/parliament/publish")
async def parliament_publish(
    payload: ParliamentPublicationRequest,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> dict[str, object]:
    if not payload.confirm_source_reviewed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A publicação exige confirmação humana explícita da fonte",
        )
    return await repository.publish_parliament_people_snapshot(
        legislature=payload.legislature,
        expected_source_sha256=payload.source_sha256,
        expected_count=payload.expected_count,
        reviewer_alias=payload.reviewer_alias,
        rationale=payload.rationale,
    )


@router.post("/official-indexes/sync")
async def sync_official_indexes(
    payload: IndexSyncRequest,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> list[dict[str, object]]:
    staging_repository = cast(OfficialIndexStagingRepository, repository)
    return await V4RolloutService(get_settings(), staging_repository).sync_sources(payload.sources)
