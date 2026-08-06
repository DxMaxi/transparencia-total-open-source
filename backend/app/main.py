import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    ai,
    base_gov,
    dre,
    health,
    open_data,
    parliament,
    public_data,
    push,
    right_of_reply,
    transparency,
    v4_rollout,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.v4_rollout import DEFAULT_ROLLOUT_SOURCES, V4RolloutService

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


async def _refresh_v4_indexes(repository: OfficialIndexStagingRepository) -> None:
    try:
        await V4RolloutService(settings, repository).sync_sources(
            list(DEFAULT_ROLLOUT_SOURCES)
        )
    except Exception:
        logger.exception("v4_official_index_refresh_failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    repository = OfficialIndexStagingRepository(settings)
    await repository.connect()
    app.state.repository = repository
    refresh_task: asyncio.Task[None] | None = None
    if settings.environment == "production" and repository.configured:
        refresh_task = asyncio.create_task(_refresh_v4_indexes(repository))
    try:
        yield
    finally:
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await refresh_task
        await repository.close()


app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description=(
        "API de recolha e normalização de fontes públicas portuguesas. "
        "Cada resposta preserva a origem oficial."
    ),
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(parliament.router, prefix=settings.api_prefix)
app.include_router(dre.router, prefix=settings.api_prefix)
app.include_router(ai.router, prefix=settings.api_prefix)
app.include_router(push.router, prefix=settings.api_prefix)
app.include_router(transparency.router, prefix=settings.api_prefix)
app.include_router(base_gov.router, prefix=settings.api_prefix)
app.include_router(right_of_reply.router, prefix=settings.api_prefix)
app.include_router(open_data.router, prefix=settings.api_prefix)
app.include_router(public_data.router, prefix=settings.api_prefix)
app.include_router(v4_rollout.router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "health": f"{settings.api_prefix}/health",
        "documentation": "/docs" if settings.environment != "production" else "disabled",
    }
