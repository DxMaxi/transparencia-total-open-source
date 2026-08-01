import httpx
import pytest
import respx

from app.core.config import Settings
from app.services.http import OfficialHttpClient


@pytest.mark.asyncio
@respx.mock
async def test_rejects_non_official_redirect_before_following_it() -> None:
    official = respx.get("https://www.parlamento.pt/redirect").mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/collect"})
    )
    untrusted = respx.get("https://evil.example/collect").mock(
        return_value=httpx.Response(200, text="should not be requested")
    )
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        _env_file=None,
    )
    async with OfficialHttpClient(settings) as client:
        with pytest.raises(ValueError, match="URL não autorizada"):
            await client.get("https://www.parlamento.pt/redirect")
    assert official.called
    assert not untrusted.called


@pytest.mark.asyncio
@respx.mock
async def test_stops_documents_above_the_configured_limit() -> None:
    respx.get("https://www.parlamento.pt/large").mock(
        return_value=httpx.Response(200, content=b"x" * 10_001)
    )
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        source_max_bytes=10_000,
        _env_file=None,
    )
    async with OfficialHttpClient(settings) as client:
        with pytest.raises(ValueError, match="excede o limite"):
            await client.get("https://www.parlamento.pt/large")
