"""Live session checks with disposable PostgreSQL; no real accounts or tokens."""

import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import asyncpg
import pytest

from app.core.staff_auth import StaffAuthUnavailable
from app.repositories.editorial import EditorialNotFoundError, EditorialRepository
from app.repositories.postgres import _asyncpg_connection_options


@pytest.mark.asyncio
async def test_session_database_failure_is_sanitized():
    repository = EditorialRepository(
        SimpleNamespace(fetchrow=AsyncMock(side_effect=asyncpg.PostgresError("private diagnostic")))
    )
    with pytest.raises(StaffAuthUnavailable, match="confirmar a sessão") as error:
        await repository.staff_session(
            auth_user_id=uuid.uuid4(), session_id=uuid.uuid4(), assurance_level="aal2"
        )
    assert "private diagnostic" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="Disposable PostgreSQL required")
@pytest.mark.parametrize(
    "revocation",
    [
        "signout",
        "deleted_account",
        "banned_account",
        "expired_session",
        "removed_factor",
        "unverified_factor",
        "other_user",
        "lowered_aal",
        "inactive_staff",
    ],
)
async def test_existing_token_cannot_outlive_session_or_factor(revocation):
    url = os.environ["DATABASE_URL"]
    assert urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"}
    dsn, settings = _asyncpg_connection_options(url)
    connection = await asyncpg.connect(dsn, server_settings=settings)
    transaction = connection.transaction()
    await transaction.start()
    user_id, session_id, factor_id, other_user = [uuid.uuid4() for _ in range(4)]
    repository = EditorialRepository(SimpleNamespace(fetchrow=connection.fetchrow))
    try:
        assert await connection.fetchval(
            "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
        )
        await connection.execute("INSERT INTO auth.users(id) VALUES ($1),($2)", user_id, other_user)
        await connection.execute(
            "INSERT INTO auth.mfa_factors(id,user_id,status) VALUES ($1,$2,'verified')",
            factor_id,
            user_id,
        )
        await connection.execute(
            "INSERT INTO auth.sessions(id,user_id,factor_id,aal) VALUES ($1,$2,$3,'aal2')",
            session_id,
            user_id,
            factor_id,
        )
        await connection.execute(
            """INSERT INTO public.staff_profiles
               (id,auth_user_id,public_alias,role,active,created_at,updated_at)
               VALUES ($1,$2,$1,'REVIEWER',true,now(),now())""",
            f"test_{uuid.uuid4().hex}",
            user_id,
        )
        args = dict(auth_user_id=user_id, session_id=session_id, assurance_level="aal2")
        assert (await repository.staff_session(**args)).assurance_level == "aal2"
        # AAL1 remains eligible to configure MFA, but cannot access private routes.
        assert (await repository.staff_session(**{**args, "assurance_level": "aal1"})).mfa_required
        mutations = {
            "signout": "DELETE FROM auth.sessions WHERE user_id=$1",
            "deleted_account": "UPDATE auth.users SET deleted_at=now() WHERE id=$1",
            "banned_account": (
                "UPDATE auth.users SET banned_until=now()+interval '1 day' WHERE id=$1"
            ),
            "expired_session": (
                "UPDATE auth.sessions SET not_after=now()-interval '1 second' WHERE user_id=$1"
            ),
            "removed_factor": "UPDATE auth.sessions SET factor_id=NULL WHERE user_id=$1",
            "unverified_factor": "UPDATE auth.mfa_factors SET status='unverified' WHERE user_id=$1",
            "lowered_aal": "UPDATE auth.sessions SET aal='aal1' WHERE user_id=$1",
            "inactive_staff": "UPDATE public.staff_profiles SET active=false WHERE auth_user_id=$1",
        }
        if revocation == "other_user":
            await connection.execute(
                "UPDATE auth.sessions SET user_id=$2 WHERE user_id=$1", user_id, other_user
            )
        else:
            await connection.execute(mutations[revocation], user_id)
        with pytest.raises(EditorialNotFoundError):
            await repository.staff_session(**args)
        if revocation == "signout":
            # A fresh login with a fresh session may recover access; old JWT stays refused.
            recovered_id = uuid.uuid4()
            await connection.execute(
                "INSERT INTO auth.sessions(id,user_id,factor_id,aal) VALUES ($1,$2,$3,'aal2')",
                recovered_id,
                user_id,
                factor_id,
            )
            assert (await repository.staff_session(**{**args, "session_id": recovered_id})).staff_id
            with pytest.raises(EditorialNotFoundError):
                await repository.staff_session(**args)
    finally:
        await transaction.rollback()
        await connection.close()
