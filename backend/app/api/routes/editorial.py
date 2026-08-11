"""Endpoints privados para revisão humana e adaptadores de publicação por domínio."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.dependencies import (
    get_editorial_repository,
    get_parliament_editorial_publication_repository,
    get_parliament_editorial_repository,
    get_staff_session,
    require_editorial_admin,
    require_editorial_staff,
)
from app.models.editorial import (
    EditorialAction,
    EditorialApprovalRequest,
    EditorialCaseCreateRequest,
    EditorialCaseKind,
    EditorialCorrectionRequest,
    EditorialDecisionRequest,
    EditorialState,
    ParliamentEditorialProposalRequest,
    ParliamentEditorialPublicationRequest,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.parliament_editorial_publication import (
    ParliamentEditorialPublicationRepository,
)

router = APIRouter(prefix="/editorial", tags=["Painel editorial V5"])


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EditorialNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, EditorialSourceError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    if isinstance(exc, EditorialConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Erro editorial inesperado",
    )


@router.get("/session")
async def session(
    actor: Annotated[StaffSession, Depends(get_staff_session)],
) -> StaffSession:
    """Permite completar MFA depois de confirmar que a conta pertence à equipa."""

    return actor


@router.get("/parliament/snapshots")
async def parliament_snapshots(
    repository: Annotated[
        ParliamentEditorialRepository,
        Depends(get_parliament_editorial_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    legislature: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[dict[str, object]]:
    """Mostra snapshots atestados, cobertura e diferenças sem criar processos."""

    return await repository.list_snapshot_candidates(
        legislature=legislature,
        limit=limit,
    )


@router.post("/parliament/proposals")
async def create_parliament_proposal(
    payload: ParliamentEditorialProposalRequest,
    repository: Annotated[
        ParliamentEditorialRepository,
        Depends(get_parliament_editorial_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Cria uma proposta PENDING por âmbito; nunca publica o snapshot."""

    try:
        return await repository.create_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/cases/{case_id}/publication")
async def parliament_publication_preview(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    repository: Annotated[
        ParliamentEditorialPublicationRepository,
        Depends(get_parliament_editorial_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a prova e a elegibilidade sem escrever nem publicar."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post("/parliament/cases/{case_id}/publication")
async def publish_parliament_case(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: ParliamentEditorialPublicationRequest,
    repository: Annotated[
        ParliamentEditorialPublicationRepository,
        Depends(get_parliament_editorial_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Publica só o âmbito derivado de um processo parlamentar aprovado."""

    try:
        return await repository.publish(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/cases")
async def cases(
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    state_filter: Annotated[EditorialState | None, Query(alias="state")] = None,
    kind: EditorialCaseKind | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> dict[str, object]:
    try:
        return await repository.list_cases(
            state=state_filter,
            kind=kind,
            limit=limit,
            cursor=cursor,
        )
    except EditorialConflictError as exc:
        raise _translate_error(exc) from exc


@router.get("/sources")
async def sources(
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[dict[str, object]]:
    return await repository.list_source_candidates(query=q, limit=limit)


@router.post("/cases", status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: EditorialCaseCreateRequest,
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    try:
        return await repository.create_case(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/cases/{case_id}")
async def case_detail(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    try:
        return await repository.get_case(case_id)
    except EditorialNotFoundError as exc:
        raise _translate_error(exc) from exc


@router.post("/cases/{case_id}/start-review")
async def start_review(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: EditorialDecisionRequest,
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    return await _transition(
        repository=repository,
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        payload=payload,
        actor=actor,
        source_confirmed=False,
    )


@router.post("/cases/{case_id}/approve")
async def approve(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: EditorialApprovalRequest,
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    return await _transition(
        repository=repository,
        case_id=case_id,
        action=EditorialAction.APPROVE,
        payload=payload,
        actor=actor,
        source_confirmed=payload.confirm_source_reviewed,
    )


@router.post("/cases/{case_id}/reject")
async def reject(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: EditorialDecisionRequest,
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    return await _transition(
        repository=repository,
        case_id=case_id,
        action=EditorialAction.REJECT,
        payload=payload,
        actor=actor,
        source_confirmed=False,
    )


@router.post("/cases/{case_id}/correct")
async def correct(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: EditorialCorrectionRequest,
    repository: Annotated[EditorialRepository, Depends(get_editorial_repository)],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    try:
        return await repository.correct_case(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError) as exc:
        raise _translate_error(exc) from exc


async def _transition(
    *,
    repository: EditorialRepository,
    case_id: str,
    action: EditorialAction,
    payload: EditorialDecisionRequest,
    actor: StaffSession,
    source_confirmed: bool,
) -> dict[str, object]:
    try:
        return await repository.transition(
            case_id=case_id,
            action=action,
            expected_revision=payload.expected_revision,
            rationale=payload.rationale,
            source_confirmed=source_confirmed,
            actor=actor,
        )
    except (EditorialConflictError, EditorialNotFoundError) as exc:
        raise _translate_error(exc) from exc
