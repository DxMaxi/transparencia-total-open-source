from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = (
    ROOT
    / "prisma"
    / "migrations"
    / "20260811133000_v5_editorial_withdrawal_cycle"
    / "migration.sql"
)


def test_withdrawal_cycle_keeps_events_unique_per_immutable_version() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    schema = (ROOT / "prisma" / "schema.prisma").read_text(encoding="utf-8")

    assert 'DROP INDEX "editorial_publication_events_case_action_target_key"' in migration
    assert (
        'CREATE UNIQUE INDEX "editorial_publication_events_case_version_action_target_key"'
        in migration
    )
    assert '"case_id", "version_id", "action", "target_type", "target_id"' in migration
    assert "@@unique([caseId, versionId, action, targetType, targetId])" in schema
    assert "DELETE FROM" not in migration
    assert 'UPDATE "editorial_publication_events"' not in migration


def test_only_withdrawn_content_can_enter_a_new_review_cycle() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    repository = (ROOT / "backend" / "app" / "repositories" / "editorial.py").read_text(
        encoding="utf-8"
    )

    assert migration.count("'WITHDRAWN'::\"EditorialState\"") >= 3
    assert 'CREATE OR REPLACE FUNCTION "validate_editorial_version_insert"' in migration
    assert 'CREATE OR REPLACE FUNCTION "validate_editorial_decision_insert"' in migration
    assert "EditorialState.WITHDRAWN" in repository
    assert (
        "EditorialState.PUBLISHED"
        not in repository.split("async def correct_case", 1)[1].split("async def", 1)[0]
    )
