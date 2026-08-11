from pathlib import Path

from app.api.dependencies import require_editorial_staff
from app.models.editorial import StaffRole, StaffSession

ROOT = Path(__file__).parents[2]
MIGRATION = (
    ROOT / "prisma" / "migrations" / "20260811110000_v5_editorial_foundation" / "migration.sql"
)


def test_v5_migration_keeps_editorial_data_private_and_append_only() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "staff_profiles",
        "editorial_cases",
        "editorial_versions",
        "editorial_decisions",
        "editorial_publication_events",
    ):
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;' in migration
        assert f'REVOKE ALL PRIVILEGES ON "{table}" FROM PUBLIC;' in migration

    assert 'CREATE TRIGGER "editorial_versions_append_only"' in migration
    assert 'CREATE TRIGGER "editorial_decisions_append_only"' in migration
    assert 'CREATE TRIGGER "editorial_publication_events_append_only"' in migration
    assert 'CREATE CONSTRAINT TRIGGER "editorial_cases_require_publication_event"' in migration
    assert "DEFERRABLE INITIALLY DEFERRED" in migration
    assert "source_archive_attestations" in migration
    assert 'source."publisher" IN (' in migration
    assert "source.\"kind\" <> 'NEWS_ARTICLE'" in migration
    assert "auth.users" in migration
    assert "to_regclass('auth.users') IS NOT NULL" in migration
    assert "CREATE POLICY" not in migration
    assert "GRANT SELECT" not in migration


def test_database_guards_state_machine_and_projection_revision() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    for action in (
        "SUBMIT",
        "START_REVIEW",
        "APPROVE",
        "REJECT",
        "CORRECT",
        "PUBLISH",
        "WITHDRAW",
    ):
        assert f"'{action}'::\"EditorialDecisionAction\"" in migration
    assert 'NEW."case_revision" <> case_record."revision" + 1' in migration
    assert "a projeção editorial exige decisão imutável correspondente" in migration
    assert "propostas de ingestão ou IA não podem fingir autoria humana" in migration


def test_no_generic_publication_endpoint_or_button_exists() -> None:
    route = (ROOT / "backend" / "app" / "api" / "routes" / "editorial.py").read_text(
        encoding="utf-8"
    )
    actions = (ROOT / "app" / "admin" / "revisao" / "actions.ts").read_text(encoding="utf-8")
    assert '@router.post("/cases/{case_id}/publish")' not in route
    assert "editorialFetch<EditorialCaseDetail>(`/cases/${id}/publish`" not in actions


def test_robots_excludes_private_routes() -> None:
    robots = (ROOT / "app" / "robots.ts").read_text(encoding="utf-8")
    assert 'disallow: ["/admin/", "/auth/"]' in robots


async def test_aal1_session_cannot_enter_editorial_routes() -> None:
    session = StaffSession(
        staff_id="staff_test",
        auth_user_id="a430b34c-8615-4cb4-aebb-3054d796783e",
        public_alias="revisor-teste",
        role=StaffRole.REVIEWER,
        assurance_level="aal1",
        mfa_required=True,
    )
    try:
        await require_editorial_staff(session)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
        assert getattr(exc, "headers", {}).get("X-MFA-Required") == "true"
    else:
        raise AssertionError("Uma sessão aal1 não pode entrar no circuito editorial")
