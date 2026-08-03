import asyncio
import hashlib

from app.core.config import Settings
from app.services.dre import DreCollector


class DreResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.text = content.decode("utf-8")
        self.url = "https://diariodarepublica.pt/dr/detalhe/lei/1-2026"
        self.headers = {"content-type": "text/html; charset=utf-8"}


class DreHttp:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def get(self, _url: str) -> DreResponse:
        return DreResponse(self.content)


def test_dre_preserves_raw_hash_separately_from_normalised_text() -> None:
    content = (
        b"<html><head><title>Lei n. 1/2026</title></head><body><main>"
        b"<h1>Lei n. 1/2026</h1><p>Texto oficial suficientemente longo para "
        b"ser extraido pelo coletor e conservado com a respetiva prova documental. "
        b"Este paragrafo serve apenas como fixture de teste.</p></main></body></html>"
    )
    collector = DreCollector(
        Settings(environment="test"),
        DreHttp(content),  # type: ignore[arg-type]
    )

    document = asyncio.run(
        collector.fetch_document("https://diariodarepublica.pt/dr/detalhe/lei/1-2026")
    )

    assert document.content_sha256 == hashlib.sha256(content).hexdigest()
    assert document.normalised_text_sha256 != document.content_sha256
    assert document.raw_document is not None
    assert document.raw_document.content == content
    assert "raw_document" not in document.model_dump(mode="json")
    assert "<html>" not in document.model_dump_json()
