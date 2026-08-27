-- V5.42: relações individuais de autoria declaradas pelo ficheiro oficial.
-- A ingestão conserva idCadastro e a iniciativa, mas não cria pessoas,
-- revisões, casos editoriais ou qualquer projeção pública.

CREATE TABLE "parliament_initiative_author_snapshots" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "legislature" TEXT NOT NULL,
    "parser_version" TEXT NOT NULL,
    "normalised_sha256" CHAR(64) NOT NULL,
    "collected_at" TIMESTAMP(3) NOT NULL,
    "initiative_count" INTEGER NOT NULL,
    "authorship_count" INTEGER NOT NULL,
    "deputy_count" INTEGER NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliament_initiative_author_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliament_initiative_author_snapshots_source_document_id_fkey"
        FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliament_initiative_author_snapshots_legislature_nonempty"
        CHECK (length(btrim("legislature")) > 0),
    CONSTRAINT "parliament_initiative_author_snapshots_parser_nonempty"
        CHECK (length(btrim("parser_version")) > 0),
    CONSTRAINT "parliament_initiative_author_snapshots_sha256_format"
        CHECK ("normalised_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "parliament_initiative_author_snapshots_counts_valid"
        CHECK (
            "initiative_count" >= 1
            AND "authorship_count" >= 1
            AND "deputy_count" >= 1
            AND "initiative_count" <= "authorship_count"
            AND "deputy_count" <= "authorship_count"
        )
);

CREATE TABLE "parliament_initiative_author_observations" (
    "id" TEXT NOT NULL,
    "snapshot_id" TEXT NOT NULL,
    "initiative_source_id" TEXT NOT NULL,
    "official_deputy_id" TEXT NOT NULL,
    "parliamentary_name" TEXT NOT NULL,
    "parliamentary_group_label" TEXT,
    "relation" TEXT NOT NULL,
    "source_record_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliament_initiative_author_observations_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliament_initiative_author_observations_snapshot_id_fkey"
        FOREIGN KEY ("snapshot_id") REFERENCES "parliament_initiative_author_snapshots"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliament_initiative_author_observations_initiative_nonempty"
        CHECK (length(btrim("initiative_source_id")) > 0),
    CONSTRAINT "parliament_initiative_author_observations_deputy_nonempty"
        CHECK (length(btrim("official_deputy_id")) > 0),
    CONSTRAINT "parliament_initiative_author_observations_name_nonempty"
        CHECK (length(btrim("parliamentary_name")) > 0),
    CONSTRAINT "parliament_initiative_author_observations_relation_allowed"
        CHECK ("relation" = 'AUTHOR'),
    CONSTRAINT "parliament_initiative_author_observations_sha256_format"
        CHECK ("source_record_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX
    "parliament_initiative_author_snapshots_source_document_legislature_parser_key"
ON "parliament_initiative_author_snapshots"(
    "source_document_id", "legislature", "parser_version"
);

CREATE INDEX "parliament_initiative_author_snapshots_legislature_collected_at_idx"
ON "parliament_initiative_author_snapshots"("legislature", "collected_at");

CREATE UNIQUE INDEX
    "parliament_initiative_author_observations_snapshot_initiative_deputy_key"
ON "parliament_initiative_author_observations"(
    "snapshot_id", "initiative_source_id", "official_deputy_id"
);

CREATE INDEX "parliament_initiative_author_observations_initiative_source_id_idx"
ON "parliament_initiative_author_observations"("initiative_source_id");

CREATE INDEX "parliament_initiative_author_observations_official_deputy_id_idx"
ON "parliament_initiative_author_observations"("official_deputy_id");

CREATE TRIGGER "parliament_initiative_author_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "parliament_initiative_author_snapshots"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

CREATE TRIGGER "parliament_initiative_author_observations_append_only"
BEFORE UPDATE OR DELETE ON "parliament_initiative_author_observations"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

ALTER TABLE "parliament_initiative_author_snapshots" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "parliament_initiative_author_observations" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "parliament_initiative_author_snapshots" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "parliament_initiative_author_observations" FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'parliament_initiative_author_snapshots', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'parliament_initiative_author_observations', api_role
            );
        END IF;
    END LOOP;
END
$$;
