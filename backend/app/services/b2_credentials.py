"""Validação fail-closed do âmbito de Application Keys do Backblaze B2.

As credenciais são usadas apenas para autorizar a conta na API oficial. O resultado
normalizado nunca inclui a chave, o identificador da chave ou o token de autorização.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from typing import Any, Final, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

AUTHORIZE_ACCOUNT_URL: Final = "https://api.backblazeb2.com/b2api/v4/b2_authorize_account"
MAX_AUTHORIZE_RESPONSE_BYTES: Final = 1_000_000

BACKUP_KEY_CAPABILITIES: Final = frozenset(
    {
        "readFiles",
        "writeFiles",
        "readFileRetentions",
        "writeFileRetentions",
    }
)
RESTORE_KEY_CAPABILITIES: Final = frozenset({"readFiles"})
KEY_CAPABILITIES_BY_ROLE: Final = {
    "backup": BACKUP_KEY_CAPABILITIES,
    "restore": RESTORE_KEY_CAPABILITIES,
}

_EU_S3_ENDPOINT_RE = re.compile(r"^https://s3\.eu-central-[0-9]+\.backblazeb2\.com$")


class B2CredentialScopeError(ValueError):
    """Indica credenciais inválidas, demasiado amplas ou dirigidas ao destino errado."""


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise B2CredentialScopeError(f"{field} deve ser um objeto")
    return cast(Mapping[str, Any], value)


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise B2CredentialScopeError(f"{field} deve ser texto não vazio")
    return value.strip()


def _capabilities(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        raise B2CredentialScopeError("allowed.capabilities deve ser uma lista")
    capabilities: list[str] = []
    for raw_capability in value:
        capability = _string(raw_capability, field="allowed.capabilities[]")
        capabilities.append(capability)
    if len(capabilities) != len(set(capabilities)):
        raise B2CredentialScopeError("allowed.capabilities contém valores repetidos")
    return frozenset(capabilities)


def authorize_b2_application_key(
    *,
    application_key_id: str,
    application_key: str,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Autoriza uma chave B2 sem a colocar no URL, argumentos ou mensagens de erro."""

    application_key_id = application_key_id.strip()
    application_key = application_key.strip()
    if not application_key_id or any(character.isspace() for character in application_key_id):
        raise B2CredentialScopeError("B2_KEY_ID ausente ou inválido")
    if not application_key or any(character.isspace() for character in application_key):
        raise B2CredentialScopeError("B2_APPLICATION_KEY ausente ou inválida")
    if timeout_seconds <= 0:
        raise B2CredentialScopeError("timeout de autorização inválido")

    basic_value = base64.b64encode(f"{application_key_id}:{application_key}".encode()).decode(
        "ascii"
    )
    request = Request(
        AUTHORIZE_ACCOUNT_URL,
        headers={
            "Authorization": f"Basic {basic_value}",
            "Accept": "application/json",
            "User-Agent": "transparencia-total-backup-scope/1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_AUTHORIZE_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise B2CredentialScopeError(
            f"o Backblaze B2 recusou a credencial (HTTP {exc.code})"
        ) from exc
    except OSError as exc:
        raise B2CredentialScopeError("não foi possível autorizar a credencial no B2") from exc

    if len(body) > MAX_AUTHORIZE_RESPONSE_BYTES:
        raise B2CredentialScopeError("resposta de autorização B2 demasiado grande")
    try:
        decoded: object = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise B2CredentialScopeError("resposta de autorização B2 inválida") from exc
    if not isinstance(decoded, dict):
        raise B2CredentialScopeError("resposta de autorização B2 deve ser um objeto")
    return cast(dict[str, Any], decoded)


def validate_b2_application_key_scope(
    authorization: Mapping[str, Any],
    *,
    role: str,
    expected_bucket: str,
    expected_prefix: str,
    expected_s3_endpoint: str,
) -> dict[str, object]:
    """Confirma destino, prefixo e conjunto exato de capacidades de uma chave B2."""

    expected_capabilities = KEY_CAPABILITIES_BY_ROLE.get(role)
    if expected_capabilities is None:
        raise B2CredentialScopeError("papel da credencial B2 desconhecido")
    expected_bucket = _string(expected_bucket, field="expected_bucket")
    expected_prefix = _string(expected_prefix, field="expected_prefix")
    expected_s3_endpoint = _string(expected_s3_endpoint, field="expected_s3_endpoint").rstrip("/")
    if _EU_S3_ENDPOINT_RE.fullmatch(expected_s3_endpoint) is None:
        raise B2CredentialScopeError("o endpoint B2 esperado não pertence à região EU Central")

    api_info = _mapping(authorization.get("apiInfo"), field="apiInfo")
    storage_api = _mapping(api_info.get("storageApi"), field="apiInfo.storageApi")
    allowed = _mapping(storage_api.get("allowed"), field="apiInfo.storageApi.allowed")

    observed_capabilities = _capabilities(allowed.get("capabilities"))
    if observed_capabilities != expected_capabilities:
        missing = sorted(expected_capabilities.difference(observed_capabilities))
        extra = sorted(observed_capabilities.difference(expected_capabilities))
        details: list[str] = []
        if missing:
            details.append("em falta: " + ", ".join(missing))
        if extra:
            details.append("a mais: " + ", ".join(extra))
        raise B2CredentialScopeError(
            "capacidades da credencial B2 fora do perfil mínimo (" + "; ".join(details) + ")"
        )

    raw_buckets = allowed.get("buckets")
    if not isinstance(raw_buckets, list) or len(raw_buckets) != 1:
        raise B2CredentialScopeError("a credencial B2 deve estar limitada a um único bucket")
    bucket = _mapping(raw_buckets[0], field="allowed.buckets[0]")
    if bucket.get("name") != expected_bucket:
        raise B2CredentialScopeError("a credencial B2 está limitada ao bucket errado")
    if allowed.get("namePrefix") != expected_prefix:
        raise B2CredentialScopeError("a credencial B2 está limitada ao prefixo errado")

    observed_s3_endpoint = _string(
        storage_api.get("s3ApiUrl"), field="apiInfo.storageApi.s3ApiUrl"
    ).rstrip("/")
    if observed_s3_endpoint != expected_s3_endpoint:
        raise B2CredentialScopeError("a credencial B2 pertence a outro endpoint ou região")

    return {
        "role": role,
        "bucket": expected_bucket,
        "name_prefix": expected_prefix,
        "capabilities": sorted(observed_capabilities),
        "s3_endpoint": observed_s3_endpoint,
    }
