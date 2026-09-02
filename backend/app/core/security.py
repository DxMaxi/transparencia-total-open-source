import hashlib
import hmac
import ipaddress
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urlparse

from fastapi import Header, HTTPException, status

from app.core.config import get_settings

OFFICIAL_HOSTS = frozenset(
    {
        "parlamento.pt",
        "www.parlamento.pt",
        "app.parlamento.pt",
        "agenda.parlamento.pt",
        "dre.pt",
        "www.dre.pt",
        "data.dre.pt",
        "diariodarepublica.pt",
        "www.diariodarepublica.pt",
        "tribunalconstitucional.pt",
        "www.tribunalconstitucional.pt",
        "entidadetransparencia.pt",
        "publicacoes.mj.pt",
        "transparencia.gov.pt",
        "www.transparencia.gov.pt",
        "base.gov.pt",
        "www.base.gov.pt",
        "dados.gov.pt",
        "www.dados.gov.pt",
        "portugal.gov.pt",
        "www.portugal.gov.pt",
        "impic.pt",
        "www.impic.pt",
        "tcontas.pt",
        "www.tcontas.pt",
        "ministeriopublico.pt",
        "www.ministeriopublico.pt",
        "tribunais.org.pt",
        "www.tribunais.org.pt",
        "dgsi.pt",
        "www.dgsi.pt",
        "data.europarl.europa.eu",
        "www.europarl.europa.eu",
        "europarl.europa.eu",
        "sns.gov.pt",
        "www.sns.gov.pt",
        "transparencia.sns.gov.pt",
    }
)

EPT_OFFICIAL_HOSTS = frozenset(
    {
        "tribunalconstitucional.pt",
        "www.tribunalconstitucional.pt",
        "entidadetransparencia.pt",
    }
)


def normalise_host(host: str | None) -> str:
    return (host or "").strip().rstrip(".").lower()


def is_official_url(url: str, extra_hosts: Iterable[str] = ()) -> bool:
    try:
        parsed = urlparse(url)
        host = normalise_host(parsed.hostname)
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        allowed = OFFICIAL_HOSTS | {normalise_host(item) for item in extra_hosts}
        return host in allowed
    except ValueError:
        return False


def require_official_url(url: str, extra_hosts: Iterable[str] = ()) -> str:
    if not is_official_url(url, extra_hosts):
        raise ValueError(f"URL não autorizada: {url}")
    return url


def is_individual_ept_source_url(url: str) -> bool:
    """Aceita apenas uma prova individual nos domínios oficiais da EPT.

    A página institucional geral é útil para pesquisa, mas não demonstra a
    existência ou o conteúdo de uma declaração individual.
    """

    if not is_official_url(url):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = normalise_host(parsed.hostname)
    path = parsed.path.rstrip("/") or "/"
    if host not in EPT_OFFICIAL_HOSTS or path == "/":
        return False
    return not (
        host in {"tribunalconstitucional.pt", "www.tribunalconstitucional.pt"}
        and path.casefold() == "/tc/ept"
    )


def is_individual_organisation_registry_source_url(url: str) -> bool:
    """Só o conteúdo individual do IRN, sem parâmetros que exponham NIPC.

    O portal usa contexto de sessão: a URL, sozinha, não identifica um ato.
    Exigem-se também referência não fiscal, conteúdo arquivado e respetivo SHA.
    """

    return (
        re.fullmatch(r"https://publicacoes\.mj\.pt/(?i:DetalhePublicacao\.aspx)", url, re.ASCII)
        is not None
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalise_public_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def hmac_protected_identifier(value: str, pepper: str) -> str:
    canonical = "".join(
        str(unicodedata.decimal(character)) for character in value if character.isdecimal()
    )
    if len(canonical) != 9:
        raise ValueError("O identificador fiscal protegido deve ter nove algarismos")
    return hmac.new(pepper.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def hmac_private_reference_identifier(value: str, pepper: str) -> str:
    """Protege um identificador oficial opaco sem presumir que é um NIF.

    A referência mantém semântica exata após normalização Unicode e remoção de
    espaços exteriores. Se a fonte usar um NIF como referência, continua a
    persistir apenas o HMAC; o texto recebido nunca é devolvido ou guardado.
    """

    canonical = unicodedata.normalize("NFKC", value).strip()
    if not canonical or len(canonical) > 200:
        raise ValueError("A referência oficial protegida tem de conter 1 a 200 caracteres")
    return hmac.new(pepper.encode(), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


async def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    configured = get_settings().admin_api_key
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY não configurada",
        )
    supplied = x_admin_key or ""
    if not hmac.compare_digest(supplied, configured.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave inválida")
