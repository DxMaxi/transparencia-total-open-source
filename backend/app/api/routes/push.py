import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_repository
from app.core.config import get_settings
from app.core.security import require_admin_key
from app.models.api import (
    PushBroadcastRequest,
    PushBroadcastResponse,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
)
from app.repositories.postgres import PostgresRepository
from app.services.push import PushService

router = APIRouter(prefix="/push", tags=["Notificações push"])
Repository = Annotated[PostgresRepository, Depends(get_repository)]
Admin = Annotated[None, Depends(require_admin_key)]


@router.post("/subscriptions", response_model=PushSubscriptionResponse, status_code=201)
async def create_subscription(
    payload: PushSubscriptionRequest,
    repository: Repository,
) -> PushSubscriptionResponse:
    try:
        subscription_id = await repository.save_push_subscription(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PushSubscriptionResponse(accepted=True, id=subscription_id)


@router.post("/broadcast", response_model=PushBroadcastResponse)
async def broadcast(
    payload: PushBroadcastRequest,
    repository: Repository,
    _admin: Admin,
) -> PushBroadcastResponse:
    settings = get_settings()
    if settings.vapid_private_key is None:
        raise HTTPException(status_code=503, detail="VAPID_PRIVATE_KEY não configurada")
    subscriptions = await repository.list_active_push_subscriptions(
        district=payload.district,
        municipality=payload.municipality,
    )
    push_payload = payload.model_dump(
        include={"title", "body", "url", "tag"},
        exclude_none=True,
    )
    try:
        sent, failed = await asyncio.to_thread(
            PushService(settings).broadcast,
            subscriptions,
            push_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PushBroadcastResponse(selected=len(subscriptions), sent=sent, failed=failed)
