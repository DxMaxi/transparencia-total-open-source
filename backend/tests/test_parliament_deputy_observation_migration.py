from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "prisma"
    / "migrations"
    / "20260824054000_v5_parliament_deputy_observations"
    / "migration.sql"
)


def test_deputy_observation_tables_are_private_versioned_and_append_only() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert 'CREATE TABLE "parliament_deputy_snapshots"' in migration
    assert 'CREATE TABLE "parliament_deputy_observations"' in migration
    assert '"source_document_id", "legislature", "parser_version"' in migration
    assert '"normalised_sha256" CHAR(64) NOT NULL' in migration
    assert '"source_id", "snapshot_id"' in migration
    assert "parliament_deputy_snapshots_append_only" in migration
    assert "parliament_deputy_observations_append_only" in migration
    assert migration.count("EXECUTE FUNCTION reject_parliament_snapshot_mutation()") == 2


def test_deputy_observation_tables_are_closed_to_browser_roles() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    for table in ("parliament_deputy_snapshots", "parliament_deputy_observations"):
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;' in migration
        assert f'REVOKE ALL PRIVILEGES ON "{table}" FROM PUBLIC;' in migration
        assert f"'{table}', api_role" in migration


def test_deputy_observation_schema_has_no_contact_or_tax_identifier_columns() -> None:
    migration = MIGRATION.read_text(encoding="utf-8").casefold()

    for forbidden in ('"email"', '"nif"', '"nipc"', '"tax_id"'):
        assert forbidden not in migration
