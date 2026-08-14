from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.api.routes import (
    ai,
    base_gov,
    dre,
    editorial,
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
from app.core.staff_auth import SupabaseJwtVerifier
from app.repositories.official_index_staging import OfficialIndexStagingRepository

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Liga apenas dependências necessárias para servir pedidos.

    Recolhas, migrações e publicações são operações separadas e controladas.
    Um reinício da API nunca deve alterar dados públicos nem contactar fontes oficiais.
    """

    repository = OfficialIndexStagingRepository(settings)
    staff_auth = SupabaseJwtVerifier(settings)
    await repository.connect()
    app.state.repository = repository
    app.state.staff_auth = staff_auth
    try:
        yield
    finally:
        await staff_auth.close()
        await repository.close()


app = FastAPI(
    title=settings.app_name,
    version="0.5.0-alpha.0",
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
    allow_headers=["Authorization", "Content-Type", "X-Admin-Key"],
)


@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "0")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    )
    development_docs = settings.environment != "production" and (
        request.url.path.startswith("/docs") or request.url.path.startswith("/redoc")
    )
    if not development_docs:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
    if settings.environment in {"staging", "production"}:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    if request.url.path == f"{settings.api_prefix}/right-of-reply":
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(parliament.router, prefix=settings.api_prefix)
app.include_router(dre.router, prefix=settings.api_prefix)
app.include_router(editorial.router, prefix=settings.api_prefix)
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
        "documentation": "/docs"
        if settings.environment != "production"
        else "disabled",
    }
