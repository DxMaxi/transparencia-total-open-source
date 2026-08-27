-- V5.40: projeção pública append-only de uma reunião de presenças integral.
--
-- As ligações novas são nullable apenas para manter as sessões históricas já
-- existentes. A porta V5.40 insere sempre o conjunto completo e liga cada linha
-- à observação oficial exata. Uma retirada futura acrescenta revisão negativa;
-- nunca apaga a sessão, a presença, a fonte ou a decisão original.

ALTER TABLE "parliamentary_sessions"
    ADD COLUMN "attendance_snapshot_id" TEXT;

ALTER TABLE "attendance_records"
    ADD COLUMN "source_observation_id" TEXT,
    ADD COLUMN "source_record_sha256" CHAR(64);

ALTER TABLE "parliamentary_sessions"
    ADD CONSTRAINT "parliamentary_sessions_snapshot_scope_check"
    CHECK ("snapshot_id" IS NULL OR "attendance_snapshot_id" IS NULL),
    ADD CONSTRAINT "parliamentary_sessions_attendance_snapshot_id_fkey"
    FOREIGN KEY ("attendance_snapshot_id")
    REFERENCES "parliament_attendance_snapshots"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "attendance_records"
    ADD CONSTRAINT "attendance_records_source_bundle_check"
    CHECK (
        (
            "source_observation_id" IS NULL
            AND "source_record_sha256" IS NULL
        )
        OR
        (
            "source_observation_id" IS NOT NULL
            AND "source_record_sha256" IS NOT NULL
            AND "source_record_sha256" ~ '^[0-9a-f]{64}$'
        )
    ),
    ADD CONSTRAINT "attendance_records_source_observation_id_fkey"
    FOREIGN KEY ("source_observation_id")
    REFERENCES "parliament_attendance_observations"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE UNIQUE INDEX "parliamentary_sessions_attendance_snapshot_id_key"
ON "parliamentary_sessions"("attendance_snapshot_id");

CREATE INDEX "parliamentary_sessions_attendance_snapshot_id_idx"
ON "parliamentary_sessions"("attendance_snapshot_id");

CREATE UNIQUE INDEX "attendance_records_source_observation_id_key"
ON "attendance_records"("source_observation_id");

ALTER TABLE "attendance_records"
    DROP CONSTRAINT "attendance_records_mandate_id_fkey",
    DROP CONSTRAINT "attendance_records_session_id_fkey";

ALTER TABLE "attendance_records"
    ADD CONSTRAINT "attendance_records_mandate_id_fkey"
    FOREIGN KEY ("mandate_id") REFERENCES "mandates"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
    ADD CONSTRAINT "attendance_records_session_id_fkey"
    FOREIGN KEY ("session_id") REFERENCES "parliamentary_sessions"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE TRIGGER "attendance_records_append_only"
BEFORE UPDATE OR DELETE ON "attendance_records"
FOR EACH ROW EXECUTE FUNCTION "reject_parliament_snapshot_mutation"();
