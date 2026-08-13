import json

import pytest

from app.core.config import Settings
from app.services.editorial_staging_readiness import REQUIRED_V5_MIGRATIONS
from app.services.staging_target import (
    StagingCatalogSnapshot,
    evaluate_staging_catalog,
    validate_staging_target,
)
from scripts import inspect_staging_target as target_command

PROJECT_REF = "abcdefghijklmnopqrst"
PRODUCTION_REF = "0123456789abcdefghij"
SUPABASE_URL = f"https://{PROJECT_REF}.supabase.co"
DIRECT_DATABASE_URL = (
    f"postgresql://postgres:private@db.{PROJECT_REF}.supabase.co:5432/"
    "postgres?sslmode=require&schema=public"
)


def _target(database_url: str = DIRECT_DATABASE_URL):
    return validate_staging_target(
        database_url=database_url,
        supabase_url=SUPABASE_URL,
        expected_project_ref=PROJECT_REF,
        forbidden_project_refs=PRODUCTION_REF,
    )


def _snapshot() -> StagingCatalogSnapshot:
    return StagingCatalogSnapshot(
        server_version_num=170006,
        transaction_read_only=True,
        roles=frozenset({"anon", "authenticated"}),
        auth_users_exists=True,
        public_table_count=54,
        public_function_count=12,
        applied_migrations=frozenset(REQUIRED_V5_MIGRATIONS),
    )


def test_target_accepts_direct_and_session_pooler_connections() -> None:
    direct = _target()
    pooler = _target(
        f"postgresql://postgres.{PROJECT_REF}:private@"
        "aws-0-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=verify-full"
    )

    assert direct.project_ref == PROJECT_REF
    assert direct.connection_kind == "direct"
    assert pooler.connection_kind == "session_pooler"


@pytest.mark.parametrize(
    ("database_url", "supabase_url", "expected_ref", "forbidden", "message"),
    [
        (
            DIRECT_DATABASE_URL,
            SUPABASE_URL,
            PROJECT_REF,
            PROJECT_REF,
            "destino proibido",
        ),
        (
            DIRECT_DATABASE_URL,
            f"https://{PRODUCTION_REF}.supabase.co",
            PROJECT_REF,
            PRODUCTION_REF,
            "SUPABASE_URL",
        ),
        (
            DIRECT_DATABASE_URL.replace(PROJECT_REF, PRODUCTION_REF),
            SUPABASE_URL,
            PROJECT_REF,
            PRODUCTION_REF,
            "DATABASE_URL",
        ),
        (
            f"postgresql://postgres.{PROJECT_REF}:private@"
            "aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require",
            SUPABASE_URL,
            PROJECT_REF,
            PRODUCTION_REF,
            "session pooler",
        ),
        (
            DIRECT_DATABASE_URL.replace("sslmode=require", "sslmode=disable"),
            SUPABASE_URL,
            PROJECT_REF,
            PRODUCTION_REF,
            "sslmode",
        ),
        (
            DIRECT_DATABASE_URL.replace("?sslmode=require&schema=public", ""),
            SUPABASE_URL,
            PROJECT_REF,
            PRODUCTION_REF,
            "sslmode",
        ),
        (
            DIRECT_DATABASE_URL.replace("/postgres?", "/outra_base?"),
            SUPABASE_URL,
            PROJECT_REF,
            PRODUCTION_REF,
            "base postgres",
        ),
        (
            DIRECT_DATABASE_URL.replace("//postgres:", "//outro_utilizador:"),
            SUPABASE_URL,
            PROJECT_REF,
            PRODUCTION_REF,
            "utilizador da ligação direta",
        ),
    ],
)
def test_target_rejects_ambiguous_or_insecure_connections(
    database_url: str,
    supabase_url: str,
    expected_ref: str,
    forbidden: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_staging_target(
            database_url=database_url,
            supabase_url=supabase_url,
            expected_project_ref=expected_ref,
            forbidden_project_refs=forbidden,
        )


def test_catalog_report_is_sanitized_and_can_require_v5_migrations() -> None:
    target = _target()
    report = evaluate_staging_catalog(_snapshot(), target, require_v5_migrations=True)

    assert report["catalog_ready"] is True
    serialized = json.dumps(report)
    assert "private@" not in serialized
    assert "DATABASE_URL" not in serialized
    assert report["target"] == {
        "project_ref": PROJECT_REF,
        "connection_kind": "direct",
    }

    missing = _snapshot()
    missing = StagingCatalogSnapshot(
        server_version_num=missing.server_version_num,
        transaction_read_only=missing.transaction_read_only,
        roles=missing.roles,
        auth_users_exists=missing.auth_users_exists,
        public_table_count=missing.public_table_count,
        public_function_count=missing.public_function_count,
        applied_migrations=frozenset(),
    )
    failed = evaluate_staging_catalog(missing, target, require_v5_migrations=True)
    failed_codes = {check["code"] for check in failed["checks"] if not check["ok"]}
    assert failed["catalog_ready"] is False
    assert failed_codes == {"required_v5_migrations"}

    unsupported_version = _snapshot()
    unsupported_version = StagingCatalogSnapshot(
        server_version_num=180001,
        transaction_read_only=unsupported_version.transaction_read_only,
        roles=unsupported_version.roles,
        auth_users_exists=unsupported_version.auth_users_exists,
        public_table_count=unsupported_version.public_table_count,
        public_function_count=unsupported_version.public_function_count,
        applied_migrations=unsupported_version.applied_migrations,
    )
    version_report = evaluate_staging_catalog(
        unsupported_version,
        target,
        require_v5_migrations=True,
    )
    assert version_report["catalog_ready"] is False
    assert {check["code"] for check in version_report["checks"] if not check["ok"]} == {
        "postgres_17"
    }


@pytest.mark.asyncio
async def test_target_command_requires_confirmation_before_loading_settings() -> None:
    with pytest.raises(RuntimeError, match="--confirm-read-only"):
        await target_command._run(confirm_read_only=False, require_v5_migrations=False)


@pytest.mark.asyncio
async def test_target_command_refuses_non_staging_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        target_command,
        "get_settings",
        lambda: Settings(_env_file=None, environment="test"),
    )

    with pytest.raises(RuntimeError, match="ENVIRONMENT=staging"):
        await target_command._run(confirm_read_only=True, require_v5_migrations=False)
