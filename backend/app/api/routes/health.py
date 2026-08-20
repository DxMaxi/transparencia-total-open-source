from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_repository
from app.core.config import get_settings
from app.models.api import HealthResponse
from app.repositories.postgres import PostgresRepository

router = APIRouter(tags=["Sistema"])

_CORE_PUBLIC_CAPABILITIES = [
    "parliament_explorer_v1",
    "parliament_publication_history_v1",
]
_AI_PUBLIC_REQUIRED_RELATIONS = [
    "public._prisma_migrations",
    "public.audit_events",
    "public.data_publication_reviews",
    "public.dre_document_snapshots",
    "public.editorial_cases",
    "public.editorial_publication_events",
    "public.editorial_versions",
    "public.source_archive_attestations",
    "public.source_documents",
    "public.sync_runs",
]
_AI_PUBLIC_REQUIRED_MIGRATIONS = [
    "20260801000000_init",
    "20260801010000_v2_civic_graph",
    "20260803070000_v4_raw_evidence_archive",
    "20260803100000_v4_4_dre_staging",
    "20260811110000_v5_editorial_foundation",
    "20260811133000_v5_editorial_withdrawal_cycle",
    "20260813150000_v5_harden_default_privileges",
]


async def _database_is_ready(repository: PostgresRepository) -> bool:
    if repository.pool is None:
        try:
            await repository.connect()
        except Exception:
            return False
    if repository.pool is None:
        return False
    try:
        async with repository.pool.acquire() as connection:
            return bool(await connection.fetchval("SELECT 1"))
    except Exception:
        return False


async def _ai_public_schema_is_ready(repository: PostgresRepository) -> bool:
    """Só anuncia a V5.15 quando o schema remoto exato está comprovado read-only."""

    if repository.pool is None:
        try:
            await repository.connect()
        except Exception:
            return False
    if repository.pool is None:
        return False
    try:
        async with repository.pool.acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    WITH required_relations(name) AS (
                        SELECT unnest($1::text[])
                    ), relation_gate AS (
                        SELECT COUNT(*) = $2 AS ready
                        FROM required_relations
                        WHERE to_regclass(name) IS NOT NULL
                    ), migration_gate AS (
                        SELECT COUNT(*) = $4 AS ready
                        FROM "_prisma_migrations"
                        WHERE migration_name = ANY($3::text[])
                          AND finished_at IS NOT NULL
                          AND rolled_back_at IS NULL
                    )
                    SELECT relation_gate.ready AND migration_gate.ready
                    FROM relation_gate CROSS JOIN migration_gate
                    """,
                    _AI_PUBLIC_REQUIRED_RELATIONS,
                    len(_AI_PUBLIC_REQUIRED_RELATIONS),
                    _AI_PUBLIC_REQUIRED_MIGRATIONS,
                    len(_AI_PUBLIC_REQUIRED_MIGRATIONS),
                )
            )
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
async def health(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> HealthResponse:
    """Compatibilidade: confirma que o processo FastAPI está activo."""

    settings = get_settings()
    capabilities = list(_CORE_PUBLIC_CAPABILITIES)
    if await _ai_public_schema_is_ready(repository):
        capabilities.append("ai_explanations_v1")
    return HealthResponse(
        environment=settings.environment,
        database_configured=settings.database_url is not None,
        ai_provider=settings.ai_provider,
        public_capabilities=capabilities,
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
