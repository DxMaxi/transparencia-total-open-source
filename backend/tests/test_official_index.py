import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.official_index import OfficialIndexCollector


@pytest.mark.asyncio
async def test_official_index_preserves_bytes_and_filters_external_links() -> None:
    body = (
        b"<html><body>"
        b'<a href="/relatorio.pdf">Relatorio oficial</a>'
        b'<a href="https://example.org/noticia">Ligacao externa</a>'
        b'<a href="/relatorio.pdf">Relatorio oficial</a>'
        b"</body></html>"
    )
    response = httpx.Response(
        200,
        content=body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", "https://www.tcontas.pt/pt-pt/ProdutosTC/"),
    )
    http = AsyncMock()
    http.get.return_value = response

    result = await OfficialIndexCollector(http).collect(
        source_name="TRIBUNAL_CONTAS",
        index_url="https://www.tcontas.pt/pt-pt/ProdutosTC/",
    )

    assert result.content_sha256 == hashlib.sha256(body).hexdigest()
    assert result.raw_document.content == body
    assert result.raw_document.mime_type == "text/html"
    assert result.publishable is False
    assert len(result.resources) == 1
    assert str(result.resources[0].url) == "https://www.tcontas.pt/relatorio.pdf"


@pytest.mark.asyncio
async def test_official_index_rejects_unapproved_source() -> None:
    http = AsyncMock()

    with pytest.raises(ValueError, match="URL nao autorizada|URL não autorizada"):
        await OfficialIndexCollector(http).collect(
            source_name="INVALID",
            index_url="https://example.org/",
        )

    http.get.assert_not_awaited()
