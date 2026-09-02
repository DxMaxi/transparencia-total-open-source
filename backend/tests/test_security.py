import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    hmac_private_reference_identifier,
    is_individual_ept_source_url,
    is_individual_organisation_registry_source_url,
    is_official_url,
    require_official_url,
)
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


@pytest.mark.parametrize(
    "url",
    [
        "https://entidadetransparencia.pt/registo/DU-42",
        "https://www.tribunalconstitucional.pt/tc/ept/declaracao/DU-42",
    ],
)
def test_accepts_only_individual_ept_source_urls(url: str) -> None:
    assert is_individual_ept_source_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://entidadetransparencia.pt/",
        "https://entidadetransparencia.pt/?declaracao=DU-42",
        "https://www.tribunalconstitucional.pt/tc/ept/",
        "https://www.tribunalconstitucional.pt/tc/ept/?declaracao=DU-42",
        "https://example.org/registo/DU-42",
    ],
)
def test_rejects_general_or_non_official_ept_sources(url: str) -> None:
    assert not is_individual_ept_source_url(url)


@pytest.mark.parametrize("path", ["DetalhePublicacao.aspx", "detalhepublicacao.aspx"])
def test_accepts_individual_irn_content(path: str) -> None:
    url = f"https://publicacoes.mj.pt/{path}"
    assert is_official_url(url)
    assert is_individual_organisation_registry_source_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://publicacoes.mj.pt/pesquisa.aspx",
        "https://publicacoes.mj.pt/Index.aspx",
        "https://publicacoes.mj.pt/DetalhePublicacao.aspx?nipc=123456789",
        "https://publicacoes.mj.pt/DetalhePublicacao.aspx#123456789",
        "https://publicacoes.mj.pt:443/DetalhePublicacao.aspx",
        "http://publicacoes.mj.pt/DetalhePublicacao.aspx",
        "https://publicacoes.mj.pt.evil.example/DetalhePublicacao.aspx",
        "https://user:pass@publicacoes.mj.pt/DetalhePublicacao.aspx",
        "https://publicacoes.mj.pt/%44etalhePublicacao.aspx",
        "https://publicacoes.mj.pt/DetalhePublicacao.aspx\n",
        "https://publıcacoes.mj.pt/DetalhePublicacao.aspx",
        "https://publicacoes.mj.pt/DetalhePublıcacao.aspx",
        "HTTPS://publicacoes.mj.pt/DetalhePublicacao.aspx",
        "https://PUBLICACOES.MJ.PT/DetalhePublicacao.aspx",
    ],
)
def test_rejects_generic_or_sensitive_irn_urls(url: str) -> None:
    assert not is_individual_organisation_registry_source_url(url)


@pytest.mark.parametrize("url", ["https://evil.example/phishing", "//evil.example", "javascript:x"])
def test_push_notifications_only_open_same_origin_paths(url: str) -> None:
    with pytest.raises(ValidationError):
        PushBroadcastRequest(title="Alerta", body="Atualização oficial", url=url)


def test_cors_origins_accept_comma_separated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://example.org")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "https://example.org"]


def test_private_reference_identifier_is_only_a_stable_hmac() -> None:
    pepper = "p" * 32
    digest = hmac_private_reference_identifier("  titular-１２３  ", pepper)

    assert digest == hmac_private_reference_identifier("titular-123", pepper)
    assert len(digest) == 64
    assert "titular" not in digest
    assert digest != hmac_private_reference_identifier("Titular-123", pepper)
