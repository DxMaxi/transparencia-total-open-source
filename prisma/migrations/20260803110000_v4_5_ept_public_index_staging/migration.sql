-- Transparência Total V4.5: índice público mínimo da Entidade para a Transparência.
-- Apenas metadados de recursos abertamente publicados. Não são recolhidos conteúdos
-- de declarações, identificadores pessoais, formulários ou áreas autenticadas.

CREATE TABLE "ept_index_snapshots" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "sync_run_id" TEXT NOT NULL,
    "parser_version" TEXT NOT NULL,
    "resource_count" INTEGER NOT NULL,
    "legal_review_status" TEXT NOT NULL DEFAULT 'REQUIRES_LEGAL_REVIEW',
    "collected_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ept_index_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ept_index_snapshots_parser_version_check"
        CHECK (length(trim("parser_version")) BETWEEN 1 AND 200),
    CONSTRAINT "ept_index_snapshots_resource_count_check"
        CHECK ("resource_count" >= 0),
    CONSTRAINT "ept_index_snapshots_legal_review_status_check"
        CHECK ("legal_review_status" = 'REQUIRES_LEGAL_REVIEW')
);

CREATE TABLE "ept_resource_snapshots" (
    "id" TEXT NOT NULL,
    "index_snapshot_id" TEXT NOT NULL,
    "ordinal" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "resource_url" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ept_resource_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ept_resource_snapshots_ordinal_check" CHECK ("ordinal" >= 0),
    CONSTRAINT "ept_resource_snapshots_title_check"
        CHECK (length(trim("title")) BETWEEN 1 AND 500),
    CONSTRAINT "ept_resource_snapshots_category_check"
        CHECK (length(trim("category")) BETWEEN 1 AND 500),
    CONSTRAINT "ept_resource_snapshots_url_check"
        CHECK ("resource_url" ~ '^https://')
);

CREATE UNIQUE INDEX "ept_index_snapshots_sync_run_id_key"
ON "ept_index_snapshots"("sync_run_id");

CREATE UNIQUE INDEX "ept_index_snapshots_source_parser_key"
ON "ept_index_snapshots"("source_document_id", "parser_version");

CREATE UNIQUE INDEX "ept_resource_snapshots_index_ordinal_key"
ON "ept_resource_snapshots"("index_snapshot_id", "ordinal");

CREATE UNIQUE INDEX "ept_resource_snapshots_index_url_key"
ON "ept_resource_snapshots"("index_snapshot_id", "resource_url");

ALTER TABLE "ept_index_snapshots"
ADD CONSTRAINT "ept_index_snapshots_source_document_id_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "ept_index_snapshots"
ADD CONSTRAINT "ept_index_snapshots_sync_run_id_fkey"
FOREIGN KEY ("sync_run_id") REFERENCES "sync_runs"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "ept_resource_snapshots"
ADD CONSTRAINT "ept_resource_snapshots_index_snapshot_id_fkey"
FOREIGN KEY ("index_snapshot_id") REFERENCES "ept_index_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE FUNCTION "validate_ept_index_snapshot_insert"()
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
         AND run."source_name" = 'TRANSPARENCY_ENTITY'
         AND run."dataset_url" = source."url"
         AND run."code_version" = NEW."parser_version"
        WHERE source."id" = NEW."source_document_id"
          AND source."publisher" = 'TRANSPARENCY_ENTITY'
          AND source."kind" = 'DECLARATION'
    ) THEN
        RAISE EXCEPTION
            'o índice EPT exige SourceDocument oficial, arquivo atestado e SyncRun coerente';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "ept_index_snapshots_validate_insert"
BEFORE INSERT ON "ept_index_snapshots"
FOR EACH ROW EXECUTE FUNCTION "validate_ept_index_snapshot_insert"();

CREATE FUNCTION "reject_ept_staging_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        '% é staging EPT append-only; UPDATE e DELETE são proibidos', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "ept_index_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "ept_index_snapshots"
FOR EACH ROW EXECUTE FUNCTION "reject_ept_staging_mutation"();

CREATE TRIGGER "ept_resource_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "ept_resource_snapshots"
FOR EACH ROW EXECUTE FUNCTION "reject_ept_staging_mutation"();
