import pytest
from fastapi import HTTPException

from app.core.rate_limit import PublicWriteRateLimiter, RateLimitPolicy


def test_public_write_rate_limit_is_scoped_and_returns_retry_after() -> None:
    now = [100.0]
    limiter = PublicWriteRateLimiter(
        clock=lambda: now[0],
        salt=b"test-salt",
        max_keys=10,
    )
    policy = RateLimitPolicy(requests=2, window_seconds=60)

    limiter.consume(bucket="reply", origin="192.0.2.1", policy=policy)
    limiter.consume(bucket="reply", origin="192.0.2.1", policy=policy)

    with pytest.raises(HTTPException) as caught:
        limiter.consume(bucket="reply", origin="192.0.2.1", policy=policy)

    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "60"}
    assert "192.0.2.1" not in str(limiter.__dict__)

    limiter.consume(bucket="push", origin="192.0.2.1", policy=policy)
    limiter.consume(bucket="reply", origin="192.0.2.2", policy=policy)

    now[0] += 61
    limiter.consume(bucket="reply", origin="192.0.2.1", policy=policy)


@pytest.mark.parametrize(
    ("requests", "window_seconds"),
    [(0, 60), (1, 0), (-1, 60)],
)
def test_rate_limit_policy_rejects_non_positive_values(
    requests: int,
    window_seconds: int,
) -> None:
    with pytest.raises(ValueError):
        RateLimitPolicy(requests=requests, window_seconds=window_seconds)
