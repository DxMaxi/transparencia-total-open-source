-- V5.37: publicação append-only de períodos de cargo parlamentares exatos.
--
-- Um cargo observado é uma entidade própria. Nunca é convertido num mandato,
-- filiação ou conclusão sobre competências atuais. A aplicação só insere depois
-- de revisão humana específica, prova oficial reconstruída e ação ADMIN com MFA.

CREATE TABLE "parliamentary_office_periods" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "source_observation_id" TEXT NOT NULL,
    "source_period_ordinal" INTEGER NOT NULL,
    "official_office_id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "legislature" TEXT NOT NULL,
    "constituency_source_id" TEXT NOT NULL,
    "constituency" TEXT NOT NULL,
    "started_at" TIMESTAMP(3) NOT NULL,
    "ended_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "source_period_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "parliamentary_office_periods_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "parliamentary_office_periods_person_id_fkey"
        FOREIGN KEY ("person_id") REFERENCES "people"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliamentary_office_periods_source_observation_id_fkey"
        FOREIGN KEY ("source_observation_id")
        REFERENCES "parliament_deputy_observations"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliamentary_office_periods_source_document_id_fkey"
        FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "parliamentary_office_periods_period_ordinal_positive"
        CHECK ("source_period_ordinal" >= 1),
    CONSTRAINT "parliamentary_office_periods_official_id_nonempty"
        CHECK (length(btrim("official_office_id")) > 0),
    CONSTRAINT "parliamentary_office_periods_title_nonempty"
        CHECK (length(btrim("title")) > 0),
    CONSTRAINT "parliamentary_office_periods_legislature_nonempty"
        CHECK (length(btrim("legislature")) > 0),
    CONSTRAINT "parliamentary_office_periods_constituency_id_nonempty"
        CHECK (length(btrim("constituency_source_id")) > 0),
    CONSTRAINT "parliamentary_office_periods_constituency_nonempty"
        CHECK (length(btrim("constituency")) > 0),
    CONSTRAINT "parliamentary_office_periods_period_order"
        CHECK ("ended_at" IS NULL OR "ended_at" >= "started_at"),
    CONSTRAINT "parliamentary_office_periods_source_period_sha256_format"
        CHECK ("source_period_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX
    "parliamentary_office_periods_source_observation_id_source_period_ordinal_key"
ON "parliamentary_office_periods"("source_observation_id", "source_period_ordinal");

CREATE INDEX "parliamentary_office_periods_person_id_started_at_idx"
ON "parliamentary_office_periods"("person_id", "started_at");

CREATE INDEX "parliamentary_office_periods_official_office_id_idx"
ON "parliamentary_office_periods"("official_office_id");

CREATE INDEX "parliamentary_office_periods_legislature_started_at_idx"
ON "parliamentary_office_periods"("legislature", "started_at");

CREATE FUNCTION "reject_parliamentary_office_history_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% é histórico público append-only; UPDATE e DELETE são proibidos',
        TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "parliamentary_office_periods_append_only"
BEFORE UPDATE OR DELETE ON "parliamentary_office_periods"
FOR EACH ROW EXECUTE FUNCTION "reject_parliamentary_office_history_mutation"();

ALTER TABLE "parliamentary_office_periods" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "parliamentary_office_periods" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_parliamentary_office_history_mutation"()
FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'parliamentary_office_periods', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_parliamentary_office_history_mutation', api_role
            );
        END IF;
    END LOOP;
END
$$;
