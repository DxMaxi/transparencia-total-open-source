"""Consulta V5.53 sem cache tolerante a conteúdo retirado."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.dependencies import get_repository
from app.core.public_database_errors import (
    PUBLIC_DATABASE_BOUNDARY_ERRORS,
    is_public_database_unavailable,
)
from app.models.public_organisations import (
    PublishedOrganisation,
    PublishedOrganisationHistory,
    PublishedOrganisationList,
)
from app.repositories.postgres import PostgresRepository
from app.repositories.public_organisations import PublicOrganisationRepository

router = APIRouter(prefix="/public/organisations", tags=["Organizações públicas"])


def _fresh(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"


def _unavailable(exc: BaseException) -> HTTPException:
    if not is_public_database_unavailable(exc):
        raise exc
    return HTTPException(
        503, "A consulta pública de organizações está temporariamente indisponível."
    )


@router.get("", response_model=PublishedOrganisationList)
async def list_public_organisations(
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> PublishedOrganisationList:
    _fresh(response)
    try:
        result = await PublicOrganisationRepository(repository.pool).list(
            limit=limit, offset=offset
        )
    except PUBLIC_DATABASE_BOUNDARY_ERRORS as exc:
        raise _unavailable(exc) from exc
    return PublishedOrganisationList.model_validate(result)


@router.get("/{public_id}/publication-history", response_model=PublishedOrganisationHistory)
async def public_organisation_history(
    public_id: str,
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> PublishedOrganisationHistory:
    _fresh(response)
    try:
        rows = await PublicOrganisationRepository(repository.pool).history(public_id=public_id)
    except PUBLIC_DATABASE_BOUNDARY_ERRORS as exc:
        raise _unavailable(exc) from exc
    if rows is None:
        raise HTTPException(404, "Histórico público não encontrado")
    return PublishedOrganisationHistory.model_validate(rows)


@router.get("/{public_id}", response_model=PublishedOrganisation)
async def public_organisation(
    public_id: str,
    response: Response,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> PublishedOrganisation:
    _fresh(response)
    try:
        row = await PublicOrganisationRepository(repository.pool).get(public_id=public_id)
    except PUBLIC_DATABASE_BOUNDARY_ERRORS as exc:
        raise _unavailable(exc) from exc
    if row is None:
        raise HTTPException(404, "Organização não publicada ou retirada")
    return PublishedOrganisation.model_validate(row)
