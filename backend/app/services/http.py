import asyncio
import logging
from collections.abc import Iterable
from time import monotonic
from urllib.parse import urljoin

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.config import Settings
from app.core.security import require_official_url

logger = logging.getLogger(__name__)


class OfficialHttpClient:
    def __init__(self, settings: Settings, *, extra_hosts: Iterable[str] = ()) -> None:
        self.settings = settings
        self.extra_hosts = tuple(extra_hosts)
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            follow_redirects=False,
            trust_env=settings.http_trust_env,
            headers={
                "User-Agent": settings.official_user_agent,
                "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.7",
                # Algumas fontes oficiais devolvem compressão inconsistente.
                "Accept-Encoding": "identity",
            },
        )

    async def __aenter__(self) -> "OfficialHttpClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.aclose()

    async def _respect_rate_limit(self) -> None:
        interval = 1 / max(self.settings.source_requests_per_second, 0.05)
        async with self._lock:
            elapsed = monotonic() - self._last_request_at
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            self._last_request_at = monotonic()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.8, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def _fetch_once(self, url: str, max_bytes: int | None = None) -> httpx.Response:
        await self._respect_rate_limit()
        size_limit = max_bytes or self.settings.source_max_bytes
        async with self.client.stream("GET", url) as response:
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > size_limit:
                raise ValueError("Documento oficial excede o limite configurado")

            chunks: list[bytes] = []
            received = 0
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > size_limit:
                    raise ValueError("Documento oficial excede o limite configurado")
                chunks.append(chunk)

            buffered = httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=b"".join(chunks),
                request=response.request,
                history=response.history,
                extensions=response.extensions,
            )
        return buffered

    async def get(self, url: str, *, max_bytes: int | None = None) -> httpx.Response:
        current_url = require_official_url(url, self.extra_hosts)
        for _ in range(6):
            response = await self._fetch_once(current_url, max_bytes)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirecionamento oficial sem destino")
                current_url = require_official_url(
                    urljoin(str(response.url), location),
                    self.extra_hosts,
                )
                continue

            response.raise_for_status()
            final_url = str(response.url)
            require_official_url(final_url, self.extra_hosts)
            logger.info("official_source_fetched url=%s bytes=%s", final_url, len(response.content))
            return response
        raise ValueError("Número excessivo de redirecionamentos na fonte oficial")
