import asyncio
import hashlib
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_repository
from app.core.config import get_settings
from app.core.rate_limit import (
    PUSH_BROADCAST_POLICY,
    PUSH_SUBSCRIPTION_POLICY,
    enforce_public_write_rate_limit,
)
from app.core.security import require_admin_key
from app.models.api import (
    PushBroadcastRequest,
    PushBroadcastResponse,
    PushSubscriptionRemovalRequest,
    PushSubscriptionRemovalResponse,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
)
from app.repositories.postgres import PostgresRepository
from app.services.push import PushService

router = APIRouter(prefix="/push", tags=["Notificações push"])
Repository = Annotated[PostgresRepository, Depends(get_repository)]
Admin = Annotated[None, Depends(require_admin_key)]

_PUSH_DATABASE_ERRORS = (
    RuntimeError,
    OSError,
    TimeoutError,
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
)


def _push_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="O serviço de alertas está temporariamente indisponível.",
    )


@router.post("/subscriptions", response_model=PushSubscriptionResponse, status_code=201)
async def create_subscription(
    request: Request,
    payload: PushSubscriptionRequest,
    repository: Repository,
) -> PushSubscriptionResponse:
    if not repository.configured:
        raise _push_unavailable()
    enforce_public_write_rate_limit(
        request,
        bucket="push_subscription",
        policy=PUSH_SUBSCRIPTION_POLICY,
    )
    try:
        subscription_id = await repository.save_push_subscription(payload)
    except _PUSH_DATABASE_ERRORS as exc:
        raise _push_unavailable() from exc
    return PushSubscriptionResponse(accepted=True, id=subscription_id)


@router.delete("/subscriptions", response_model=PushSubscriptionRemovalResponse)
async def remove_subscription(
    request: Request,
    payload: PushSubscriptionRemovalRequest,
    repository: Repository,
) -> PushSubscriptionRemovalResponse:
    if not repository.configured:
        raise _push_unavailable()
    enforce_public_write_rate_limit(
        request,
        bucket="push_subscription",
        policy=PUSH_SUBSCRIPTION_POLICY,
    )
    try:
        await repository.remove_push_subscription(str(payload.endpoint))
    except _PUSH_DATABASE_ERRORS as exc:
        raise _push_unavailable() from exc
    return PushSubscriptionRemovalResponse()


@router.post("/broadcast", response_model=PushBroadcastResponse)
async def broadcast(
    request: Request,
    payload: PushBroadcastRequest,
    repository: Repository,
    _admin: Admin,
) -> PushBroadcastResponse:
    settings = get_settings()
    if not repository.configured or settings.vapid_private_key is None:
        raise _push_unavailable()
    enforce_public_write_rate_limit(
        request,
        bucket="push_broadcast",
        policy=PUSH_BROADCAST_POLICY,
    )
    try:
        alert = await repository.get_publishable_push_alert(payload.alert_id)
        if alert is None:
            raise HTTPException(
                status_code=404,
                detail="Alerta aprovado e publicável não encontrado.",
            )
        subscriptions = await repository.list_active_push_subscriptions(
            municipality=alert.get("municipality"),
        )
    except _PUSH_DATABASE_ERRORS as exc:
        raise _push_unavailable() from exc
    public_tag = hashlib.sha256(str(alert["id"]).encode()).hexdigest()[:20]
    push_payload = {
        "title": str(alert["title"]),
        "body": str(alert["body"]),
        "url": "/guia-cidadao",
        "tag": f"citizen-alert-{public_tag}",
    }
    try:
        sent, failed = await asyncio.to_thread(
            PushService(settings).broadcast,
            subscriptions,
            push_payload,
        )
    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
        raise _push_unavailable() from exc
    return PushBroadcastResponse(selected=len(subscriptions), sent=sent, failed=failed)
