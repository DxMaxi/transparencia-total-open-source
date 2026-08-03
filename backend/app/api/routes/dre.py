import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import get_settings
from app.core.security import require_admin_key
from app.models.api import LegalDocument
from app.services.dre import DreCollector
from app.services.http import OfficialHttpClient

router = APIRouter(
    prefix="/dre",
    tags=["Diário da República"],
    dependencies=[Depends(require_admin_key)],
)


@router.get("/document", response_model=LegalDocument)
async def document(source_url: str = Query(min_length=12, max_length=2048)) -> LegalDocument:
    settings = get_settings()
    try:
        async with OfficialHttpClient(settings) as http:
            return await DreCollector(settings, http).fetch_document(source_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Falha ao consultar a fonte DRE") from exc


@router.get("/rss")
async def rss() -> list[dict[str, str | None]]:
    settings = get_settings()
    try:
        async with OfficialHttpClient(settings) as http:
            return await DreCollector(settings, http).read_rss()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Falha ao consultar o RSS do DRE") from exc
