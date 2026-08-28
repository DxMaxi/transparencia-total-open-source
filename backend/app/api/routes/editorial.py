"""Endpoints privados para revisão humana e adaptadores de publicação por domínio."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from openai import APIError

from app.api.dependencies import (
    get_ai_editorial_publication_repository,
    get_ai_editorial_repository,
    get_editorial_repository,
    get_ept_declaration_editorial_repository,
    get_parliament_editorial_publication_repository,
    get_parliament_editorial_repository,
    get_politician_attendance_editorial_repository,
    get_politician_attendance_publication_repository,
    get_politician_attendance_withdrawal_repository,
    get_politician_initiative_authorship_editorial_repository,
    get_politician_initiative_authorship_publication_repository,
    get_politician_initiative_authorship_withdrawal_repository,
    get_politician_mandate_editorial_repository,
    get_politician_mandate_publication_repository,
    get_politician_mandate_withdrawal_repository,
    get_politician_office_editorial_repository,
    get_politician_office_publication_repository,
    get_politician_office_withdrawal_repository,
    get_politician_profile_editorial_repository,
    get_politician_profile_publication_readiness_repository,
    get_politician_profile_snapshot_publication_repository,
    get_politician_profile_snapshot_withdrawal_repository,
    get_staff_session,
    require_editorial_admin,
    require_editorial_staff,
)
from app.core.config import get_settings
from app.models.editorial import (
    AiDreProposalRequest,
    AiDreRegenerationRequest,
    AiEditorialPublicationRequest,
    AiEditorialWithdrawalRequest,
    EditorialAction,
    EditorialApprovalRequest,
    EditorialCaseCreateRequest,
    EditorialCaseKind,
    EditorialCorrectionRequest,
    EditorialDecisionRequest,
    EditorialState,
    ParliamentEditorialProposalRequest,
    ParliamentEditorialPublicationRequest,
    ParliamentEditorialWithdrawalRequest,
    PoliticianAttendanceEditorialProposalRequest,
    PoliticianAttendancePublicationRequest,
    PoliticianAttendanceWithdrawalRequest,
    PoliticianInitiativeAuthorshipEditorialProposalRequest,
    PoliticianInitiativeAuthorshipPublicationRequest,
    PoliticianInitiativeAuthorshipWithdrawalRequest,
    PoliticianMandateEditorialProposalRequest,
    PoliticianMandatePublicationRequest,
    PoliticianMandateWithdrawalRequest,
    PoliticianOfficeEditorialProposalRequest,
    PoliticianOfficePublicationRequest,
    PoliticianOfficeWithdrawalRequest,
    PoliticianProfileEditorialProposalRequest,
    PoliticianProfileSnapshotPublicationRequest,
    PoliticianProfileSnapshotWithdrawalRequest,
    StaffSession,
)
from app.models.ept_declaration import EptPublicInterestEditorialProposalRequest
from app.repositories.ai_editorial import AiEditorialRepository
from app.repositories.ai_editorial_publication import AiEditorialPublicationRepository
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.ept_declaration_editorial import EptDeclarationEditorialRepository
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.parliament_editorial_publication import (
    ParliamentEditorialPublicationRepository,
)
from app.repositories.politician_attendance_editorial import (
    PoliticianAttendanceEditorialRepository,
)
from app.repositories.politician_attendance_publication import (
    PoliticianAttendancePublicationRepository,
)
from app.repositories.politician_attendance_withdrawal import (
    PoliticianAttendanceWithdrawalRepository,
)
from app.repositories.politician_initiative_authorship_editorial import (
    PoliticianInitiativeAuthorshipEditorialRepository,
)
from app.repositories.politician_initiative_authorship_publication import (
    PoliticianInitiativeAuthorshipPublicationRepository,
)
from app.repositories.politician_initiative_authorship_withdrawal import (
    PoliticianInitiativeAuthorshipWithdrawalRepository,
)
from app.repositories.politician_mandate_editorial import (
    PoliticianMandateEditorialRepository,
)
from app.repositories.politician_mandate_publication import (
    PoliticianMandatePublicationRepository,
)
from app.repositories.politician_mandate_withdrawal import (
    PoliticianMandateWithdrawalRepository,
)
from app.repositories.politician_office_editorial import (
    PoliticianOfficeEditorialRepository,
)
from app.repositories.politician_office_publication import (
    PoliticianOfficePublicationRepository,
)
from app.repositories.politician_office_withdrawal import (
    PoliticianOfficeWithdrawalRepository,
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
from app.repositories.politician_profile_snapshot_withdrawal import (
    PoliticianProfileSnapshotWithdrawalRepository,
)
from app.services.ai_editorial import AiEditorialService, AiGenerationError
from app.services.ai_summarizer import get_summarizer

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


@router.get("/ept/public-interest-candidates")
async def ept_public_interest_candidates(
    repository: Annotated[
        EptDeclarationEditorialRepository,
        Depends(get_ept_declaration_editorial_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    """Lista metadados privados; não devolve HMAC nem associa pessoas por nome."""

    return await repository.list_candidates(query=q, limit=limit, offset=offset)


@router.post("/ept/public-interest-proposals", status_code=status.HTTP_201_CREATED)
async def create_ept_public_interest_proposal(
    payload: EptPublicInterestEditorialProposalRequest,
    repository: Annotated[
        EptDeclarationEditorialRepository,
        Depends(get_ept_declaration_editorial_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Cria um caso PENDING sem ligar identidade, rever juridicamente ou publicar."""

    try:
        return await repository.create_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


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


