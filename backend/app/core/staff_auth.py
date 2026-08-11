"""Validação local e fail-closed das sessões Supabase usadas pelo painel V5."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import httpx
import jwt

from app.core.config import Settings

_ALLOWED_ALGORITHMS = frozenset({"ES256", "RS256"})


class StaffAuthUnavailable(RuntimeError):
    """A autenticação privada não está configurada ou o JWKS não está disponível."""


class InvalidStaffToken(ValueError):
    """O bearer token não constitui uma sessão Supabase válida."""


@dataclass(frozen=True, slots=True)
class VerifiedStaffToken:
    auth_user_id: UUID
    assurance_level: Literal["aal1", "aal2"]
    expires_at: int


class SupabaseJwtVerifier:
    """Verifica assinatura, emissor, audiência e AAL sem confiar no browser.

    O JWKS público é mantido em memória durante um intervalo curto. Um ``kid``
    desconhecido força uma atualização, permitindo rotação de chaves sem aceitar
    algoritmos simétricos ou segredos partilhados no frontend.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_expire_at = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(5.0),
            trust_env=settings.http_trust_env,
            headers={"Accept": "application/json"},
        )

    @property
    def configured(self) -> bool:
        return self._settings.supabase_url is not None

    @property
    def issuer(self) -> str:
        if self._settings.supabase_url is None:
            raise StaffAuthUnavailable("SUPABASE_URL não configurada")
        return f"{str(self._settings.supabase_url).rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"

    async def close(self) -> None:
        await self._client.aclose()

    async def verify_bearer(self, authorization: str | None) -> VerifiedStaffToken:
        if not self.configured:
            raise StaffAuthUnavailable("Autenticação editorial não configurada")
        token = self._extract_bearer(authorization)
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise InvalidStaffToken("Sessão inválida") from exc

        algorithm = header.get("alg")
        key_id = header.get("kid")
        if algorithm not in _ALLOWED_ALGORITHMS or not isinstance(key_id, str) or not key_id:
            raise InvalidStaffToken("Algoritmo ou chave de sessão não autorizados")

        signing_key = await self._signing_key(key_id, algorithm)
        try:
            claims = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=[algorithm],
                audience=self._settings.supabase_jwt_audience,
                issuer=self.issuer,
                leeway=30,
                options={"require": ["exp", "iat", "sub", "aud", "aal", "role"]},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidStaffToken("Sessão expirada ou inválida") from exc

        assurance_level = claims.get("aal")
        if assurance_level not in {"aal1", "aal2"}:
            raise InvalidStaffToken("Nível de autenticação inválido")
        if claims.get("role") != "authenticated":
            raise InvalidStaffToken("Tipo de sessão não autorizado")
        try:
            auth_user_id = UUID(str(claims["sub"]))
            expires_at = int(claims["exp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidStaffToken("Identidade de sessão inválida") from exc

        return VerifiedStaffToken(
            auth_user_id=auth_user_id,
            assurance_level=assurance_level,
            expires_at=expires_at,
        )

    @staticmethod
    def _extract_bearer(authorization: str | None) -> str:
        if authorization is None:
            raise InvalidStaffToken("Sessão em falta")
        scheme, separator, token = authorization.strip().partition(" ")
        if separator != " " or scheme.casefold() != "bearer" or not token:
            raise InvalidStaffToken("Cabeçalho de sessão inválido")
        if len(token) > 8192 or any(character.isspace() for character in token):
            raise InvalidStaffToken("Sessão inválida")
        return token

    async def _signing_key(self, key_id: str, algorithm: str) -> jwt.PyJWK:
        now = time.monotonic()
        cached = self._keys.get(key_id)
        if cached is not None and now < self._keys_expire_at:
            return cached

        async with self._lock:
            now = time.monotonic()
            cached = self._keys.get(key_id)
            if cached is not None and now < self._keys_expire_at:
                return cached
            await self._refresh_keys()
            signing_key = self._keys.get(key_id)
            if signing_key is None or signing_key.algorithm_name != algorithm:
                raise InvalidStaffToken("Chave de assinatura desconhecida")
            return signing_key

    async def _refresh_keys(self) -> None:
        try:
            response = await self._client.get(self.jwks_url)
            response.raise_for_status()
            payload: Any = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StaffAuthUnavailable("Não foi possível validar a sessão") from exc

        raw_keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(raw_keys, list) or not raw_keys or len(raw_keys) > 20:
            raise StaffAuthUnavailable("JWKS Supabase inválido")

        parsed: dict[str, jwt.PyJWK] = {}
        for raw_key in raw_keys:
            if not isinstance(raw_key, dict):
                continue
            key_id = raw_key.get("kid")
            algorithm = raw_key.get("alg")
            if not isinstance(key_id, str) or not key_id or algorithm not in _ALLOWED_ALGORITHMS:
                continue
            try:
                parsed[key_id] = jwt.PyJWK.from_dict(raw_key, algorithm=algorithm)
            except jwt.PyJWTError:
                continue

        if not parsed:
            raise StaffAuthUnavailable("JWKS Supabase sem chaves autorizadas")
        self._keys = parsed
        self._keys_expire_at = time.monotonic() + self._settings.supabase_jwks_cache_seconds
