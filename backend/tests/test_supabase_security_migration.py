"""Contratos de hardening PostgreSQL verificados pelo advisor Supabase."""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "prisma"
    / "migrations"
    / "20260809043000_v4_pin_database_function_search_paths"
    / "migration.sql"
)

FUNCTIONS_REQUIRING_PRIVATE_TABLES = {
    "validate_source_archive_attestation_insert",
    "protect_attested_source_document_anchor",
    "validate_base_staging_batch_insert",
    "validate_dre_document_snapshot_insert",
    "validate_ept_index_snapshot_insert",
}

PURE_TRIGGER_GUARDS = {
    "reject_source_archive_attestation_mutation",
    "reject_base_staging_mutation",
    "reject_audit_event_mutation",
    "reject_base_staging_batch_mutation_except_eligibility",
    "reject_dre_staging_mutation",
    "reject_ept_staging_mutation",
    "reject_v4_rollout_mutation",
    "reject_parliament_snapshot_mutation",
}


def test_every_v4_trigger_function_has_a_fixed_minimal_search_path() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    for function_name in FUNCTIONS_REQUIRING_PRIVATE_TABLES:
        assert (
            f"ALTER FUNCTION public.{function_name}()\n    SET search_path = pg_catalog, public;"
        ) in migration

    for function_name in PURE_TRIGGER_GUARDS:
        assert (
            f"ALTER FUNCTION public.{function_name}()\n    SET search_path = pg_catalog;"
        ) in migration

    assert migration.count("ALTER FUNCTION public.") == 13
    assert migration.count("SET search_path =") == 13
