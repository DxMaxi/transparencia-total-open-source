-- V5.34: prova relacional exata e histórico append-only dos mandatos.
--
-- As colunas são nullable apenas para manter compatibilidade com linhas históricas.
-- A porta V5.34 insere sempre o conjunto completo; a constraint impede conjuntos
-- parciais. Uma correção futura acrescenta outro mandato a partir de uma nova
-- observação oficial, e uma retirada acrescenta uma revisão negativa.

ALTER TABLE "mandates"
    ADD COLUMN "source_observation_id" TEXT,
    ADD COLUMN "source_period_ordinal" INTEGER,
    ADD COLUMN "source_period_sha256" CHAR(64);

ALTER TABLE "mandates"
    ADD CONSTRAINT "mandates_source_period_bundle_check"
    CHECK (
        (
            "source_observation_id" IS NULL
            AND "source_period_ordinal" IS NULL
            AND "source_period_sha256" IS NULL
        )
        OR
        (
            "source_observation_id" IS NOT NULL
            AND "source_period_ordinal" IS NOT NULL
            AND "source_period_ordinal" >= 1
            AND "source_period_sha256" IS NOT NULL
            AND "source_period_sha256" ~ '^[0-9a-f]{64}$'
        )
    ),
    ADD CONSTRAINT "mandates_period_order_check"
    CHECK ("ended_at" IS NULL OR "ended_at" >= "started_at") NOT VALID;

ALTER TABLE "mandates"
    ADD CONSTRAINT "mandates_source_observation_id_fkey"
    FOREIGN KEY ("source_observation_id")
    REFERENCES "parliament_deputy_observations"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE UNIQUE INDEX "mandates_source_observation_id_source_period_ordinal_key"
ON "mandates"("source_observation_id", "source_period_ordinal");

CREATE FUNCTION "reject_mandate_history_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% é histórico público append-only; UPDATE e DELETE são proibidos',
        TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "mandates_append_only"
BEFORE UPDATE OR DELETE ON "mandates"
FOR EACH ROW EXECUTE FUNCTION "reject_mandate_history_mutation"();

CREATE TRIGGER "data_publication_reviews_append_only"
BEFORE UPDATE OR DELETE ON "data_publication_reviews"
FOR EACH ROW EXECUTE FUNCTION "reject_mandate_history_mutation"();

REVOKE ALL PRIVILEGES ON FUNCTION "reject_mandate_history_mutation"() FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION "reject_mandate_history_mutation"() FROM %I',
                api_role
            );
        END IF;
    END LOOP;
END
$$;
