-- V5.46: observações privadas do registo público de interesses da EPT.
--
-- Esta tabela não guarda conteúdo patrimonial ou financeiro, identificadores
-- protegidos, moradas, contactos ou bytes da declaração. Os bytes exatos ficam
-- exclusivamente no arquivo privado já atestado. A observação também não cria
-- qualquer ligação a `people`: essa decisão pertence a uma revisão humana
-- posterior, apoiada por identificadores oficiais inequívocos.

CREATE TABLE "ept_public_interest_observations" (
    "id" TEXT NOT NULL,
    "official_declaration_id" TEXT NOT NULL,
    "official_subject_digest" CHAR(64) NOT NULL,
    "public_subject_name" TEXT NOT NULL,
    "declaration_type" TEXT NOT NULL DEFAULT 'INTEREST_REGISTER',
    "declared_at" TIMESTAMP(3),
    "period_label" TEXT,
    "public_access_scope" TEXT NOT NULL DEFAULT 'PUBLIC_INTEREST_REGISTER',
    "legal_review_status" TEXT NOT NULL DEFAULT 'REQUIRES_INDEPENDENT_LEGAL_REVIEW',
    "identity_link_status" TEXT NOT NULL DEFAULT 'UNLINKED_PRIVATE',
    "source_document_id" TEXT NOT NULL,
    "source_record_sha256" CHAR(64) NOT NULL,
    "observed_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ept_public_interest_observations_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ept_public_interest_observations_declaration_id_check"
        CHECK (length(trim("official_declaration_id")) BETWEEN 1 AND 200),
    CONSTRAINT "ept_public_interest_observations_subject_digest_check"
        CHECK ("official_subject_digest" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_public_interest_observations_subject_name_check"
        CHECK (length(trim("public_subject_name")) BETWEEN 1 AND 300),
    CONSTRAINT "ept_public_interest_observations_type_check"
        CHECK ("declaration_type" = 'INTEREST_REGISTER'),
    CONSTRAINT "ept_public_interest_observations_period_check"
        CHECK ("period_label" IS NULL OR length(trim("period_label")) BETWEEN 1 AND 200),
    CONSTRAINT "ept_public_interest_observations_scope_check"
        CHECK ("public_access_scope" = 'PUBLIC_INTEREST_REGISTER'),
    CONSTRAINT "ept_public_interest_observations_legal_status_check"
        CHECK ("legal_review_status" = 'REQUIRES_INDEPENDENT_LEGAL_REVIEW'),
    CONSTRAINT "ept_public_interest_observations_identity_status_check"
        CHECK ("identity_link_status" = 'UNLINKED_PRIVATE'),
    CONSTRAINT "ept_public_interest_observations_record_sha_check"
        CHECK ("source_record_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX "ept_public_interest_observations_source_declaration_key"
ON "ept_public_interest_observations"("source_document_id", "official_declaration_id");

CREATE INDEX "ept_public_interest_observations_declaration_observed_idx"
ON "ept_public_interest_observations"("official_declaration_id", "observed_at");

CREATE INDEX "ept_public_interest_observations_subject_observed_idx"
ON "ept_public_interest_observations"("official_subject_digest", "observed_at");

CREATE INDEX "ept_public_interest_observations_review_status_idx"
ON "ept_public_interest_observations"
   ("legal_review_status", "identity_link_status", "observed_at");

CREATE INDEX "ept_public_interest_observations_record_sha_idx"
ON "ept_public_interest_observations"("source_record_sha256");

ALTER TABLE "ept_public_interest_observations"
ADD CONSTRAINT "ept_public_interest_observations_source_document_id_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE FUNCTION "validate_ept_public_interest_observation_insert"()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM "source_documents" AS source
        JOIN "source_archive_attestations" AS archive
          ON archive."source_document_id" = source."id"
         AND archive."content_sha256" = source."content_sha256"
         AND archive."retrieval_url" = source."url"
         AND archive."retrieved_at" = source."retrieved_at"
        WHERE source."id" = NEW."source_document_id"
          AND source."publisher" = 'TRANSPARENCY_ENTITY'
          AND source."kind" = 'DECLARATION'
          AND source."official_identifier" = NEW."official_declaration_id"
          AND source."url" ~ '^https://((www\.)?tribunalconstitucional\.pt|entidadetransparencia\.pt)/[^?#]'
          AND source."url" NOT IN (
              'https://www.tribunalconstitucional.pt/tc/ept/',
              'https://entidadetransparencia.pt/'
          )
          AND source."url" !~ '^https://(www\.)?tribunalconstitucional\.pt/tc/ept/?([?#].*)?$'
    ) THEN
        RAISE EXCEPTION
            'a observação EPT exige prova individual oficial, identificador exato e arquivo atestado';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "ept_public_interest_observations_validate_insert"
BEFORE INSERT ON "ept_public_interest_observations"
FOR EACH ROW EXECUTE FUNCTION "validate_ept_public_interest_observation_insert"();

CREATE FUNCTION "reject_ept_public_interest_observation_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'ept_public_interest_observations preserva staging histórico; UPDATE e DELETE são proibidos';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "ept_public_interest_observations_append_only"
BEFORE UPDATE OR DELETE ON "ept_public_interest_observations"
FOR EACH ROW EXECUTE FUNCTION "reject_ept_public_interest_observation_mutation"();

ALTER TABLE "ept_public_interest_observations" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "ept_public_interest_observations" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_ept_public_interest_observation_insert"()
FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_ept_public_interest_observation_mutation"()
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
                'ept_public_interest_observations', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_ept_public_interest_observation_insert', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_ept_public_interest_observation_mutation', api_role
            );
        END IF;
    END LOOP;
END
$$;
