-- Transparência Total V4.2: snapshots privados e append-only do Portal BASE.
-- Ingestão não é publicação: estas tabelas não têm ligação a public_contracts,
-- interest_entities, contract_match_reviews ou interest_relationships.

CREATE TABLE "base_staging_batches" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "sync_run_id" TEXT NOT NULL,
    "resource_year" INTEGER NOT NULL,
    "resource_title" TEXT NOT NULL,
    "resource_format" TEXT NOT NULL,
    "parser_version" TEXT NOT NULL,
    "normalised_sha256" TEXT NOT NULL,
    "identifier_digests_stored" BOOLEAN NOT NULL,
    "contract_count" INTEGER NOT NULL,
    "party_count" INTEGER NOT NULL,
    "collected_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_staging_batches_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_staging_batches_year_check"
        CHECK ("resource_year" BETWEEN 2012 AND 2100),
    CONSTRAINT "base_staging_batches_format_check"
        CHECK ("resource_format" IN ('JSON', 'XML', 'ZIP')),
    CONSTRAINT "base_staging_batches_parser_version_check"
        CHECK (length(trim("parser_version")) BETWEEN 1 AND 200),
    CONSTRAINT "base_staging_batches_normalised_sha256_check"
        CHECK ("normalised_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_staging_batches_counts_check"
        CHECK ("contract_count" > 0 AND "party_count" >= 0),
    CONSTRAINT "base_staging_batches_title_check"
        CHECK (length(trim("resource_title")) BETWEEN 1 AND 500)
);

CREATE UNIQUE INDEX "base_staging_batches_sync_run_id_key"
ON "base_staging_batches"("sync_run_id");

CREATE UNIQUE INDEX "base_staging_batches_source_parser_key"
ON "base_staging_batches"("source_document_id", "parser_version");

CREATE INDEX "base_staging_batches_year_collected_at_idx"
ON "base_staging_batches"("resource_year", "collected_at");

CREATE INDEX "base_staging_batches_normalised_sha256_idx"
ON "base_staging_batches"("normalised_sha256");

CREATE TABLE "base_contract_snapshots" (
    "id" TEXT NOT NULL,
    "batch_id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "object" TEXT NOT NULL,
    "procedure" "PublicContractProcedure" NOT NULL DEFAULT 'UNKNOWN',
    "cpv_code" TEXT,
    "base_value" DECIMAL(20,2),
    "contract_value" DECIMAL(20,2),
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "decision_at" TIMESTAMP(3),
    "signed_at" TIMESTAMP(3),
    "published_at" TIMESTAMP(3),
    "execution_days" INTEGER,
    "direct_official_url" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_contract_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_contract_snapshots_source_id_check"
        CHECK (length(trim("source_id")) BETWEEN 1 AND 500),
    CONSTRAINT "base_contract_snapshots_object_check"
        CHECK (length(trim("object")) > 0),
    CONSTRAINT "base_contract_snapshots_values_check"
        CHECK (
            ("base_value" IS NULL OR "base_value" >= 0)
            AND ("contract_value" IS NULL OR "contract_value" >= 0)
        ),
    CONSTRAINT "base_contract_snapshots_currency_check"
        CHECK ("currency" ~ '^[A-Z]{3}$'),
    CONSTRAINT "base_contract_snapshots_execution_days_check"
        CHECK ("execution_days" IS NULL OR "execution_days" >= 0)
);

CREATE UNIQUE INDEX "base_contract_snapshots_batch_source_key"
ON "base_contract_snapshots"("batch_id", "source_id");

CREATE INDEX "base_contract_snapshots_source_id_idx"
ON "base_contract_snapshots"("source_id");

CREATE INDEX "base_contract_snapshots_procedure_published_at_idx"
ON "base_contract_snapshots"("procedure", "published_at");

