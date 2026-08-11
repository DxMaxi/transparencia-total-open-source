import base64
import time
import uuid

import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response

from app.core.config import Settings
from app.core.staff_auth import InvalidStaffToken, StaffAuthUnavailable, SupabaseJwtVerifier


def _base64url_integer(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture
def signing_material() -> tuple[object, dict[str, str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    return private_key, {
        "kty": "RSA",
        "use": "sig",
        "kid": "editorial-test-key",
        "alg": "RS256",
        "n": _base64url_integer(numbers.n),
        "e": _base64url_integer(numbers.e),
    }


def _token(private_key: object, *, user_id: uuid.UUID, **overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "iat": now,
        "exp": now + 300,
        "aal": "aal2",
        "role": "authenticated",
    }
    claims.update(overrides)
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "editorial-test-key"},
    )


@pytest.mark.asyncio
async def test_verifies_supabase_signature_issuer_audience_and_aal(
    signing_material: tuple[object, dict[str, str]],
) -> None:
    private_key, public_jwk = signing_material
    settings = Settings(_env_file=None, supabase_url="https://example.supabase.co")
    verifier = SupabaseJwtVerifier(settings)
    user_id = uuid.uuid4()
    with respx.mock(assert_all_called=True) as router:
        route = router.get("https://example.supabase.co/auth/v1/.well-known/jwks.json").mock(
            return_value=Response(200, json={"keys": [public_jwk]})
        )
        first = await verifier.verify_bearer(f"Bearer {_token(private_key, user_id=user_id)}")
        second = await verifier.verify_bearer(f"Bearer {_token(private_key, user_id=user_id)}")
    await verifier.close()

    assert first.auth_user_id == user_id
    assert first.assurance_level == "aal2"
    assert second == first
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_rejects_wrong_audience_after_valid_signature(
    signing_material: tuple[object, dict[str, str]],
) -> None:
    private_key, public_jwk = signing_material
    verifier = SupabaseJwtVerifier(
        Settings(_env_file=None, supabase_url="https://example.supabase.co")
    )
    with respx.mock:
        respx.get("https://example.supabase.co/auth/v1/.well-known/jwks.json").mock(
            return_value=Response(200, json={"keys": [public_jwk]})
        )
        with pytest.raises(InvalidStaffToken, match="expirada|inválida"):
            await verifier.verify_bearer(
                f"Bearer {_token(private_key, user_id=uuid.uuid4(), aud='other')}"
            )
    await verifier.close()


@pytest.mark.asyncio
async def test_rejects_symmetric_or_missing_bearer_without_fetching_jwks() -> None:
    verifier = SupabaseJwtVerifier(
        Settings(_env_file=None, supabase_url="https://example.supabase.co")
    )
    symmetric = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": int(time.time()) + 60},
        "not-a-real-production-secret-with-32-bytes",
        algorithm="HS256",
        headers={"kid": "legacy"},
    )
    with pytest.raises(InvalidStaffToken, match="Algoritmo"):
        await verifier.verify_bearer(f"Bearer {symmetric}")
    with pytest.raises(InvalidStaffToken, match="falta"):
        await verifier.verify_bearer(None)
    await verifier.close()


@pytest.mark.asyncio
async def test_authentication_is_fail_closed_when_not_configured() -> None:
    verifier = SupabaseJwtVerifier(Settings(_env_file=None))
    with pytest.raises(StaffAuthUnavailable, match="não configurada"):
        await verifier.verify_bearer("Bearer token")
    await verifier.close()
