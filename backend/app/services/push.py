import json
import logging
from collections.abc import Iterable

from pywebpush import WebPushException, webpush

from app.core.config import Settings

logger = logging.getLogger(__name__)


class PushService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, subscription: dict[str, str], payload: dict[str, str]) -> bool:
        if self.settings.vapid_private_key is None:
            raise ValueError("VAPID_PRIVATE_KEY não configurada")
        subscription_info = {
            "endpoint": subscription["endpoint"],
            "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=self.settings.vapid_private_key.get_secret_value(),
                vapid_claims={"sub": self.settings.vapid_subject},
                ttl=3600,
            )
            return True
        except WebPushException:
            logger.exception("push_delivery_failed")
            return False

    def broadcast(
        self,
        subscriptions: Iterable[dict[str, str]],
        payload: dict[str, str],
    ) -> tuple[int, int]:
        sent = failed = 0
        for subscription in subscriptions:
            if self.send(subscription, payload):
                sent += 1
            else:
                failed += 1
        return sent, failed
