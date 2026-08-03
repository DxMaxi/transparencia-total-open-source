import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.security import require_admin_key
from app.models.api import TransparencyResource
from app.services.http import OfficialHttpClient
from app.services.transparency_entity import TransparencyEntityCollector

router = APIRouter(
    prefix="/transparency-entity",
    tags=["Entidade para a Transparência"],
    dependencies=[Depends(require_admin_key)],
)


@router.get("/resources", response_model=list[TransparencyResource])
async def resources() -> list[TransparencyResource]:
    settings = get_settings()
    try:
        async with OfficialHttpClient(settings) as http:
            return await TransparencyEntityCollector(settings, http).public_resources()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Falha ao consultar a fonte oficial") from exc
