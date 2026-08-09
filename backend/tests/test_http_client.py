import httpx
import pytest
import respx
from tenacity import wait_none

from app.core.config import Settings
from app.services.http import OfficialHttpClient


@pytest.mark.asyncio
@respx.mock
async def test_follows_an_approved_redirect_to_the_sns_transparency_portal() -> None:
    initial = respx.get("https://transparencia.sns.gov.pt/").mock(
        return_value=httpx.Response(302, headers={"Location": "/pages/home-page/"})
    )
    destination = respx.get("https://transparencia.sns.gov.pt/pages/home-page/").mock(
        return_value=httpx.Response(200, text="índice oficial")
    )
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        _env_file=None,
    )

    async with OfficialHttpClient(settings) as client:
        response = await client.get("https://transparencia.sns.gov.pt/")

    assert response.status_code == 200
    assert initial.called
    assert destination.called


@pytest.mark.asyncio
@respx.mock
async def test_retries_transient_network_failures_with_a_bounded_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://www.tribunalconstitucional.pt/tc/ept/"
    request = httpx.Request("GET", url)
    route = respx.get(url).mock(
        side_effect=[
            httpx.ConnectError("temporariamente indisponível", request=request),
            httpx.ConnectError("temporariamente indisponível", request=request),
            httpx.ConnectError("temporariamente indisponível", request=request),
            httpx.ConnectError("temporariamente indisponível", request=request),
            httpx.Response(200, text="índice recuperado"),
        ]
    )
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        _env_file=None,
    )

    async with OfficialHttpClient(settings) as client:
        monkeypatch.setattr(client._fetch_once.retry, "wait", wait_none())
        response = await client.get(url)

    assert response.status_code == 200
    assert route.call_count == 5


@pytest.mark.asyncio
@respx.mock
async def test_persistent_ept_failure_remains_visible_without_unverified_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://www.tribunalconstitucional.pt/tc/ept/"
    request = httpx.Request("GET", url)
    canonical = respx.get(url).mock(
        side_effect=httpx.ConnectError("indisponibilidade persistente", request=request)
    )
    unverified_fallback = respx.get("https://entidadetransparencia.pt/").mock(
        return_value=httpx.Response(200, text="aplicação sem índice equivalente")
    )
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        _env_file=None,
    )

    async with OfficialHttpClient(settings) as client:
        monkeypatch.setattr(client._fetch_once.retry, "wait", wait_none())
        with pytest.raises(httpx.ConnectError, match="indisponibilidade persistente"):
            await client.get(url)

    assert canonical.call_count == 5
    assert not unverified_fallback.called


@pytest.mark.asyncio
@respx.mock
async def test_does_not_retry_a_non_transient_http_error() -> None:
    url = "https://transparencia.sns.gov.pt/pages/home-page/"
    route = respx.get(url).mock(return_value=httpx.Response(405))
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        _env_file=None,
    )

    async with OfficialHttpClient(settings) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get(url)

    assert route.call_count == 1


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
