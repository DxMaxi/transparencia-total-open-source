-- Transparência Total V4: fotografias parlamentares versionadas e append-only.
-- Cada identificador oficial pode reaparecer em novas recolhas, mas nunca é
-- sobrescrito: a identidade de uma observação inclui o documento-fonte.

ALTER TABLE "vote_events"
ADD COLUMN IF NOT EXISTS "legislature" TEXT NOT NULL DEFAULT 'UNKNOWN';

ALTER TABLE "parliamentary_membership_snapshots"
ADD COLUMN IF NOT EXISTS "parliamentary_name" TEXT,
ADD COLUMN IF NOT EXISTS "full_name" TEXT;

UPDATE "vote_events" AS event
SET "legislature" = initiative."legislature"
FROM "parliamentary_initiatives" AS initiative
WHERE event."initiative_id" = initiative."id"
  AND event."legislature" = 'UNKNOWN';

DROP INDEX IF EXISTS "parliamentary_sessions_source_id_key";
DROP INDEX IF EXISTS "parliamentary_initiatives_source_id_key";
DROP INDEX IF EXISTS "vote_events_source_id_key";

CREATE TABLE "parliament_activity_snapshots" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "legislature" TEXT NOT NULL,
    "parser_version" TEXT NOT NULL,
    "normalised_sha256" CHAR(64) NOT NULL,
    "collected_at" TIMESTAMP(3) NOT NULL,
    "session_count" INTEGER NOT NULL,
    "initiative_count" INTEGER NOT NULL,
    "vote_count" INTEGER NOT NULL,
    "vote_record_count" INTEGER NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliament_activity_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliament_activity_snapshots_source_document_id_fkey"
        FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliament_activity_snapshots_counts_nonnegative"
        CHECK (
            "session_count" >= 0 AND "initiative_count" >= 0
            AND "vote_count" >= 0 AND "vote_record_count" >= 0
        ),
    CONSTRAINT "parliament_activity_snapshots_normalised_sha256_format"
        CHECK ("normalised_sha256" ~ '^[0-9a-f]{64}$')
);

ALTER TABLE "parliamentary_sessions" ADD COLUMN "snapshot_id" TEXT;
ALTER TABLE "parliamentary_initiatives" ADD COLUMN "snapshot_id" TEXT;
ALTER TABLE "vote_events" ADD COLUMN "snapshot_id" TEXT;

ALTER TABLE "parliamentary_sessions"
ADD CONSTRAINT "parliamentary_sessions_snapshot_id_fkey"
FOREIGN KEY ("snapshot_id") REFERENCES "parliament_activity_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "parliamentary_initiatives"
ADD CONSTRAINT "parliamentary_initiatives_snapshot_id_fkey"
FOREIGN KEY ("snapshot_id") REFERENCES "parliament_activity_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "vote_events"
ADD CONSTRAINT "vote_events_snapshot_id_fkey"
FOREIGN KEY ("snapshot_id") REFERENCES "parliament_activity_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS
    "parliament_activity_snapshots_source_document_id_legislature_parser_version_key"
ON "parliament_activity_snapshots"("source_document_id", "legislature", "parser_version");

CREATE INDEX IF NOT EXISTS "parliament_activity_snapshots_legislature_collected_at_idx"
ON "parliament_activity_snapshots"("legislature", "collected_at");

CREATE UNIQUE INDEX IF NOT EXISTS "parliamentary_sessions_source_id_snapshot_id_key"
ON "parliamentary_sessions"("source_id", "snapshot_id");

CREATE UNIQUE INDEX IF NOT EXISTS
    "parliamentary_initiatives_source_id_snapshot_id_key"
ON "parliamentary_initiatives"("source_id", "snapshot_id");

CREATE UNIQUE INDEX IF NOT EXISTS "vote_events_source_id_snapshot_id_key"
ON "vote_events"("source_id", "snapshot_id");

CREATE INDEX IF NOT EXISTS "parliamentary_sessions_snapshot_id_idx"
ON "parliamentary_sessions"("snapshot_id");

CREATE INDEX IF NOT EXISTS "parliamentary_initiatives_snapshot_id_idx"
ON "parliamentary_initiatives"("snapshot_id");

CREATE INDEX IF NOT EXISTS "vote_events_snapshot_id_idx"
ON "vote_events"("snapshot_id");

CREATE INDEX IF NOT EXISTS "vote_events_legislature_voted_at_idx"
ON "vote_events"("legislature", "voted_at");

CREATE OR REPLACE FUNCTION reject_parliament_snapshot_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% é uma fotografia parlamentar append-only; UPDATE e DELETE são proibidos',
        TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS parliamentary_sessions_append_only ON "parliamentary_sessions";
CREATE TRIGGER parliamentary_sessions_append_only
BEFORE UPDATE OR DELETE ON "parliamentary_sessions"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

DROP TRIGGER IF EXISTS parliamentary_membership_snapshots_append_only
ON "parliamentary_membership_snapshots";
CREATE TRIGGER parliamentary_membership_snapshots_append_only
BEFORE UPDATE OR DELETE ON "parliamentary_membership_snapshots"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

DROP TRIGGER IF EXISTS parliament_activity_snapshots_append_only
ON "parliament_activity_snapshots";
CREATE TRIGGER parliament_activity_snapshots_append_only
BEFORE UPDATE OR DELETE ON "parliament_activity_snapshots"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

DROP TRIGGER IF EXISTS parliamentary_initiatives_append_only ON "parliamentary_initiatives";
CREATE TRIGGER parliamentary_initiatives_append_only
BEFORE UPDATE OR DELETE ON "parliamentary_initiatives"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

DROP TRIGGER IF EXISTS vote_events_append_only ON "vote_events";
CREATE TRIGGER vote_events_append_only
BEFORE UPDATE OR DELETE ON "vote_events"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

DROP TRIGGER IF EXISTS vote_records_append_only ON "vote_records";
CREATE TRIGGER vote_records_append_only
BEFORE UPDATE OR DELETE ON "vote_records"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();
