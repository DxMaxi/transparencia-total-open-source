from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_repository
from app.models.api import (
    PublicDataStatus,
    PublicInvestigatorDataset,
    PublishedPersonSummary,
    PublishedPoliticianProfile,
    PublishedPromise,
)
from app.models.public_parliament import (
    PublishedParliamentaryInitiative,
    PublishedParliamentarySession,
    PublishedParliamentaryVote,
    PublishedParliamentPublicationHistoryItem,
)
from app.repositories.postgres import PostgresRepository
from app.repositories.public_parliament import PublicParliamentRepository

router = APIRouter(prefix="/public", tags=["Leitura pública"])


def _cache(response: Response) -> None:
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"


def _unavailable(exc: RuntimeError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


@router.get("/data-status", response_model=PublicDataStatus)
async def public_data_status(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> PublicDataStatus:
    _cache(response)
    return PublicDataStatus.model_validate(await repository.get_public_data_status())


@router.get("/politicians", response_model=list[PublishedPersonSummary])
async def public_politicians(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[PublishedPersonSummary]:
    _cache(response)
    try:
        rows = await repository.list_public_politicians(limit=limit, offset=offset)
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return [PublishedPersonSummary.model_validate(row) for row in rows]


@router.get("/politicians/{slug}", response_model=PublishedPoliticianProfile)
async def public_politician_profile(
    slug: str,
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> PublishedPoliticianProfile:
    _cache(response)
    try:
        row = await repository.get_public_politician(slug)
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Perfil público não encontrado")
    return PublishedPoliticianProfile.model_validate(row)


@router.get("/promises", response_model=list[PublishedPromise])
async def public_promises(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    limit: int = Query(default=250, ge=1, le=1_000),
    offset: int = Query(default=0, ge=0),
) -> list[PublishedPromise]:
    _cache(response)
    try:
        rows = await repository.list_public_promises(limit=limit, offset=offset)
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return [PublishedPromise.model_validate(row) for row in rows]


@router.get("/investigator", response_model=PublicInvestigatorDataset)
async def public_investigator(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    limit: int = Query(default=200, ge=1, le=500),
) -> PublicInvestigatorDataset:
    _cache(response)
    try:
        row = await repository.get_public_investigator_dataset(limit=limit)
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return PublicInvestigatorDataset.model_validate(row)


@router.get("/parliament/sessions", response_model=list[PublishedParliamentarySession])
async def public_parliament_sessions(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    legislature: str = Query(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[PublishedParliamentarySession]:
    _cache(response)
    try:
        rows = await PublicParliamentRepository(repository.pool).list_sessions(
            legislature=legislature,
            limit=limit,
            offset=offset,
        )
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return [PublishedParliamentarySession.model_validate(row) for row in rows]


@router.get(
    "/parliament/publication-history",
    response_model=list[PublishedParliamentPublicationHistoryItem],
)
async def public_parliament_publication_history(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    legislature: str = Query(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[PublishedParliamentPublicationHistoryItem]:
    """Publica apenas o resumo redigido das decisões, nunca a nota editorial privada."""

    _cache(response)
    try:
        rows = await PublicParliamentRepository(repository.pool).list_publication_history(
            legislature=legislature,
            limit=limit,
        )
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return [PublishedParliamentPublicationHistoryItem.model_validate(row) for row in rows]


@router.get(
    "/parliament/initiatives",
    response_model=list[PublishedParliamentaryInitiative],
)
async def public_parliament_initiatives(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    legislature: str = Query(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[PublishedParliamentaryInitiative]:
    _cache(response)
    try:
        rows = await PublicParliamentRepository(repository.pool).list_initiatives(
            legislature=legislature,
            limit=limit,
            offset=offset,
        )
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return [PublishedParliamentaryInitiative.model_validate(row) for row in rows]


@router.get("/parliament/votes", response_model=list[PublishedParliamentaryVote])
async def public_parliament_votes(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    legislature: str = Query(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[PublishedParliamentaryVote]:
    _cache(response)
    try:
        rows = await PublicParliamentRepository(repository.pool).list_votes(
            legislature=legislature,
            limit=limit,
            offset=offset,
        )
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return [PublishedParliamentaryVote.model_validate(row) for row in rows]
