-- V5.48: catálogo integral privado do Programa do XXV Governo.
--
-- Esta migração não promove dados. Cada item explicitamente enumerado fica
-- PENDING, sem critério atribuído automaticamente e sem qualquer projeção em
-- government_programmes, promises ou promise_reviews.

CREATE TABLE "government_programme_snapshots" (
    "id" TEXT NOT NULL,
    "government_number" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "source_content_sha256" CHAR(64) NOT NULL,
    "source_byte_size" INTEGER NOT NULL,
    "source_page_count" INTEGER NOT NULL,
    "methodology_version" TEXT NOT NULL,
    "parser_version" TEXT NOT NULL,
    "layout_manifest_sha256" CHAR(64) NOT NULL,
    "catalogue_sha256" CHAR(64) NOT NULL,
    "candidate_count" INTEGER NOT NULL,
    "coverage_block_count" INTEGER NOT NULL,
    "catalogue_state" TEXT NOT NULL DEFAULT 'PRIVATE_PENDING_REVIEW',
    "publication_performed" BOOLEAN NOT NULL DEFAULT FALSE,
    "observed_at" TIMESTAMP(3) NOT NULL,
    "staged_by_alias" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "government_programme_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "government_programme_snapshot_source_sha_check"
        CHECK ("source_content_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "government_programme_snapshot_layout_sha_check"
        CHECK ("layout_manifest_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "government_programme_snapshot_catalogue_sha_check"
        CHECK ("catalogue_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "government_programme_snapshot_source_size_check"
        CHECK ("source_byte_size" BETWEEN 100000 AND 50000000),
    CONSTRAINT "government_programme_snapshot_page_count_check"
        CHECK ("source_page_count" BETWEEN 1 AND 2000),
    CONSTRAINT "government_programme_snapshot_candidate_count_check"
        CHECK ("candidate_count" BETWEEN 1 AND 10000),
    CONSTRAINT "government_programme_snapshot_coverage_count_check"
        CHECK ("coverage_block_count" BETWEEN 1 AND 500),
    CONSTRAINT "government_programme_snapshot_state_check"
        CHECK ("catalogue_state" = 'PRIVATE_PENDING_REVIEW'),
    CONSTRAINT "government_programme_snapshot_no_publication_check"
        CHECK ("publication_performed" = FALSE),
    CONSTRAINT "government_programme_snapshot_actor_check"
        CHECK (length(trim("staged_by_alias")) BETWEEN 3 AND 120)
);

CREATE UNIQUE INDEX "government_programme_snapshot_source_method_key"
ON "government_programme_snapshots"("source_document_id", "methodology_version");
CREATE INDEX "government_programme_snapshot_government_observed_idx"
ON "government_programme_snapshots"("government_number", "observed_at");
CREATE INDEX "government_programme_snapshot_source_sha_idx"
ON "government_programme_snapshots"("source_content_sha256");

CREATE TABLE "government_promise_catalogue_coverage" (
    "id" TEXT NOT NULL,
    "snapshot_id" TEXT NOT NULL,
    "block_id" TEXT NOT NULL,
    "part" TEXT NOT NULL,
    "area" TEXT NOT NULL,
    "section_path" TEXT NOT NULL,
    "start_page" INTEGER NOT NULL,
    "end_page" INTEGER NOT NULL,
    "start_anchor" TEXT NOT NULL,
    "end_anchor" TEXT,
    "extraction_state" TEXT NOT NULL DEFAULT 'EXTRACTED',
    "candidate_count" INTEGER NOT NULL,
    "block_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "government_promise_catalogue_coverage_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "government_promise_coverage_pages_check"
        CHECK ("start_page" >= 1 AND "end_page" >= "start_page"),
    CONSTRAINT "government_promise_coverage_state_check"
        CHECK ("extraction_state" = 'EXTRACTED'),
    CONSTRAINT "government_promise_coverage_count_check"
        CHECK ("candidate_count" >= 1),
    CONSTRAINT "government_promise_coverage_sha_check"
        CHECK ("block_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "government_promise_coverage_text_check"
        CHECK (
            length(trim("block_id")) BETWEEN 3 AND 100
            AND length(trim("part")) BETWEEN 3 AND 80
            AND length(trim("area")) BETWEEN 2 AND 160
            AND length(trim("section_path")) BETWEEN 2 AND 300
            AND length(trim("start_anchor")) BETWEEN 2 AND 300
        )
);

CREATE UNIQUE INDEX "government_promise_coverage_snapshot_block_key"
ON "government_promise_catalogue_coverage"("snapshot_id", "block_id");
CREATE INDEX "government_promise_coverage_snapshot_page_idx"
ON "government_promise_catalogue_coverage"("snapshot_id", "start_page");

CREATE TABLE "government_promise_candidates" (
    "id" TEXT NOT NULL,
    "snapshot_id" TEXT NOT NULL,
    "candidate_key" TEXT NOT NULL,
    "block_id" TEXT NOT NULL,
    "ordinal" INTEGER NOT NULL,
    "parent_ordinal" INTEGER,
    "hierarchy_level" INTEGER NOT NULL,
    "source_marker" TEXT NOT NULL,
    "area" TEXT NOT NULL,
    "section_path" TEXT NOT NULL,
    "programme_page_start" INTEGER NOT NULL,
    "programme_page_end" INTEGER NOT NULL,
    "statement_text" TEXT NOT NULL,
    "statement_sha256" CHAR(64) NOT NULL,
    "source_locator_sha256" CHAR(64) NOT NULL,
    "identification_basis" TEXT NOT NULL DEFAULT 'EXPLICIT_ENUMERATED_PROGRAMME_ITEM',
    "criterion_state" TEXT NOT NULL DEFAULT 'REQUIRES_HUMAN_DEFINITION',
    "review_state" TEXT NOT NULL DEFAULT 'PENDING',
    "publication_state" TEXT NOT NULL DEFAULT 'PRIVATE_NOT_PUBLISHED',
    "publication_performed" BOOLEAN NOT NULL DEFAULT FALSE,
    "observed_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "government_promise_candidates_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "government_promise_candidate_ordinal_check"
        CHECK ("ordinal" >= 1 AND ("parent_ordinal" IS NULL OR "parent_ordinal" < "ordinal")),
    CONSTRAINT "government_promise_candidate_level_check"
        CHECK ("hierarchy_level" BETWEEN 1 AND 3),
    CONSTRAINT "government_promise_candidate_pages_check"
        CHECK (
            "programme_page_start" >= 1
            AND "programme_page_end" >= "programme_page_start"
        ),
    CONSTRAINT "government_promise_candidate_statement_check"
        CHECK (length(trim("statement_text")) BETWEEN 3 AND 12000),
    CONSTRAINT "government_promise_candidate_statement_sha_check"
        CHECK ("statement_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "government_promise_candidate_locator_sha_check"
        CHECK ("source_locator_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "government_promise_candidate_basis_check"
        CHECK ("identification_basis" = 'EXPLICIT_ENUMERATED_PROGRAMME_ITEM'),
    CONSTRAINT "government_promise_candidate_criterion_check"
        CHECK ("criterion_state" = 'REQUIRES_HUMAN_DEFINITION'),
    CONSTRAINT "government_promise_candidate_review_check"
        CHECK ("review_state" = 'PENDING'),
    CONSTRAINT "government_promise_candidate_publication_state_check"
        CHECK ("publication_state" = 'PRIVATE_NOT_PUBLISHED'),
    CONSTRAINT "government_promise_candidate_no_publication_check"
        CHECK ("publication_performed" = FALSE)
);

CREATE UNIQUE INDEX "government_promise_candidate_snapshot_key"
ON "government_promise_candidates"("snapshot_id", "candidate_key");
CREATE UNIQUE INDEX "government_promise_candidate_snapshot_ordinal_key"
ON "government_promise_candidates"("snapshot_id", "block_id", "ordinal");
CREATE INDEX "government_promise_candidate_snapshot_area_page_idx"
ON "government_promise_candidates"("snapshot_id", "area", "programme_page_start");
CREATE INDEX "government_promise_candidate_review_created_idx"
ON "government_promise_candidates"("review_state", "created_at");
CREATE INDEX "government_promise_candidate_statement_sha_idx"
ON "government_promise_candidates"("statement_sha256");

ALTER TABLE "government_programme_snapshots"
ADD CONSTRAINT "government_programme_snapshot_source_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "government_promise_catalogue_coverage"
ADD CONSTRAINT "government_promise_coverage_snapshot_fkey"
FOREIGN KEY ("snapshot_id") REFERENCES "government_programme_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "government_promise_candidates"
ADD CONSTRAINT "government_promise_candidate_snapshot_fkey"
FOREIGN KEY ("snapshot_id") REFERENCES "government_programme_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE FUNCTION "validate_government_programme_snapshot_insert"()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM "source_documents" AS source
        WHERE source."id" = NEW."source_document_id"
          AND source."publisher" = 'OTHER_OFFICIAL'
          AND source."kind" = 'GOVERNMENT_PROGRAMME'
          AND source."content_sha256" = NEW."source_content_sha256"
          AND source."url" LIKE 'https://portugal.gov.pt/%'
          AND EXISTS (
              SELECT 1
              FROM "source_archive_attestations" AS archive
              WHERE archive."source_document_id" = source."id"
                AND archive."content_sha256" = source."content_sha256"
                AND archive."retrieval_url" = source."url"
                AND archive."retrieved_at" = source."retrieved_at"
                AND archive."byte_size" = NEW."source_byte_size"
          )
    ) THEN
        RAISE EXCEPTION
            'o catálogo exige o PDF oficial do Governo previamente arquivado e atestado';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION "validate_government_programme_catalogue_completion"()
RETURNS TRIGGER AS $$
DECLARE
    observed_candidates INTEGER;
    observed_blocks INTEGER;
    mismatched_blocks INTEGER;
BEGIN
    SELECT count(*) INTO observed_candidates
    FROM "government_promise_candidates"
    WHERE "snapshot_id" = NEW."id";

    SELECT count(*) INTO observed_blocks
    FROM "government_promise_catalogue_coverage"
    WHERE "snapshot_id" = NEW."id";

    SELECT count(*) INTO mismatched_blocks
    FROM "government_promise_catalogue_coverage" AS coverage
    WHERE coverage."snapshot_id" = NEW."id"
      AND coverage."candidate_count" <> (
          SELECT count(*)
          FROM "government_promise_candidates" AS candidate
          WHERE candidate."snapshot_id" = NEW."id"
            AND candidate."block_id" = coverage."block_id"
      );

    IF observed_candidates <> NEW."candidate_count"
       OR observed_blocks <> NEW."coverage_block_count"
       OR mismatched_blocks <> 0 THEN
        RAISE EXCEPTION
            'o catálogo privado não coincide com as contagens do manifesto validado';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION "reject_government_programme_catalogue_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'o catálogo privado do programa é append-only; UPDATE e DELETE são proibidos';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "government_programme_snapshot_validate_insert"
BEFORE INSERT ON "government_programme_snapshots"
FOR EACH ROW EXECUTE FUNCTION "validate_government_programme_snapshot_insert"();

CREATE CONSTRAINT TRIGGER "government_programme_catalogue_validate_completion"
AFTER INSERT ON "government_programme_snapshots"
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION "validate_government_programme_catalogue_completion"();

CREATE TRIGGER "government_programme_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "government_programme_snapshots"
FOR EACH ROW EXECUTE FUNCTION "reject_government_programme_catalogue_mutation"();
CREATE TRIGGER "government_promise_coverage_append_only"
BEFORE UPDATE OR DELETE ON "government_promise_catalogue_coverage"
FOR EACH ROW EXECUTE FUNCTION "reject_government_programme_catalogue_mutation"();
CREATE TRIGGER "government_promise_candidates_append_only"
BEFORE UPDATE OR DELETE ON "government_promise_candidates"
FOR EACH ROW EXECUTE FUNCTION "reject_government_programme_catalogue_mutation"();

ALTER TABLE "government_programme_snapshots" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "government_promise_catalogue_coverage" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "government_promise_candidates" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "government_programme_snapshots" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "government_promise_catalogue_coverage" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "government_promise_candidates" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_government_programme_snapshot_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_government_programme_catalogue_completion"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_government_programme_catalogue_mutation"() FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'government_programme_snapshots', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'government_promise_catalogue_coverage', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'government_promise_candidates', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_government_programme_snapshot_insert', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_government_programme_catalogue_completion', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_government_programme_catalogue_mutation', api_role
            );
        END IF;
    END LOOP;
END
$$;
