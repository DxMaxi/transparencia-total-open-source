import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import get_settings
from app.core.security import require_admin_key
from app.models.api import ParliamentDataset
from app.services.http import OfficialHttpClient
from app.services.parlamento import ParlamentoCollector

router = APIRouter(
    prefix="/parliament",
    tags=["Assembleia da República"],
    dependencies=[Depends(require_admin_key)],
)


@router.get("/deputies", response_model=ParliamentDataset)
async def deputies(
    legislature: str = Query(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$"),
) -> ParliamentDataset:
    settings = get_settings()
    try:
        async with OfficialHttpClient(settings) as http:
            return await ParlamentoCollector(settings, http).collect_deputies(legislature)
    except (httpx.HTTPError, ValueError, LookupError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/votes", response_model=ParliamentDataset)
async def votes(
    legislature: str = Query(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$"),
) -> ParliamentDataset:
    settings = get_settings()
    try:
        async with OfficialHttpClient(settings) as http:
            return await ParlamentoCollector(settings, http).collect_votes(legislature)
    except (httpx.HTTPError, ValueError, LookupError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
