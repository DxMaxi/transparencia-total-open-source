from datetime import date
from typing import Annotated, Literal

import asyncpg
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
    PublishedParliamentExplorer,
    PublishedParliamentPublicationHistoryItem,
)
from app.models.public_politicians import PublishedPoliticianDirectory
from app.repositories.postgres import PostgresRepository
from app.repositories.public_parliament import PublicParliamentRepository
from app.repositories.public_politicians import (
    PublicPoliticianCursorError,
    PublicPoliticianRepository,
)

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
    try:
        data = await repository.get_public_data_status()
    except (
        RuntimeError,
        OSError,
        TimeoutError,
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O servi?o de dados est? temporariamente indispon?vel.",
        ) from exc
    return PublicDataStatus.model_validate(data)


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


@router.get("/politicians/explore", response_model=PublishedPoliticianDirectory)
async def public_politician_directory(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    q: str | None = Query(default=None, max_length=120),
    party_short: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=24, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
) -> PublishedPoliticianDirectory:
    """Pesquisa apenas identidades publicadas; nunca associa pessoas por semelhança."""

    query = q.strip() if q and q.strip() else None
    party = party_short.strip() if party_short and party_short.strip() else None
    _cache(response)
    try:
        result = await PublicPoliticianRepository(repository.pool).explore(
            query=query,
            party_short=party,
            limit=limit,
            cursor=cursor,
        )
    except PublicPoliticianCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return PublishedPoliticianDirectory.model_validate(result)


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


@router.get("/parliament/explore", response_model=PublishedParliamentExplorer)
async def public_parliament_explorer(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    kind: Literal["sessions", "initiatives", "votes"] = Query(default="votes"),
    legislature: str = Query(default="XVII", pattern=r"^[A-Z0-9.ª ]{1,20}$"),
    q: str | None = Query(default=None, max_length=120),
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    initiative_type: str | None = Query(default=None, max_length=120),
    initiative_status: str | None = Query(default=None, max_length=200),
    vote_result: str | None = Query(default=None, max_length=200),
    is_nominal: bool | None = Query(default=None),
    party_source_id: str | None = Query(default=None, min_length=1, max_length=200),
    choice: Literal["FAVOR", "AGAINST", "ABSTENTION", "ABSENT", "UNKNOWN"] | None = Query(
        default=None
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> PublishedParliamentExplorer:
    """Pesquisa apenas a fotografia revista; filtros de partido usam ID oficial exato."""

    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A data inicial não pode ser posterior à data final",
        )
    query = q.strip() if q and q.strip() else None
    _cache(response)
    try:
        result = await PublicParliamentRepository(repository.pool).explore(
            kind=kind,
            legislature=legislature,
            query=query,
            date_from=date_from,
            date_to=date_to,
            initiative_type=initiative_type,
            initiative_status=initiative_status,
            vote_result=vote_result,
            is_nominal=is_nominal,
            party_source_id=party_source_id,
            choice=choice,
            limit=limit,
            offset=offset,
        )
    except RuntimeError as exc:
        raise _unavailable(exc) from exc
    return PublishedParliamentExplorer.model_validate(result)


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
