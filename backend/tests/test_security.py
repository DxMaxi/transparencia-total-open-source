import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import is_official_url, require_official_url
from app.models.api import PushBroadcastRequest


@pytest.mark.parametrize(
    "url",
    [
        "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx",
        "https://data.dre.pt/eli/lei/48/2018/08/14/p/dre/pt/html",
        "https://www.tribunalconstitucional.pt/tc/ept/",
        "https://entidadetransparencia.pt/",
        "https://transparencia.sns.gov.pt/pages/home-page/",
        "https://portugal.gov.pt/gc25/governo/programa-do-governo",
    ],
)
def test_accepts_official_https_urls(url: str) -> None:
    assert is_official_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.parlamento.pt/dados",
        "https://parlamento.pt.evil.example/dados",
        "https://www.entidadetransparencia.pt/",
        "https://127.0.0.1/admin",
        "file:///etc/passwd",
    ],
)
def test_rejects_ssrf_and_non_https_urls(url: str) -> None:
    assert not is_official_url(url)
    with pytest.raises(ValueError):
        require_official_url(url)


@pytest.mark.parametrize("url", ["https://evil.example/phishing", "//evil.example", "javascript:x"])
def test_push_notifications_only_open_same_origin_paths(url: str) -> None:
    with pytest.raises(ValidationError):
        PushBroadcastRequest(title="Alerta", body="Atualização oficial", url=url)


def test_cors_origins_accept_comma_separated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://example.org")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "https://example.org"]
