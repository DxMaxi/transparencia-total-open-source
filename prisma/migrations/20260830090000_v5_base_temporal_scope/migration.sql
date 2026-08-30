-- V5.49: âmbito temporal privado e auditável dos contratos do Portal BASE.
--
-- Esta migração conserva apenas o catálogo oficial do dados.gov.pt. Não descarrega
-- contratos, não cria PublicContract, não cria correspondências e não publica dados.

CREATE TABLE "base_contract_catalogue_scopes" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "sync_run_id" TEXT NOT NULL,
    "dataset_id" TEXT NOT NULL,
    "dataset_title" TEXT NOT NULL,
    "producer_id" TEXT NOT NULL,
    "producer_name" TEXT NOT NULL,
    "licence_code" TEXT NOT NULL,
    "update_frequency" TEXT NOT NULL,
    "public_dataset_url" TEXT NOT NULL,
    "parser_version" TEXT NOT NULL,
    "policy_version" TEXT NOT NULL,
    "first_year" INTEGER NOT NULL,
    "closed_through_year" INTEGER NOT NULL,
    "rolling_year" INTEGER NOT NULL,
    "source_sha256" CHAR(64) NOT NULL,
    "scope_sha256" CHAR(64) NOT NULL,
    "source_byte_size" INTEGER NOT NULL,
    "resource_count" INTEGER NOT NULL,
    "retrieved_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_contract_catalogue_scopes_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_contract_catalogue_scopes_source_document_fkey"
        FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_catalogue_scopes_sync_run_fkey"
        FOREIGN KEY ("sync_run_id") REFERENCES "sync_runs"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_catalogue_scopes_dataset_check"
        CHECK ("dataset_id" = '66d72d488ca4b7cb2de28712'),
    CONSTRAINT "base_contract_catalogue_scopes_producer_check"
        CHECK ("producer_id" = '5ae97fa2c8d8c915d5faa3bf'),
    CONSTRAINT "base_contract_catalogue_scopes_licence_check"
        CHECK ("licence_code" = 'other-pd'),
    CONSTRAINT "base_contract_catalogue_scopes_frequency_check"
        CHECK ("update_frequency" = 'weekly'),
    CONSTRAINT "base_contract_catalogue_scopes_public_url_check"
        CHECK (
            "public_dataset_url" =
            'https://dados.gov.pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2026'
        ),
    CONSTRAINT "base_contract_catalogue_scopes_versions_check"
        CHECK (
            "parser_version" = 'base-contracts-catalogue-v1'
            AND "policy_version" = 'base-temporal-scope-v1'
        ),
    CONSTRAINT "base_contract_catalogue_scopes_years_check"
        CHECK (
            "first_year" = 2012
            AND "rolling_year" BETWEEN 2013 AND 2100
            AND "closed_through_year" = "rolling_year" - 1
        ),
    CONSTRAINT "base_contract_catalogue_scopes_hashes_check"
        CHECK (
            "source_sha256" ~ '^[0-9a-f]{64}$'
            AND "scope_sha256" ~ '^[0-9a-f]{64}$'
        ),
    CONSTRAINT "base_contract_catalogue_scopes_counts_check"
        CHECK (
            "source_byte_size" BETWEEN 1 AND 10000000
            AND "resource_count" = "rolling_year" - "first_year" + 1
        )
);

CREATE UNIQUE INDEX "base_contract_catalogue_scopes_source_parser_key"
ON "base_contract_catalogue_scopes"("source_document_id", "parser_version");
CREATE UNIQUE INDEX "base_contract_catalogue_scopes_sync_run_key"
ON "base_contract_catalogue_scopes"("sync_run_id");
CREATE INDEX "base_contract_catalogue_scopes_years_retrieved_idx"
ON "base_contract_catalogue_scopes"("first_year", "rolling_year", "retrieved_at" DESC);
CREATE INDEX "base_contract_catalogue_scopes_hash_idx"
ON "base_contract_catalogue_scopes"("scope_sha256");

