import os
import uuid

import pytest

from app.core.config import Settings
from app.repositories.postgres import PostgresRepository
from app.services.editorial_staging_readiness import (
    EDITORIAL_FUNCTION_SEARCH_PATHS,
    EDITORIAL_TABLES,
    EDITORIAL_TRIGGERS,
    REQUIRED_V5_MIGRATIONS,
    EditorialDatabaseSnapshot,
    _normalize_catalog_char,
    evaluate_editorial_staging_snapshot,
    inspect_editorial_staging_readiness,
)
from scripts import inspect_editorial_staging_readiness as readiness_command


def _ready_snapshot() -> EditorialDatabaseSnapshot:
    return EditorialDatabaseSnapshot(
        server_version_num=170000,
        roles=frozenset({"anon", "authenticated"}),
        role_privileges={"anon": frozenset(), "authenticated": frozenset()},
        auth_users_exists=True,
        table_rls={table: True for table in EDITORIAL_TABLES},
        policy_count=0,
        roles_with_schema_usage=frozenset(),
        table_privileges=frozenset(),
        function_search_paths={
            function_name: frozenset({search_path})
            for function_name, search_path in EDITORIAL_FUNCTION_SEARCH_PATHS.items()
        },
        function_privileges=frozenset(),
        enabled_triggers=frozenset(EDITORIAL_TRIGGERS),
        auth_fk_target="auth.users",
        auth_fk_delete="r",
        auth_fk_update="c",
        migrations=frozenset(REQUIRED_V5_MIGRATIONS),
        active_staff_counts={"ADMIN": 1, "REVIEWER": 0},
    )


def test_readiness_report_separates_database_proof_from_manual_auth_gates() -> None:
    report = evaluate_editorial_staging_snapshot(_ready_snapshot())

    assert report["database_ready"] is True
    assert all(check["ok"] for check in report["checks"])
    assert len(report["manual_auth_gates"]) == 5
    assert "nunca configura" in str(report["scope"])


def test_readiness_fails_closed_on_browser_access_or_missing_admin() -> None:
    snapshot = _ready_snapshot()
    snapshot.table_privileges = frozenset({"authenticated:editorial_cases"})
    snapshot.active_staff_counts = {"ADMIN": 0, "REVIEWER": 1}

    report = evaluate_editorial_staging_snapshot(snapshot)
    failed = {str(check["code"]) for check in report["checks"] if not check["ok"]}

    assert report["database_ready"] is False
    assert failed == {"no_browser_table_privileges", "active_admin"}


def test_readiness_fails_closed_when_browser_role_can_bypass_rls() -> None:
    snapshot = _ready_snapshot()
    snapshot.role_privileges["authenticated"] = frozenset({"BYPASSRLS"})

    report = evaluate_editorial_staging_snapshot(snapshot)
    failed = {str(check["code"]) for check in report["checks"] if not check["ok"]}

    assert report["database_ready"] is False
    assert failed == {"browser_roles_unprivileged"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(b"r", "r"), (bytearray(b"c"), "c"), (memoryview(b"D"), "D"), ("O", "O")],
)
def test_postgres_catalog_char_is_normalized(value: object, expected: str) -> None:
    assert _normalize_catalog_char(value) == expected


@pytest.mark.parametrize("value", [b"", b"rr", b"\xff", "", "rr", 1, None])
def test_postgres_catalog_char_rejects_invalid_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _normalize_catalog_char(value)


@pytest.mark.asyncio
async def test_readiness_command_requires_explicit_read_only_confirmation() -> None:
    with pytest.raises(RuntimeError, match="--confirm-read-only"):
        await readiness_command._run(confirm_read_only=False)


@pytest.mark.asyncio
async def test_readiness_command_refuses_non_staging_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        readiness_command,
        "get_settings",
        lambda: Settings(environment="test"),
    )

    with pytest.raises(RuntimeError, match="ENVIRONMENT=staging"):
        await readiness_command._run(confirm_read_only=True)


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Exige PostgreSQL 17 descartável com o bootstrap Supabase de CI.",
)
@pytest.mark.asyncio
async def test_disposable_supabase_shape_exercises_rls_privileges_and_staff_fk() -> None:
    repository = PostgresRepository(Settings(environment="test"))
    await repository.connect()
    try:
        assert repository.pool is not None
        suffix = uuid.uuid4().hex
        auth_user_id = uuid.uuid4()
        staff_id = f"staff_readiness_{suffix}"

        async with repository.pool.acquire() as connection:
            marker_exists = await connection.fetchval(
                "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
            )
            if not marker_exists:
                pytest.skip("A base não foi preparada com o stub Supabase descartável")

            await connection.execute(
                "INSERT INTO auth.users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
                auth_user_id,
            )
            await connection.execute(
                """
                INSERT INTO staff_profiles
                    (id, auth_user_id, public_alias, role, active, created_at, updated_at)
                VALUES ($1, $2, $3, 'ADMIN', TRUE, NOW(), NOW())
                """,
                staff_id,
                auth_user_id,
                f"admin-readiness-{suffix[:12]}",
            )
            try:
                async with connection.transaction(readonly=True, isolation="repeatable_read"):
                    report = await inspect_editorial_staging_readiness(connection)
            finally:
                await connection.execute("DELETE FROM staff_profiles WHERE id = $1", staff_id)
                await connection.execute("DELETE FROM auth.users WHERE id = $1", auth_user_id)

        failed_checks = [
            f"{check['code']}: {check['detail']}" for check in report["checks"] if not check["ok"]
        ]
        assert not failed_checks, failed_checks
        assert report["database_ready"] is True
    finally:
        await repository.close()