@router.get("/parliament/deputies")
async def parliament_deputy_candidates(
    repository: Annotated[
        PoliticianProfileEditorialRepository,
        Depends(get_politician_profile_editorial_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    legislature: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    """Compara observações separadas por DepId sem criar identidades ou revisões."""

    return await repository.list_candidates(
        legislature=legislature,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.post("/parliament/deputy-proposals", status_code=status.HTTP_201_CREATED)
async def create_parliament_deputy_proposal(
    payload: PoliticianProfileEditorialProposalRequest,
    repository: Annotated[
        PoliticianProfileEditorialRepository,
        Depends(get_politician_profile_editorial_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Cria um perfil PENDING a partir de uma observação; nunca publica nem infere mandato."""

    try:
        return await repository.create_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/mandate-candidates")
async def parliament_mandate_candidates(
    repository: Annotated[
        PoliticianMandateEditorialRepository,
        Depends(get_politician_mandate_editorial_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    legislature: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    """Lista intervalos oficiais sem lhes atribuir automaticamente significado jurídico."""

    return await repository.list_candidates(
        legislature=legislature,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.post("/parliament/mandate-proposals", status_code=status.HTTP_201_CREATED)
async def create_parliament_mandate_proposal(
    payload: PoliticianMandateEditorialProposalRequest,
    repository: Annotated[
        PoliticianMandateEditorialRepository,
        Depends(get_politician_mandate_editorial_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Cria um caso PENDING por intervalo; nunca cria ou publica um mandato."""

    try:
        return await repository.create_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/office-candidates")
async def parliament_office_candidates(
    repository: Annotated[
        PoliticianOfficeEditorialRepository,
        Depends(get_politician_office_editorial_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    legislature: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    """Lista cargos oficiais observados sem inferir mandato, filiação ou efeito jurídico."""

    return await repository.list_candidates(
        legislature=legislature,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.post("/parliament/office-proposals", status_code=status.HTTP_201_CREATED)
async def create_parliament_office_proposal(
    payload: PoliticianOfficeEditorialProposalRequest,
    repository: Annotated[
        PoliticianOfficeEditorialRepository,
        Depends(get_politician_office_editorial_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Cria um caso PENDING por cargo exato; nunca cria ou publica um cargo ou mandato."""

    try:
        return await repository.create_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/attendance-candidates")
async def parliament_attendance_candidates(
    repository: Annotated[
        PoliticianAttendanceEditorialRepository,
        Depends(get_politician_attendance_editorial_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    legislature: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    """Lista reuniões integrais atestadas sem criar presenças públicas."""

    return await repository.list_candidates(
        legislature=legislature,
        limit=limit,
        offset=offset,
    )


@router.post("/parliament/attendance-proposals", status_code=status.HTTP_201_CREATED)
async def create_parliament_attendance_proposal(
    payload: PoliticianAttendanceEditorialProposalRequest,
    repository: Annotated[
        PoliticianAttendanceEditorialRepository,
        Depends(get_politician_attendance_editorial_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Cria um caso PENDING para a reunião completa; nunca publica linhas individuais."""

    try:
        return await repository.create_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/initiative-authorship-candidates")
async def parliament_initiative_authorship_candidates(
    repository: Annotated[
        PoliticianInitiativeAuthorshipEditorialRepository,
        Depends(get_politician_initiative_authorship_editorial_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    legislature: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    """Lista autorias individuais declaradas, sem associar pessoas por nome."""

    return await repository.list_candidates(
        legislature=legislature,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/parliament/initiative-authorship-proposals",
    status_code=status.HTTP_201_CREATED,
)
async def create_parliament_initiative_authorship_proposal(
    payload: PoliticianInitiativeAuthorshipEditorialProposalRequest,
    repository: Annotated[
        PoliticianInitiativeAuthorshipEditorialRepository,
        Depends(get_politician_initiative_authorship_editorial_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Cria um caso PENDING por IniId/idCadastro exatos; nunca publica a relação."""

    try:
        return await repository.create_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/initiative-authorship-cases/{case_id}/publication")
async def parliament_initiative_authorship_publication_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianInitiativeAuthorshipPublicationRepository,
        Depends(get_politician_initiative_authorship_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói uma autoria pública sem escrever em qualquer projeção."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/initiative-authorship-cases/{case_id}/publication",
    status_code=status.HTTP_201_CREATED,
)
async def publish_parliament_initiative_authorship(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianInitiativeAuthorshipPublicationRequest,
    repository: Annotated[
        PoliticianInitiativeAuthorshipPublicationRepository,
        Depends(get_politician_initiative_authorship_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Publica uma relação AUTHOR exata numa transação ADMIN com MFA."""

    try:
        return await repository.publish(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/initiative-authorship-cases/{case_id}/withdrawal")
async def parliament_initiative_authorship_withdrawal_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianInitiativeAuthorshipWithdrawalRepository,
        Depends(get_politician_initiative_authorship_withdrawal_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a publicação e o efeito da retirada sem escrever."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/initiative-authorship-cases/{case_id}/withdrawal",
    status_code=status.HTTP_201_CREATED,
)
async def withdraw_parliament_initiative_authorship(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianInitiativeAuthorshipWithdrawalRequest,
    repository: Annotated[
        PoliticianInitiativeAuthorshipWithdrawalRepository,
        Depends(get_politician_initiative_authorship_withdrawal_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Retira a autoria sem apagar ligação, fontes ou prova histórica."""

    try:
        return await repository.withdraw(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/attendance-cases/{case_id}/publication")
async def parliament_attendance_publication_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianAttendancePublicationRepository,
        Depends(get_politician_attendance_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a reunião integral e todos os mapeamentos sem escrever."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/attendance-cases/{case_id}/publication",
    status_code=status.HTTP_201_CREATED,
)
async def publish_parliament_attendance(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianAttendancePublicationRequest,
    repository: Annotated[
        PoliticianAttendancePublicationRepository,
        Depends(get_politician_attendance_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Publica a reunião completa e a prova numa transação ADMIN com MFA."""

    try:
        return await repository.publish(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/attendance-cases/{case_id}/withdrawal")
async def parliament_attendance_withdrawal_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianAttendanceWithdrawalRepository,
        Depends(get_politician_attendance_withdrawal_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a publicação e o efeito integral da retirada sem escrever."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/attendance-cases/{case_id}/withdrawal",
    status_code=status.HTTP_201_CREATED,
)
async def withdraw_parliament_attendance(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianAttendanceWithdrawalRequest,
    repository: Annotated[
        PoliticianAttendanceWithdrawalRepository,
        Depends(get_politician_attendance_withdrawal_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Retira a reunião inteira sem apagar sessão, linhas ou prova histórica."""

    try:
        return await repository.withdraw(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/office-cases/{case_id}/publication")
async def parliament_office_publication_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianOfficePublicationRepository,
        Depends(get_politician_office_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a publicação do cargo sem escrever em qualquer projeção."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/office-cases/{case_id}/publication",
    status_code=status.HTTP_201_CREATED,
)
async def publish_parliament_office(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianOfficePublicationRequest,
    repository: Annotated[
        PoliticianOfficePublicationRepository,
        Depends(get_politician_office_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Publica um cargo e toda a prova numa única transação ADMIN com MFA."""

    try:
        return await repository.publish(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/office-cases/{case_id}/withdrawal")
async def parliament_office_withdrawal_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianOfficeWithdrawalRepository,
        Depends(get_politician_office_withdrawal_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a publicação original e o efeito da retirada sem escrever."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/office-cases/{case_id}/withdrawal",
    status_code=status.HTTP_201_CREATED,
)
async def withdraw_parliament_office(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianOfficeWithdrawalRequest,
    repository: Annotated[
        PoliticianOfficeWithdrawalRepository,
        Depends(get_politician_office_withdrawal_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Retira um cargo da projeção ativa sem apagar qualquer prova histórica."""

    try:
        return await repository.withdraw(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/mandate-cases/{case_id}/publication")
async def parliament_mandate_publication_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianMandatePublicationRepository,
        Depends(get_politician_mandate_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a publicação do mandato sem escrever em qualquer projeção."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/mandate-cases/{case_id}/publication",
    status_code=status.HTTP_201_CREATED,
)
async def publish_parliament_mandate(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianMandatePublicationRequest,
    repository: Annotated[
        PoliticianMandatePublicationRepository,
        Depends(get_politician_mandate_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Publica um mandato e toda a sua prova numa única transação ADMIN com MFA."""

    try:
        return await repository.publish(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/mandate-cases/{case_id}/withdrawal")
async def parliament_mandate_withdrawal_preview(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianMandateWithdrawalRepository,
        Depends(get_politician_mandate_withdrawal_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Simula a retirada exata sem alterar o mandato ou a consulta pública."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/parliament/mandate-cases/{case_id}/withdrawal",
    status_code=status.HTTP_201_CREATED,
)
async def withdraw_parliament_mandate(
    case_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianMandateWithdrawalRequest,
    repository: Annotated[
        PoliticianMandateWithdrawalRepository,
        Depends(get_politician_mandate_withdrawal_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Retira a visibilidade e acrescenta prova imutável numa transação ADMIN com MFA."""

    try:
        return await repository.withdraw(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/deputy-snapshots/publication-readiness")
async def parliament_deputy_snapshot_readiness_list(
    repository: Annotated[
        PoliticianProfilePublicationReadinessRepository,
        Depends(get_politician_profile_publication_readiness_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    legislature: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> dict[str, object]:
    """Inspeciona fotografias inteiras sem criar qualquer efeito público."""

    return await repository.list_snapshots(legislature=legislature, limit=limit)


@router.get("/parliament/deputy-snapshots/{snapshot_id}/publication-readiness")
async def parliament_deputy_snapshot_readiness(
    snapshot_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianProfilePublicationReadinessRepository,
        Depends(get_politician_profile_publication_readiness_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a prova de cada perfil aprovado; nunca publica a fotografia."""

    try:
        return await repository.inspect(snapshot_id=snapshot_id)
    except (EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/deputy-snapshots/{snapshot_id}/publication")
async def parliament_deputy_snapshot_publication_preview(
    snapshot_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianProfileSnapshotPublicationRepository,
        Depends(get_politician_profile_snapshot_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói o efeito integral sem escrever em qualquer projeção pública."""

    try:
        return await repository.inspect(snapshot_id=snapshot_id)
    except (EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post("/parliament/deputy-snapshots/{snapshot_id}/publication")
async def publish_parliament_deputy_snapshot(
    snapshot_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianProfileSnapshotPublicationRequest,
    repository: Annotated[
        PoliticianProfileSnapshotPublicationRepository,
        Depends(get_politician_profile_snapshot_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Publica a fotografia inteira; nunca cria mandatos ou filiações inferidas."""

    try:
        return await repository.publish(
            snapshot_id=snapshot_id,
            payload=payload,
            actor=actor,
        )
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/parliament/deputy-snapshots/{snapshot_id}/withdrawal")
async def parliament_deputy_snapshot_withdrawal_preview(
    snapshot_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    repository: Annotated[
        PoliticianProfileSnapshotWithdrawalRepository,
        Depends(get_politician_profile_snapshot_withdrawal_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a publicação integral e o efeito da retirada sem escrever."""

    try:
        return await repository.inspect(snapshot_id=snapshot_id)
    except (EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post("/parliament/deputy-snapshots/{snapshot_id}/withdrawal")
async def withdraw_parliament_deputy_snapshot(
    snapshot_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")],
    payload: PoliticianProfileSnapshotWithdrawalRequest,
    repository: Annotated[
        PoliticianProfileSnapshotWithdrawalRepository,
        Depends(get_politician_profile_snapshot_withdrawal_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Retira todos os perfis da fotografia sem apagar qualquer registo histórico."""

    try:
        return await repository.withdraw(
            snapshot_id=snapshot_id,
            payload=payload,
            actor=actor,
        )
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/ai/dre-snapshots")
async def ai_dre_snapshots(
    repository: Annotated[AiEditorialRepository, Depends(get_ai_editorial_repository)],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, object]:
    """Lista prova DRE novamente verificada, sem devolver o texto jurídico."""

    settings = get_settings()
    service = AiEditorialService(
        repository=repository,
        editorial=EditorialRepository(repository.pool),
        settings=settings,
        summarizer=None,
    )
    return await service.list_dre_snapshots(query=q, limit=limit)


@router.get("/ai/cases/{case_id}/source")
async def ai_dre_case_source(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    repository: Annotated[AiEditorialRepository, Depends(get_ai_editorial_repository)],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50_000)] = 40_000,
) -> dict[str, object]:
    """Devolve a fonte arquivada exata apenas para comparação editorial privada."""

    service = AiEditorialService(
        repository=repository,
        editorial=EditorialRepository(repository.pool),
        settings=get_settings(),
        summarizer=None,
    )
    try:
        return await service.case_source(case_id=case_id, offset=offset, limit=limit)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post("/ai/dre-proposals", status_code=status.HTTP_201_CREATED)
async def create_ai_dre_proposal(
    payload: AiDreProposalRequest,
    repository: Annotated[AiEditorialRepository, Depends(get_ai_editorial_repository)],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Gera e persiste uma proposta privada; nunca publica o resumo."""

    settings = get_settings()
    if settings.ai_provider == "disabled":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline editorial de IA desativado",
        )
    try:
        service = AiEditorialService(
            repository=repository,
            editorial=EditorialRepository(repository.pool),
            settings=settings,
            summarizer=get_summarizer(settings),
        )
        return await service.create_dre_proposal(payload=payload, actor=actor)
    except (EditorialConflictError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc
    except (APIError, AiGenerationError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha temporária no fornecedor de IA; nenhuma proposta foi criada",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuração do pipeline editorial de IA inválida",
        ) from exc


@router.post("/ai/cases/{case_id}/regenerate")
async def regenerate_ai_dre_proposal(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: AiDreRegenerationRequest,
    repository: Annotated[AiEditorialRepository, Depends(get_ai_editorial_repository)],
    actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Acrescenta uma nova versão AI privada; nunca substitui nem publica a anterior."""

    settings = get_settings()
    if settings.ai_provider == "disabled":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline editorial de IA desativado",
        )
    try:
        service = AiEditorialService(
            repository=repository,
            editorial=EditorialRepository(repository.pool),
            settings=settings,
            summarizer=get_summarizer(settings),
        )
        return await service.regenerate_dre_proposal(
            case_id=case_id,
            payload=payload,
            actor=actor,
        )
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc
    except (APIError, AiGenerationError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha temporária no fornecedor de IA; nenhuma versão foi criada",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuração do pipeline editorial de IA inválida",
        ) from exc


@router.get("/ai/cases/{case_id}/publication")
async def ai_publication_preview(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    repository: Annotated[
        AiEditorialPublicationRepository,
        Depends(get_ai_editorial_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Reconstrói a projeção pública exata, sem escrever nem chamar o modelo."""

    try:
        return await repository.inspect(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post("/ai/cases/{case_id}/publication")
async def publish_ai_case(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: AiEditorialPublicationRequest,
    repository: Annotated[
        AiEditorialPublicationRepository,
        Depends(get_ai_editorial_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Publica uma versão DRE aprovada, rotulada como IA e revista por humano."""

    try:
        return await repository.publish(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.get("/ai/cases/{case_id}/withdrawal")
async def ai_withdrawal_preview(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    repository: Annotated[
        AiEditorialPublicationRepository,
        Depends(get_ai_editorial_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Mostra a prova publicada e o efeito da retirada sem escrever."""

    try:
        return await repository.inspect_withdrawal(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post("/ai/cases/{case_id}/withdrawal")
async def withdraw_ai_case(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: AiEditorialWithdrawalRequest,
    repository: Annotated[
        AiEditorialPublicationRepository,
        Depends(get_ai_editorial_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Retira a explicação ativa sem apagar a versão ou qualquer evento anterior."""

    try:
        return await repository.withdraw(case_id=case_id, payload=payload, actor=actor)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
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


@router.get("/parliament/cases/{case_id}/withdrawal")
async def parliament_withdrawal_preview(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    repository: Annotated[
        ParliamentEditorialPublicationRepository,
        Depends(get_parliament_editorial_publication_repository),
    ],
    _actor: Annotated[StaffSession, Depends(require_editorial_staff)],
) -> dict[str, object]:
    """Simula a retirada e o eventual recuo público sem escrever."""

    try:
        return await repository.inspect_withdrawal(case_id=case_id)
    except (EditorialConflictError, EditorialNotFoundError, EditorialSourceError) as exc:
        raise _translate_error(exc) from exc


@router.post("/parliament/cases/{case_id}/withdrawal")
async def withdraw_parliament_case(
    case_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: ParliamentEditorialWithdrawalRequest,
    repository: Annotated[
        ParliamentEditorialPublicationRepository,
        Depends(get_parliament_editorial_publication_repository),
    ],
    actor: Annotated[StaffSession, Depends(require_editorial_admin)],
) -> dict[str, object]:
    """Retira só o âmbito derivado e preserva publicação, versão e prova."""

    try:
        return await repository.withdraw(case_id=case_id, payload=payload, actor=actor)
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
