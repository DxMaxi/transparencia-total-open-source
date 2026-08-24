-- V5.27: fotografias privadas, versionadas e append-only da atividade biográfica
-- dos deputados. Estas tabelas não são uma projeção pública e não criam pessoas,
-- mandatos, relações partidárias ou decisões editoriais automaticamente.

CREATE TABLE "parliament_deputy_snapshots" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "legislature" TEXT NOT NULL,
    "parser_version" TEXT NOT NULL,
    "normalised_sha256" CHAR(64) NOT NULL,
    "collected_at" TIMESTAMP(3) NOT NULL,
    "deputy_count" INTEGER NOT NULL,
    "group_period_count" INTEGER NOT NULL,
    "situation_period_count" INTEGER NOT NULL,
    "office_period_count" INTEGER NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliament_deputy_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliament_deputy_snapshots_source_document_id_fkey"
        FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliament_deputy_snapshots_counts_nonnegative"
        CHECK (
            "deputy_count" >= 0
            AND "group_period_count" >= 0
            AND "situation_period_count" >= 0
            AND "office_period_count" >= 0
        ),
    CONSTRAINT "parliament_deputy_snapshots_normalised_sha256_format"
        CHECK ("normalised_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE TABLE "parliament_deputy_observations" (
    "id" TEXT NOT NULL,
    "snapshot_id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "candidate_source_id" TEXT,
    "parliamentary_name" TEXT NOT NULL,
    "full_name" TEXT,
    "constituency_source_id" TEXT,
    "constituency_label" TEXT,
    "parliamentary_groups" JSONB NOT NULL DEFAULT '[]'::jsonb,
    "mandate_situations" JSONB NOT NULL DEFAULT '[]'::jsonb,
    "offices" JSONB NOT NULL DEFAULT '[]'::jsonb,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliament_deputy_observations_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliament_deputy_observations_snapshot_id_fkey"
        FOREIGN KEY ("snapshot_id") REFERENCES "parliament_deputy_snapshots"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliament_deputy_observations_source_id_nonempty"
        CHECK (length(btrim("source_id")) > 0),
    CONSTRAINT "parliament_deputy_observations_name_nonempty"
        CHECK (length(btrim("parliamentary_name")) > 0),
    CONSTRAINT "parliament_deputy_observations_groups_array"
        CHECK (jsonb_typeof("parliamentary_groups") = 'array'),
    CONSTRAINT "parliament_deputy_observations_situations_array"
        CHECK (jsonb_typeof("mandate_situations") = 'array'),
    CONSTRAINT "parliament_deputy_observations_offices_array"
        CHECK (jsonb_typeof("offices") = 'array')
);

CREATE UNIQUE INDEX
    "parliament_deputy_snapshots_source_document_id_legislature_parser_version_key"
ON "parliament_deputy_snapshots"(
    "source_document_id", "legislature", "parser_version"
);

CREATE INDEX "parliament_deputy_snapshots_legislature_collected_at_idx"
ON "parliament_deputy_snapshots"("legislature", "collected_at");

CREATE UNIQUE INDEX "parliament_deputy_observations_source_id_snapshot_id_key"
ON "parliament_deputy_observations"("source_id", "snapshot_id");

CREATE INDEX "parliament_deputy_observations_snapshot_id_idx"
ON "parliament_deputy_observations"("snapshot_id");

CREATE INDEX "parliament_deputy_observations_constituency_source_id_idx"
ON "parliament_deputy_observations"("constituency_source_id");

DROP TRIGGER IF EXISTS parliament_deputy_snapshots_append_only
ON "parliament_deputy_snapshots";
CREATE TRIGGER parliament_deputy_snapshots_append_only
BEFORE UPDATE OR DELETE ON "parliament_deputy_snapshots"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

DROP TRIGGER IF EXISTS parliament_deputy_observations_append_only
ON "parliament_deputy_observations";
CREATE TRIGGER parliament_deputy_observations_append_only
BEFORE UPDATE OR DELETE ON "parliament_deputy_observations"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

ALTER TABLE "parliament_deputy_snapshots" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "parliament_deputy_observations" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "parliament_deputy_snapshots" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "parliament_deputy_observations" FROM PUBLIC;

DO $$
DECLARE
  api_role TEXT;
BEGIN
  FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
      EXECUTE format(
        'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
        'parliament_deputy_snapshots', api_role
      );
      EXECUTE format(
        'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
        'parliament_deputy_observations', api_role
      );
    END IF;
  END LOOP;
END
$$;
