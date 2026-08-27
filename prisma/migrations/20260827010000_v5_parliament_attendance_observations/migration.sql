-- V5.39: fotografias privadas e append-only das presenças oficiais em plenário.
-- Cada fotografia representa uma reunião completa e conserva os BID individuais;
-- não cria pessoas, mandatos, sessões públicas, revisões ou publicações.

CREATE TABLE "parliament_attendance_snapshots" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "legislature" TEXT NOT NULL,
    "official_meeting_id" TEXT NOT NULL,
    "meeting_date" DATE NOT NULL,
    "meeting_type" TEXT NOT NULL,
    "session_number" TEXT,
    "parser_version" TEXT NOT NULL,
    "normalised_sha256" CHAR(64) NOT NULL,
    "collected_at" TIMESTAMP(3) NOT NULL,
    "record_count" INTEGER NOT NULL,
    "present_count" INTEGER NOT NULL,
    "justified_absence_count" INTEGER NOT NULL,
    "unjustified_absence_count" INTEGER NOT NULL,
    "unknown_count" INTEGER NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliament_attendance_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliament_attendance_snapshots_source_document_id_fkey"
        FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliament_attendance_snapshots_legislature_nonempty"
        CHECK (length(btrim("legislature")) > 0),
    CONSTRAINT "parliament_attendance_snapshots_meeting_id_nonempty"
        CHECK (length(btrim("official_meeting_id")) > 0),
    CONSTRAINT "parliament_attendance_snapshots_meeting_type_nonempty"
        CHECK (length(btrim("meeting_type")) > 0),
    CONSTRAINT "parliament_attendance_snapshots_counts_nonnegative"
        CHECK (
            "record_count" >= 0
            AND "present_count" >= 0
            AND "justified_absence_count" >= 0
            AND "unjustified_absence_count" >= 0
            AND "unknown_count" >= 0
        ),
    CONSTRAINT "parliament_attendance_snapshots_counts_match"
        CHECK (
            "record_count" = "present_count"
                + "justified_absence_count"
                + "unjustified_absence_count"
                + "unknown_count"
        ),
    CONSTRAINT "parliament_attendance_snapshots_normalised_sha256_format"
        CHECK ("normalised_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE TABLE "parliament_attendance_observations" (
    "id" TEXT NOT NULL,
    "snapshot_id" TEXT NOT NULL,
    "official_deputy_id" TEXT NOT NULL,
    "parliamentary_name" TEXT NOT NULL,
    "parliamentary_group_label" TEXT,
    "status" TEXT NOT NULL,
    "source_status_label" TEXT NOT NULL,
    "source_status_code" TEXT,
    "absence_reason" TEXT,
    "source_record_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliament_attendance_observations_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliament_attendance_observations_snapshot_id_fkey"
        FOREIGN KEY ("snapshot_id") REFERENCES "parliament_attendance_snapshots"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliament_attendance_observations_deputy_id_nonempty"
        CHECK (length(btrim("official_deputy_id")) > 0),
    CONSTRAINT "parliament_attendance_observations_name_nonempty"
        CHECK (length(btrim("parliamentary_name")) > 0),
    CONSTRAINT "parliament_attendance_observations_status_allowed"
        CHECK (
            "status" IN (
                'PRESENT',
                'JUSTIFIED_ABSENCE',
                'UNJUSTIFIED_ABSENCE',
                'UNKNOWN'
            )
        ),
    CONSTRAINT "parliament_attendance_observations_source_label_nonempty"
        CHECK (length(btrim("source_status_label")) > 0),
    CONSTRAINT "parliament_attendance_observations_source_record_sha256_format"
        CHECK ("source_record_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX
    "parliament_attendance_snapshots_source_document_id_legislature_parser_version_key"
ON "parliament_attendance_snapshots"(
    "source_document_id", "legislature", "parser_version"
);

CREATE INDEX "parliament_attendance_snapshots_legislature_meeting_date_idx"
ON "parliament_attendance_snapshots"("legislature", "meeting_date");

CREATE INDEX "parliament_attendance_snapshots_official_meeting_id_idx"
ON "parliament_attendance_snapshots"("official_meeting_id");

CREATE UNIQUE INDEX
    "parliament_attendance_observations_snapshot_id_official_deputy_id_key"
ON "parliament_attendance_observations"("snapshot_id", "official_deputy_id");

CREATE INDEX "parliament_attendance_observations_official_deputy_id_idx"
ON "parliament_attendance_observations"("official_deputy_id");

CREATE INDEX "parliament_attendance_observations_snapshot_id_status_idx"
ON "parliament_attendance_observations"("snapshot_id", "status");

CREATE TRIGGER "parliament_attendance_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "parliament_attendance_snapshots"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

CREATE TRIGGER "parliament_attendance_observations_append_only"
BEFORE UPDATE OR DELETE ON "parliament_attendance_observations"
FOR EACH ROW EXECUTE FUNCTION reject_parliament_snapshot_mutation();

ALTER TABLE "parliament_attendance_snapshots" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "parliament_attendance_observations" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "parliament_attendance_snapshots" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "parliament_attendance_observations" FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'parliament_attendance_snapshots', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'parliament_attendance_observations', api_role
            );
        END IF;
    END LOOP;
END
$$;
