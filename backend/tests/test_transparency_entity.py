import httpx
import pytest
import respx
from tenacity import wait_none

from app.core.config import Settings
from app.services.http import OfficialHttpClient
from app.services.transparency_entity import (
    EPT_INDEX_URL,
    EPT_PORTAL_FALLBACK_URL,
    EPT_PORTAL_FALLBACK_WARNING,
    TransparencyEntityCollector,
)


@pytest.mark.asyncio
@respx.mock
async def test_controlled_rollout_uses_the_linked_official_portal_as_partial_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("GET", EPT_INDEX_URL)
    canonical = respx.get(EPT_INDEX_URL).mock(
        side_effect=httpx.ConnectError("índice indisponível", request=request)
    )
    fallback = respx.get(EPT_PORTAL_FALLBACK_URL).mock(
        return_value=httpx.Response(
            200,
            text='<html><a href="/informacao">Informação institucional</a></html>',
        )
    )
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        _env_file=None,
    )

    async with OfficialHttpClient(settings) as client:
        monkeypatch.setattr(client._fetch_once.retry, "wait", wait_none())
        collection = await TransparencyEntityCollector(settings, client).fetch_public_index(
            allow_portal_fallback=True
        )

    assert canonical.call_count == 5
    assert fallback.call_count == 1
    assert collection.canonical_index_available is False
    assert collection.warnings == (EPT_PORTAL_FALLBACK_WARNING,)
    assert str(collection.raw_document.source_url) == EPT_PORTAL_FALLBACK_URL
    assert [str(resource.url) for resource in collection.resources] == [
        "https://entidadetransparencia.pt/informacao"
    ]


@pytest.mark.asyncio
@respx.mock
async def test_direct_ept_resource_endpoint_does_not_hide_the_canonical_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("GET", EPT_INDEX_URL)
    canonical = respx.get(EPT_INDEX_URL).mock(
        side_effect=httpx.ConnectError("índice indisponível", request=request)
    )
    fallback = respx.get(EPT_PORTAL_FALLBACK_URL).mock(
        return_value=httpx.Response(200, text="portal alternativo")
    )
    settings = Settings(
        environment="test",
        source_requests_per_second=5,
        _env_file=None,
    )

    async with OfficialHttpClient(settings) as client:
        monkeypatch.setattr(client._fetch_once.retry, "wait", wait_none())
        with pytest.raises(httpx.ConnectError, match="índice indisponível"):
            await TransparencyEntityCollector(settings, client).fetch_public_index()

    assert canonical.call_count == 5
    assert not fallback.called
