-- Transparência Total V4.4: staging jurídico privado e append-only do DRE.
-- Ingestão, extração de texto e arquivo não constituem publicação. Esta tabela
-- não tem ligação a laws, citizen_alerts, interest_relationships ou outra
-- projeção pública.

CREATE TABLE "dre_document_snapshots" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "sync_run_id" TEXT NOT NULL,
    "official_identifier" TEXT,
    "title" TEXT NOT NULL,
    "document_kind" "DocumentKind" NOT NULL,
    "published_at" TIMESTAMP(3),
    "parser_version" TEXT NOT NULL,
    "normalised_text_sha256" TEXT NOT NULL,
    "extracted_text" TEXT NOT NULL,
    "text_length" INTEGER NOT NULL,
    "collected_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "dre_document_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "dre_document_snapshots_identifier_check"
        CHECK (
            "official_identifier" IS NULL
            OR length(trim("official_identifier")) BETWEEN 1 AND 500
        ),
    CONSTRAINT "dre_document_snapshots_title_check"
        CHECK (length(trim("title")) BETWEEN 1 AND 500),
    CONSTRAINT "dre_document_snapshots_kind_check"
        CHECK ("document_kind" IN ('LAW', 'REGULATION')),
    CONSTRAINT "dre_document_snapshots_parser_version_check"
        CHECK (length(trim("parser_version")) BETWEEN 1 AND 200),
    CONSTRAINT "dre_document_snapshots_normalised_sha256_check"
        CHECK ("normalised_text_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "dre_document_snapshots_text_check"
        CHECK (
            "text_length" BETWEEN 100 AND 5000000
            AND char_length("extracted_text") = "text_length"
        )
);

CREATE UNIQUE INDEX "dre_document_snapshots_sync_run_id_key"
ON "dre_document_snapshots"("sync_run_id");

CREATE UNIQUE INDEX "dre_document_snapshots_source_parser_key"
ON "dre_document_snapshots"("source_document_id", "parser_version");

CREATE INDEX "dre_document_snapshots_identifier_collected_at_idx"
ON "dre_document_snapshots"("official_identifier", "collected_at");

CREATE INDEX "dre_document_snapshots_kind_published_at_idx"
ON "dre_document_snapshots"("document_kind", "published_at");

CREATE INDEX "dre_document_snapshots_normalised_sha256_idx"
ON "dre_document_snapshots"("normalised_text_sha256");

ALTER TABLE "dre_document_snapshots"
ADD CONSTRAINT "dre_document_snapshots_source_document_id_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "dre_document_snapshots"
ADD CONSTRAINT "dre_document_snapshots_sync_run_id_fkey"
FOREIGN KEY ("sync_run_id") REFERENCES "sync_runs"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

-- Mesmo perante escrita SQL direta, um snapshot DRE só pode nascer sobre uma
-- fonte DRE oficial, com bytes atestados, URL/hash coerentes e SyncRun da mesma
-- versão do parser.
CREATE FUNCTION "validate_dre_document_snapshot_insert"()
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
         AND run."source_name" = 'DRE'
         AND run."dataset_url" = source."url"
         AND run."code_version" = NEW."parser_version"
        WHERE source."id" = NEW."source_document_id"
          AND source."publisher" = 'DRE'
          AND source."kind" = NEW."document_kind"
    ) THEN
        RAISE EXCEPTION
            'o snapshot DRE exige SourceDocument oficial, arquivo atestado e SyncRun coerente';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "dre_document_snapshots_validate_insert"
BEFORE INSERT ON "dre_document_snapshots"
FOR EACH ROW EXECUTE FUNCTION "validate_dre_document_snapshot_insert"();

CREATE FUNCTION "reject_dre_staging_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        '% é staging DRE append-only; UPDATE e DELETE são proibidos', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "dre_document_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "dre_document_snapshots"
FOR EACH ROW EXECUTE FUNCTION "reject_dre_staging_mutation"();
