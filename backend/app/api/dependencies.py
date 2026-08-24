from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.staff_auth import (
    InvalidStaffToken,
    StaffAuthUnavailable,
    SupabaseJwtVerifier,
)
from app.models.editorial import StaffRole, StaffSession
from app.repositories.ai_editorial import AiEditorialRepository
from app.repositories.ai_editorial_publication import AiEditorialPublicationRepository
from app.repositories.editorial import EditorialNotFoundError, EditorialRepository
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.parliament_editorial_publication import (
    ParliamentEditorialPublicationRepository,
)
from app.repositories.politician_profile_editorial import (
    PoliticianProfileEditorialRepository,
)
from app.repositories.politician_profile_publication import (
    PoliticianProfilePublicationReadinessRepository,
)
from app.repositories.politician_profile_snapshot_publication import (
    PoliticianProfileSnapshotPublicationRepository,
)
from app.repositories.postgres import PostgresRepository


def get_repository(request: Request) -> PostgresRepository:
    return cast(PostgresRepository, request.app.state.repository)


def get_editorial_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> EditorialRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial não configurada",
        )
    return EditorialRepository(repository.pool)


def get_ai_editorial_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> AiEditorialRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial de IA não configurada",
        )
    return AiEditorialRepository(repository.pool)


def get_ai_editorial_publication_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> AiEditorialPublicationRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial de IA não configurada",
        )
    return AiEditorialPublicationRepository(repository.pool)


def get_parliament_editorial_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> ParliamentEditorialRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial não configurada",
        )
    return ParliamentEditorialRepository(repository.pool)


def get_parliament_editorial_publication_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> ParliamentEditorialPublicationRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial não configurada",
        )
    return ParliamentEditorialPublicationRepository(repository.pool)


def get_politician_profile_editorial_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> PoliticianProfileEditorialRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial não configurada",
        )
    return PoliticianProfileEditorialRepository(repository.pool)


def get_politician_profile_publication_readiness_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> PoliticianProfilePublicationReadinessRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial não configurada",
        )
    return PoliticianProfilePublicationReadinessRepository(repository.pool)


def get_politician_profile_snapshot_publication_repository(
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> PoliticianProfileSnapshotPublicationRepository:
    if repository.pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de dados editorial não configurada",
        )
    return PoliticianProfileSnapshotPublicationRepository(repository.pool)


async def get_staff_session(
    request: Request,
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> StaffSession:
    verifier = cast(SupabaseJwtVerifier, request.app.state.staff_auth)
    try:
        verified = await verifier.verify_bearer(authorization)
        return await repository.staff_session(
            auth_user_id=verified.auth_user_id,
            assurance_level=verified.assurance_level,
        )
    except InvalidStaffToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except StaffAuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except EditorialNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


async def require_editorial_staff(
    session: Annotated[StaffSession, Depends(get_staff_session)],
) -> StaffSession:
    if session.assurance_level != "aal2":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Autenticação multifator obrigatória",
            headers={"X-MFA-Required": "true"},
        )
    return session


async def require_editorial_admin(
    session: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> StaffSession:
    if session.role is not StaffRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta ação pública exige um administrador editorial",
        )
    return session
