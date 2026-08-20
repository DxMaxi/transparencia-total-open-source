from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_editorial_staff
from app.models.api import (
    CitizenGuideRequest,
    CitizenGuideResponse,
    SummaryRequest,
    SummaryResponse,
)
from app.models.editorial import StaffSession

router = APIRouter(prefix="/ai", tags=["IA — resumos cidadãos"])


@router.post("/summaries", response_model=SummaryResponse)
async def summarize(
    request: SummaryRequest,
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> SummaryResponse:
    del request, _actor
    raise HTTPException(
        status_code=410,
        detail=(
            "Geração direta desativada. Use o circuito editorial privado baseado num snapshot "
            "oficial arquivado e atestado."
        ),
    )


@router.post("/civic-guide", response_model=CitizenGuideResponse)
async def civic_guide(
    request: CitizenGuideRequest,
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> CitizenGuideResponse:
    del request, _actor
    raise HTTPException(
        status_code=410,
        detail=(
            "O Guia do Cidadão permanece indisponível até existir persistência privada e "
            "revisão humana específica para este tipo de proposta."
        ),
    )
