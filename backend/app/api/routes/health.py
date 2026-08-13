from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_repository
from app.core.config import get_settings
from app.models.api import HealthResponse
from app.repositories.postgres import PostgresRepository

router = APIRouter(tags=["Sistema"])


async def _database_is_ready(repository: PostgresRepository) -> bool:
    if repository.pool is None:
        return False
    try:
        async with repository.pool.acquire() as connection:
            return bool(await connection.fetchval("SELECT 1"))
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Compatibilidade: confirma que o processo FastAPI está activo."""

    settings = get_settings()
    return HealthResponse(
        environment=settings.environment,
        database_configured=settings.database_url is not None,
        ai_provider=settings.ai_provider,
        public_capabilities=[
            "parliament_explorer_v1",
            "parliament_publication_history_v1",
        ],
    )


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Liveness: não consulta dependências externas."""

    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> dict[str, object]:
    """Readiness: só aceita tráfego quando o PostgreSQL responde."""

    database_ready = await _database_is_ready(repository)
    if not database_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unavailable",
                "database_ready": False,
            },
        )
    return {
        "status": "ready",
        "database_ready": True,
    }
