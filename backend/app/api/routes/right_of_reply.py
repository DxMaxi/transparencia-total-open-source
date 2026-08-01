from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_repository
from app.models.api import RightOfReplyReceipt, RightOfReplyRequest
from app.repositories.postgres import PostgresRepository
from app.services.right_of_reply import build_right_of_reply_receipt

router = APIRouter(prefix="/right-of-reply", tags=["Direito de resposta"])


@router.post("", response_model=RightOfReplyReceipt, status_code=status.HTTP_202_ACCEPTED)
async def submit_right_of_reply(
    payload: RightOfReplyRequest,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
) -> RightOfReplyReceipt:
    if not repository.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canal indisponível enquanto a base de dados não estiver configurada",
        )
    receipt = build_right_of_reply_receipt(payload)
    try:
        await repository.save_right_of_reply(payload, receipt)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return receipt
