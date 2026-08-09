-- Pin every V4 trigger function to a deterministic search path.
-- The validating functions resolve private evidence tables in public; the
-- mutation guards need only PostgreSQL's trusted pg_catalog schema.

ALTER FUNCTION public.validate_source_archive_attestation_insert()
    SET search_path = pg_catalog, public;
ALTER FUNCTION public.protect_attested_source_document_anchor()
    SET search_path = pg_catalog, public;
ALTER FUNCTION public.reject_source_archive_attestation_mutation()
    SET search_path = pg_catalog;

ALTER FUNCTION public.validate_base_staging_batch_insert()
    SET search_path = pg_catalog, public;
ALTER FUNCTION public.reject_base_staging_mutation()
    SET search_path = pg_catalog;
ALTER FUNCTION public.reject_audit_event_mutation()
    SET search_path = pg_catalog;
ALTER FUNCTION public.reject_base_staging_batch_mutation_except_eligibility()
    SET search_path = pg_catalog;

ALTER FUNCTION public.validate_dre_document_snapshot_insert()
    SET search_path = pg_catalog, public;
ALTER FUNCTION public.reject_dre_staging_mutation()
    SET search_path = pg_catalog;

ALTER FUNCTION public.validate_ept_index_snapshot_insert()
    SET search_path = pg_catalog, public;
ALTER FUNCTION public.reject_ept_staging_mutation()
    SET search_path = pg_catalog;

ALTER FUNCTION public.reject_v4_rollout_mutation()
    SET search_path = pg_catalog;
ALTER FUNCTION public.reject_parliament_snapshot_mutation()
    SET search_path = pg_catalog;
