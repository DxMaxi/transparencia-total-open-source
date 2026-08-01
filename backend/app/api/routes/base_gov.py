from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import get_settings
from app.core.security import require_admin_key
from app.models.api import BaseContractCollection, BaseDatasetResource
from app.services.base_gov import BaseGovCollector
from app.services.http import OfficialHttpClient

router = APIRouter(prefix="/base", tags=["Portal BASE"])


@router.get("/resources/{year}", response_model=BaseDatasetResource)
async def resource(year: int) -> BaseDatasetResource:
    settings = get_settings()
    try:
        async with OfficialHttpClient(settings) as http:
            return await BaseGovCollector(settings, http).discover_resource(year)
    except (httpx.HTTPError, LookupError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/contracts/preview",
    response_model=BaseContractCollection,
    dependencies=[Depends(require_admin_key)],
)
async def contracts_preview(
    year: int,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> BaseContractCollection:
    settings = get_settings()
    try:
        async with OfficialHttpClient(settings) as http:
            return await BaseGovCollector(settings, http).collect(year, limit=limit)
    except (httpx.HTTPError, LookupError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