CREATE TABLE "base_contract_party_snapshots" (
    "id" TEXT NOT NULL,
    "contract_snapshot_id" TEXT NOT NULL,
    "ordinal" INTEGER NOT NULL,
    "role" "ContractPartyRole" NOT NULL,
    "source_name" TEXT NOT NULL,
    "protected_identifier_digest" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_contract_party_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_contract_party_snapshots_ordinal_check"
        CHECK ("ordinal" >= 0),
    CONSTRAINT "base_contract_party_snapshots_source_name_check"
        CHECK (length(trim("source_name")) BETWEEN 1 AND 500),
    CONSTRAINT "base_contract_party_snapshots_digest_check"
        CHECK (
            "protected_identifier_digest" IS NULL
            OR "protected_identifier_digest" ~ '^[0-9a-f]{64}$'
        )
);

CREATE UNIQUE INDEX "base_contract_party_snapshots_contract_ordinal_key"
ON "base_contract_party_snapshots"("contract_snapshot_id", "ordinal");

CREATE INDEX "base_contract_party_snapshots_role_idx"
ON "base_contract_party_snapshots"("role");

CREATE INDEX "base_contract_party_snapshots_digest_idx"
ON "base_contract_party_snapshots"("protected_identifier_digest");

ALTER TABLE "base_staging_batches"
ADD CONSTRAINT "base_staging_batches_source_document_id_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "base_staging_batches"
ADD CONSTRAINT "base_staging_batches_sync_run_id_fkey"
FOREIGN KEY ("sync_run_id") REFERENCES "sync_runs"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "base_contract_snapshots"
ADD CONSTRAINT "base_contract_snapshots_batch_id_fkey"
FOREIGN KEY ("batch_id") REFERENCES "base_staging_batches"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "base_contract_party_snapshots"
ADD CONSTRAINT "base_contract_party_snapshots_contract_snapshot_id_fkey"
FOREIGN KEY ("contract_snapshot_id") REFERENCES "base_contract_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

-- Mesmo que outro cliente escreva diretamente na base, um lote só pode nascer
-- sobre uma fonte BASE oficial com URL/hash já atestados e um SyncRun coerente.
CREATE FUNCTION "validate_base_staging_batch_insert"()
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
         AND run."source_name" = 'BASE_GOV'
         AND run."dataset_url" = source."url"
         AND run."code_version" = NEW."parser_version"
        WHERE source."id" = NEW."source_document_id"
          AND source."publisher" = 'BASE_GOV'
          AND source."kind" = 'OPEN_DATASET'
    ) THEN
        RAISE EXCEPTION
            'o lote BASE exige SourceDocument oficial, arquivo atestado e SyncRun coerente';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "base_staging_batches_validate_insert"
BEFORE INSERT ON "base_staging_batches"
FOR EACH ROW EXECUTE FUNCTION "validate_base_staging_batch_insert"();

CREATE FUNCTION "reject_base_staging_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        '% é staging append-only; UPDATE e DELETE são proibidos', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "base_staging_batches_append_only"
BEFORE UPDATE OR DELETE ON "base_staging_batches"
FOR EACH ROW EXECUTE FUNCTION "reject_base_staging_mutation"();

CREATE TRIGGER "base_contract_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "base_contract_snapshots"
FOR EACH ROW EXECUTE FUNCTION "reject_base_staging_mutation"();

CREATE TRIGGER "base_contract_party_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "base_contract_party_snapshots"
FOR EACH ROW EXECUTE FUNCTION "reject_base_staging_mutation"();

-- AuditEvent é o histórico de decisões e operações. Correções acrescentam uma
-- nova linha; nunca alteram nem apagam o evento anterior.
CREATE FUNCTION "reject_audit_event_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events é append-only; UPDATE e DELETE são proibidos';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "audit_events_append_only"
BEFORE UPDATE OR DELETE ON "audit_events"
FOR EACH ROW EXECUTE FUNCTION "reject_audit_event_mutation"();

