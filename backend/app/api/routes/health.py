from fastapi import APIRouter

from app.core.config import get_settings
from app.models.api import HealthResponse

router = APIRouter(tags=["Sistema"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        environment=settings.environment,
        database_configured=settings.database_url is not None,
        ai_provider=settings.ai_provider,
    )