CREATE TABLE "base_contract_catalogue_resources" (
    "id" TEXT NOT NULL,
    "scope_id" TEXT NOT NULL,
    "ordinal" INTEGER NOT NULL,
    "source_resource_id" TEXT NOT NULL,
    "resource_year" INTEGER NOT NULL,
    "coverage_state" TEXT NOT NULL,
    "resource_title" TEXT NOT NULL,
    "resource_format" TEXT NOT NULL,
    "versioned_url" TEXT NOT NULL,
    "stable_url" TEXT NOT NULL,
    "source_modified_at" TIMESTAMP(3) NOT NULL,
    "byte_size" INTEGER NOT NULL,
    "metadata_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_contract_catalogue_resources_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_contract_catalogue_resources_scope_fkey"
        FOREIGN KEY ("scope_id") REFERENCES "base_contract_catalogue_scopes"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_catalogue_resources_ordinal_check"
        CHECK ("ordinal" >= 0),
    CONSTRAINT "base_contract_catalogue_resources_id_check"
        CHECK ("source_resource_id" ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    CONSTRAINT "base_contract_catalogue_resources_year_check"
        CHECK ("resource_year" BETWEEN 2012 AND 2100),
    CONSTRAINT "base_contract_catalogue_resources_state_check"
        CHECK ("coverage_state" IN ('HISTORICAL_CLOSED_YEAR', 'CURRENT_ROLLING_YEAR')),
    CONSTRAINT "base_contract_catalogue_resources_format_check"
        CHECK ("resource_format" = 'ZIP'),
    CONSTRAINT "base_contract_catalogue_resources_title_check"
        CHECK (
            lower("resource_title") =
            ('contratos' || "resource_year"::TEXT || '.zip')
        ),
    CONSTRAINT "base_contract_catalogue_resources_versioned_url_check"
        CHECK (
            "versioned_url" LIKE 'https://dados.gov.pt/%'
            AND lower("versioned_url") LIKE
                ('%/contratos' || "resource_year"::TEXT || '.zip')
        ),
    CONSTRAINT "base_contract_catalogue_resources_stable_url_check"
        CHECK (
            "stable_url" =
            ('https://dados.gov.pt/api/1/datasets/r/' || "source_resource_id")
        ),
    CONSTRAINT "base_contract_catalogue_resources_size_check"
        CHECK ("byte_size" BETWEEN 1 AND 500000000),
    CONSTRAINT "base_contract_catalogue_resources_hash_check"
        CHECK ("metadata_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX "base_contract_catalogue_resources_scope_year_key"
ON "base_contract_catalogue_resources"("scope_id", "resource_year");
CREATE UNIQUE INDEX "base_contract_catalogue_resources_scope_ordinal_key"
ON "base_contract_catalogue_resources"("scope_id", "ordinal");
CREATE UNIQUE INDEX "base_contract_catalogue_resources_scope_source_key"
ON "base_contract_catalogue_resources"("scope_id", "source_resource_id");
CREATE INDEX "base_contract_catalogue_resources_state_year_idx"
ON "base_contract_catalogue_resources"("coverage_state", "resource_year");

CREATE FUNCTION "validate_base_contract_catalogue_scope_insert"()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM "source_documents" AS source
        JOIN "source_archive_attestations" AS archive
          ON archive."source_document_id" = source."id"
         AND archive."content_sha256" = source."content_sha256"
         AND archive."retrieval_url" = source."url"
        JOIN "sync_runs" AS run
          ON run."id" = NEW."sync_run_id"
         AND run."source_name" = 'BASE_CONTRACTS_CATALOGUE_PRIVATE'
         AND run."dataset_url" = source."url"
         AND run."code_version" = NEW."parser_version"
        WHERE source."id" = NEW."source_document_id"
          AND source."publisher" = 'BASE_GOV'
          AND source."kind" = 'OPEN_DATASET'
          AND source."url" =
              'https://dados.gov.pt/api/1/datasets/66d72d488ca4b7cb2de28712/'
          AND source."content_sha256" = NEW."source_sha256"
          AND source."retrieved_at" = NEW."retrieved_at"
          AND archive."byte_size" = NEW."source_byte_size"
    ) THEN
        RAISE EXCEPTION
            'o âmbito BASE exige catálogo oficial, arquivo atestado e SyncRun privado coerente';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION "validate_base_contract_catalogue_completion"()
RETURNS TRIGGER AS $$
DECLARE
    target_scope_id TEXT;
    scope_row "base_contract_catalogue_scopes"%ROWTYPE;
    observed_count INTEGER;
    observed_min INTEGER;
    observed_max INTEGER;
    invalid_rows INTEGER;
BEGIN
    IF TG_TABLE_NAME = 'base_contract_catalogue_scopes' THEN
        target_scope_id := to_jsonb(NEW)->>'id';
    ELSE
        target_scope_id := to_jsonb(NEW)->>'scope_id';
    END IF;
    SELECT * INTO scope_row
    FROM "base_contract_catalogue_scopes"
    WHERE "id" = target_scope_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'o âmbito BASE associado não existe';
    END IF;

    SELECT COUNT(*), MIN("resource_year"), MAX("resource_year"),
           COUNT(*) FILTER (
               WHERE "ordinal" <> "resource_year" - scope_row."first_year"
                  OR "source_modified_at" > scope_row."retrieved_at"
                  OR (
                       "resource_year" <= scope_row."closed_through_year"
                       AND "coverage_state" <> 'HISTORICAL_CLOSED_YEAR'
                     )
                  OR (
                       "resource_year" = scope_row."rolling_year"
                       AND "coverage_state" <> 'CURRENT_ROLLING_YEAR'
                     )
                  OR "resource_year" < scope_row."first_year"
                  OR "resource_year" > scope_row."rolling_year"
           )
    INTO observed_count, observed_min, observed_max, invalid_rows
    FROM "base_contract_catalogue_resources"
    WHERE "scope_id" = target_scope_id;

    IF observed_count <> scope_row."resource_count"
       OR observed_min <> scope_row."first_year"
       OR observed_max <> scope_row."rolling_year"
       OR invalid_rows <> 0
    THEN
        RAISE EXCEPTION
            'o âmbito BASE exige exatamente um recurso anual coerente entre o primeiro ano e o ano corrente';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION "reject_base_contract_catalogue_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'o âmbito privado BASE é append-only; UPDATE e DELETE são proibidos';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "base_contract_catalogue_scope_validate_insert"
BEFORE INSERT ON "base_contract_catalogue_scopes"
FOR EACH ROW EXECUTE FUNCTION "validate_base_contract_catalogue_scope_insert"();

CREATE CONSTRAINT TRIGGER "base_contract_catalogue_scope_validate_completion"
AFTER INSERT ON "base_contract_catalogue_scopes"
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION "validate_base_contract_catalogue_completion"();

CREATE CONSTRAINT TRIGGER "base_contract_catalogue_resource_validate_completion"
AFTER INSERT ON "base_contract_catalogue_resources"
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION "validate_base_contract_catalogue_completion"();

CREATE TRIGGER "base_contract_catalogue_scopes_append_only"
BEFORE UPDATE OR DELETE ON "base_contract_catalogue_scopes"
FOR EACH ROW EXECUTE FUNCTION "reject_base_contract_catalogue_mutation"();
CREATE TRIGGER "base_contract_catalogue_resources_append_only"
BEFORE UPDATE OR DELETE ON "base_contract_catalogue_resources"
FOR EACH ROW EXECUTE FUNCTION "reject_base_contract_catalogue_mutation"();

ALTER TABLE "base_contract_catalogue_scopes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "base_contract_catalogue_resources" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "base_contract_catalogue_scopes" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "base_contract_catalogue_resources" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_base_contract_catalogue_scope_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_base_contract_catalogue_completion"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_base_contract_catalogue_mutation"() FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'base_contract_catalogue_scopes', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'base_contract_catalogue_resources', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_base_contract_catalogue_scope_insert', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_base_contract_catalogue_completion', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_base_contract_catalogue_mutation', api_role
            );
        END IF;
    END LOOP;
END
$$;
