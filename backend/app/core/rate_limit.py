import hashlib
import math
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    requests: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.requests < 1 or self.window_seconds < 1:
            raise ValueError("A política de rate limit exige limites positivos")


class PublicWriteRateLimiter:
    """Limite mínimo por processo, sem guardar nem registar endereços de origem."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        salt: bytes | None = None,
        max_keys: int = 10_000,
    ) -> None:
        if max_keys < 1:
            raise ValueError("max_keys tem de ser positivo")
        self._clock = clock
        self._salt = salt or secrets.token_bytes(32)
        self._max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _key(self, bucket: str, origin: str) -> str:
        value = f"{bucket}\0{origin}".encode()
        return hashlib.sha256(self._salt + value).hexdigest()

    def consume(self, *, bucket: str, origin: str, policy: RateLimitPolicy) -> None:
        now = self._clock()
        key = self._key(bucket, origin)
        cutoff = now - policy.window_seconds

        with self._lock:
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self._max_keys:
                    oldest_key = min(
                        self._events,
                        key=lambda candidate: self._events[candidate][-1],
                    )
                    del self._events[oldest_key]
                events = deque()
                self._events[key] = events

            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= policy.requests:
                retry_after = max(1, math.ceil(events[0] + policy.window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Demasiados pedidos. Tente novamente mais tarde.",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


PUSH_SUBSCRIPTION_POLICY = RateLimitPolicy(requests=20, window_seconds=60 * 60)
PUSH_BROADCAST_POLICY = RateLimitPolicy(requests=30, window_seconds=60 * 60)
RIGHT_OF_REPLY_POLICY = RateLimitPolicy(requests=5, window_seconds=60 * 60)

public_write_rate_limiter = PublicWriteRateLimiter()


def enforce_public_write_rate_limit(
    request: Request,
    *,
    bucket: str,
    policy: RateLimitPolicy,
) -> None:
    origin = request.client.host if request.client is not None else "unknown"
    public_write_rate_limiter.consume(bucket=bucket, origin=origin, policy=policy)
