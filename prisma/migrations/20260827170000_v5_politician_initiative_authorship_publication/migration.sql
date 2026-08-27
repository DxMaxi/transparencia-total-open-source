-- V5.43: projeção pública append-only de uma autoria parlamentar exata.
--
-- A linha não é uma inferência por nome ou partido. Liga exclusivamente uma
-- observação AUTHOR por idCadastro a uma iniciativa pelo IniId oficial, depois
-- de ambas as provas terem passado portas públicas humanas independentes.

CREATE TABLE "politician_initiative_authorships" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "initiative_id" TEXT NOT NULL,
    "source_observation_id" TEXT NOT NULL,
    "relation" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "source_record_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "politician_initiative_authorships_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "politician_initiative_authorships_person_id_fkey"
        FOREIGN KEY ("person_id") REFERENCES "people"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "politician_initiative_authorships_initiative_id_fkey"
        FOREIGN KEY ("initiative_id") REFERENCES "parliamentary_initiatives"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "politician_initiative_authorships_source_observation_id_fkey"
        FOREIGN KEY ("source_observation_id")
        REFERENCES "parliament_initiative_author_observations"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "politician_initiative_authorships_source_document_id_fkey"
        FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "politician_initiative_authorships_relation_allowed"
        CHECK ("relation" = 'AUTHOR'),
    CONSTRAINT "politician_initiative_authorships_source_sha256_format"
        CHECK ("source_record_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX
    "politician_initiative_authorships_source_observation_id_key"
ON "politician_initiative_authorships"("source_observation_id");

CREATE UNIQUE INDEX
    "politician_initiative_authorships_person_initiative_relation_key"
ON "politician_initiative_authorships"("person_id", "initiative_id", "relation");

CREATE INDEX "politician_initiative_authorships_person_created_at_idx"
ON "politician_initiative_authorships"("person_id", "created_at");

CREATE INDEX "politician_initiative_authorships_initiative_id_idx"
ON "politician_initiative_authorships"("initiative_id");

CREATE FUNCTION "reject_politician_initiative_authorship_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% é histórico público append-only; UPDATE e DELETE são proibidos',
        TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "politician_initiative_authorships_append_only"
BEFORE UPDATE OR DELETE ON "politician_initiative_authorships"
FOR EACH ROW EXECUTE FUNCTION "reject_politician_initiative_authorship_mutation"();

ALTER TABLE "politician_initiative_authorships" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "politician_initiative_authorships" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_politician_initiative_authorship_mutation"()
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
                'politician_initiative_authorships', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_politician_initiative_authorship_mutation', api_role
            );
        END IF;
    END LOOP;
END
$$;
