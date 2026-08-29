-- V5.47: avaliação jurídica independente, ligação exata e porta EPT específica.
--
-- As duas tabelas são privadas e append-only. O parecer não é tratado como
-- fonte factual: apenas se conservam o SHA-256, a referência pseudonimizada do
-- avaliador e a localização cifrada do documento. A identidade original do
-- titular nunca é persistida; a ligação usa exclusivamente o HMAC já calculado.

CREATE TABLE "ept_independent_legal_assessments" (
    "id" TEXT NOT NULL,
    "observation_id" TEXT NOT NULL,
    "case_id" TEXT NOT NULL,
    "assessment_scope" TEXT NOT NULL DEFAULT 'PUBLIC_INTEREST_METADATA_ONLY',
    "outcome" TEXT NOT NULL,
    "assessment_document_sha256" CHAR(64) NOT NULL,
    "assessment_document_storage_backend" TEXT NOT NULL,
    "assessment_document_storage_key" TEXT NOT NULL,
    "assessment_document_byte_size" INTEGER NOT NULL,
    "assessment_document_mime_type" TEXT NOT NULL,
    "assessor_reference_sha256" CHAR(64) NOT NULL,
    "qualification_evidence_sha256" CHAR(64) NOT NULL,
    "conflict_check_sha256" CHAR(64) NOT NULL,
    "assessed_at" TIMESTAMP(3) NOT NULL,
    "valid_until" TIMESTAMP(3),
    "recorded_by_id" TEXT NOT NULL,
    "recorded_by_alias" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ept_independent_legal_assessments_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ept_legal_assessment_scope_check"
        CHECK ("assessment_scope" = 'PUBLIC_INTEREST_METADATA_ONLY'),
    CONSTRAINT "ept_legal_assessment_outcome_check"
        CHECK ("outcome" IN (
            'PERMITS_PUBLIC_INTEREST_METADATA_ONLY',
            'DOES_NOT_PERMIT_PUBLICATION',
            'REQUIRES_CHANGES'
        )),
    CONSTRAINT "ept_legal_assessment_document_sha_check"
        CHECK ("assessment_document_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_legal_assessment_storage_backend_check"
        CHECK ("assessment_document_storage_backend" IN (
            'BACKBLAZE_B2_ENCRYPTED', 'OTHER_ENCRYPTED_PRIVATE'
        )),
    CONSTRAINT "ept_legal_assessment_storage_key_check"
        CHECK (length(trim("assessment_document_storage_key")) BETWEEN 1 AND 500),
    CONSTRAINT "ept_legal_assessment_byte_size_check"
        CHECK ("assessment_document_byte_size" BETWEEN 1 AND 50000000),
    CONSTRAINT "ept_legal_assessment_mime_type_check"
        CHECK ("assessment_document_mime_type" IN ('application/pdf', 'application/octet-stream')),
    CONSTRAINT "ept_legal_assessment_assessor_sha_check"
        CHECK ("assessor_reference_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_legal_assessment_qualification_sha_check"
        CHECK ("qualification_evidence_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_legal_assessment_conflict_sha_check"
        CHECK ("conflict_check_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_legal_assessment_validity_check"
        CHECK ("valid_until" IS NULL OR "valid_until" > "assessed_at"),
    CONSTRAINT "ept_legal_assessment_alias_check"
        CHECK (length(trim("recorded_by_alias")) BETWEEN 3 AND 80)
);

CREATE UNIQUE INDEX "ept_legal_assessment_case_document_key"
ON "ept_independent_legal_assessments"("case_id", "assessment_document_sha256");
CREATE INDEX "ept_legal_assessment_observation_assessed_idx"
ON "ept_independent_legal_assessments"("observation_id", "assessed_at");
CREATE INDEX "ept_legal_assessment_case_assessed_idx"
ON "ept_independent_legal_assessments"("case_id", "assessed_at");
CREATE INDEX "ept_legal_assessment_outcome_valid_idx"
ON "ept_independent_legal_assessments"("outcome", "valid_until");
CREATE INDEX "ept_legal_assessment_recorded_by_idx"
ON "ept_independent_legal_assessments"("recorded_by_id");

CREATE TABLE "ept_exact_identity_links" (
    "id" TEXT NOT NULL,
    "observation_id" TEXT NOT NULL,
    "case_id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "evidence_document_id" TEXT NOT NULL,
    "official_subject_digest" CHAR(64) NOT NULL,
    "person_source_id" TEXT NOT NULL,
    "evidence_sha256" CHAR(64) NOT NULL,
    "link_proof_sha256" CHAR(64) NOT NULL,
    "recorded_by_id" TEXT NOT NULL,
    "recorded_by_alias" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ept_exact_identity_links_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "ept_identity_link_subject_digest_check"
        CHECK ("official_subject_digest" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_identity_link_person_source_check"
        CHECK (length(trim("person_source_id")) BETWEEN 1 AND 200),
    CONSTRAINT "ept_identity_link_evidence_sha_check"
        CHECK ("evidence_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_identity_link_proof_sha_check"
        CHECK ("link_proof_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "ept_identity_link_alias_check"
        CHECK (length(trim("recorded_by_alias")) BETWEEN 3 AND 80)
);

CREATE UNIQUE INDEX "ept_exact_identity_links_case_key"
ON "ept_exact_identity_links"("case_id");
CREATE UNIQUE INDEX "ept_exact_identity_links_observation_person_evidence_key"
ON "ept_exact_identity_links"("observation_id", "person_id", "evidence_document_id");
CREATE UNIQUE INDEX "ept_exact_identity_links_proof_key"
ON "ept_exact_identity_links"("link_proof_sha256");
CREATE INDEX "ept_exact_identity_links_observation_created_idx"
ON "ept_exact_identity_links"("observation_id", "created_at");
CREATE INDEX "ept_exact_identity_links_person_created_idx"
ON "ept_exact_identity_links"("person_id", "created_at");
CREATE INDEX "ept_exact_identity_links_evidence_idx"
ON "ept_exact_identity_links"("evidence_document_id");
CREATE INDEX "ept_exact_identity_links_recorded_by_idx"
ON "ept_exact_identity_links"("recorded_by_id");

ALTER TABLE "ept_independent_legal_assessments"
ADD CONSTRAINT "ept_legal_assessment_observation_fkey"
FOREIGN KEY ("observation_id") REFERENCES "ept_public_interest_observations"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "ept_independent_legal_assessments"
ADD CONSTRAINT "ept_legal_assessment_case_fkey"
FOREIGN KEY ("case_id") REFERENCES "editorial_cases"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "ept_independent_legal_assessments"
ADD CONSTRAINT "ept_legal_assessment_recorded_by_fkey"
FOREIGN KEY ("recorded_by_id") REFERENCES "staff_profiles"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "ept_exact_identity_links"
ADD CONSTRAINT "ept_identity_link_observation_fkey"
FOREIGN KEY ("observation_id") REFERENCES "ept_public_interest_observations"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "ept_exact_identity_links"
ADD CONSTRAINT "ept_identity_link_case_fkey"
FOREIGN KEY ("case_id") REFERENCES "editorial_cases"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "ept_exact_identity_links"
ADD CONSTRAINT "ept_identity_link_person_fkey"
FOREIGN KEY ("person_id") REFERENCES "people"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "ept_exact_identity_links"
ADD CONSTRAINT "ept_identity_link_evidence_fkey"
FOREIGN KEY ("evidence_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "ept_exact_identity_links"
ADD CONSTRAINT "ept_identity_link_recorded_by_fkey"
FOREIGN KEY ("recorded_by_id") REFERENCES "staff_profiles"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE FUNCTION "validate_ept_legal_assessment_insert"()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW."assessed_at" >
       (clock_timestamp() AT TIME ZONE 'UTC') + INTERVAL '5 minutes' THEN
        RAISE EXCEPTION 'a avaliação EPT não pode ter uma data futura';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM "editorial_cases" AS editorial_case
        JOIN "staff_profiles" AS recorder ON recorder."id" = NEW."recorded_by_id"
        WHERE editorial_case."id" = NEW."case_id"
          AND editorial_case."subject_type" = 'EPT_PUBLIC_INTEREST_OBSERVATION'
          AND editorial_case."subject_id" = NEW."observation_id"
          AND editorial_case."current_state" = 'APPROVED'
          AND recorder."active" = TRUE
          AND recorder."role" = 'ADMIN'
          AND recorder."public_alias" = NEW."recorded_by_alias"
    ) THEN
        RAISE EXCEPTION
            'a avaliação EPT exige processo aprovado e registo por ADMIN ativo';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION "validate_ept_identity_link_insert"()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM "editorial_cases" AS editorial_case
        JOIN "ept_public_interest_observations" AS observation
          ON observation."id" = NEW."observation_id"
        JOIN "people" AS person ON person."id" = NEW."person_id"
        JOIN "source_documents" AS evidence
          ON evidence."id" = NEW."evidence_document_id"
        JOIN "staff_profiles" AS recorder ON recorder."id" = NEW."recorded_by_id"
        WHERE editorial_case."id" = NEW."case_id"
          AND editorial_case."subject_type" = 'EPT_PUBLIC_INTEREST_OBSERVATION'
          AND editorial_case."subject_id" = observation."id"
          AND editorial_case."current_state" = 'APPROVED'
          AND observation."official_subject_digest" = NEW."official_subject_digest"
          AND person."source_id" = NEW."person_source_id"
          AND person."active" = TRUE
          AND evidence."id" <> observation."source_document_id"
          AND evidence."official_identifier" = person."source_id"
          AND evidence."content_sha256" = NEW."evidence_sha256"
          AND evidence."url" LIKE 'https://%'
          AND evidence."publisher" <> 'MEDIA'
          AND evidence."kind" <> 'NEWS_ARTICLE'
          AND EXISTS (
              SELECT 1 FROM "source_archive_attestations" AS archive
              WHERE archive."source_document_id" = evidence."id"
                AND archive."content_sha256" = evidence."content_sha256"
                AND archive."retrieval_url" = evidence."url"
                AND archive."retrieved_at" = evidence."retrieved_at"
          )
          AND (
              SELECT review."publishable"
              FROM "data_publication_reviews" AS review
              WHERE review."entity_type" = 'PERSON'
                AND review."entity_id" = person."id"
                AND review."source_document_id" = evidence."id"
              ORDER BY review."reviewed_at" DESC, review."id" DESC
              LIMIT 1
          ) = TRUE
          AND recorder."active" = TRUE
          AND recorder."role" = 'ADMIN'
          AND recorder."public_alias" = NEW."recorded_by_alias"
    ) THEN
        RAISE EXCEPTION
            'a ligação EPT exige HMAC coincidente, pessoa exata e segunda fonte oficial atestada';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION "reject_ept_legal_gate_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'o gate jurídico EPT é append-only; UPDATE e DELETE são proibidos';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "ept_legal_assessments_validate_insert"
BEFORE INSERT ON "ept_independent_legal_assessments"
FOR EACH ROW EXECUTE FUNCTION "validate_ept_legal_assessment_insert"();
CREATE TRIGGER "ept_identity_links_validate_insert"
BEFORE INSERT ON "ept_exact_identity_links"
FOR EACH ROW EXECUTE FUNCTION "validate_ept_identity_link_insert"();
CREATE TRIGGER "ept_legal_assessments_append_only"
BEFORE UPDATE OR DELETE ON "ept_independent_legal_assessments"
FOR EACH ROW EXECUTE FUNCTION "reject_ept_legal_gate_mutation"();
CREATE TRIGGER "ept_identity_links_append_only"
BEFORE UPDATE OR DELETE ON "ept_exact_identity_links"
FOR EACH ROW EXECUTE FUNCTION "reject_ept_legal_gate_mutation"();

ALTER TABLE "ept_independent_legal_assessments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "ept_exact_identity_links" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "ept_independent_legal_assessments" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "ept_exact_identity_links" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_ept_legal_assessment_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_ept_identity_link_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_ept_legal_gate_mutation"() FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'ept_independent_legal_assessments', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'ept_exact_identity_links', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_ept_legal_assessment_insert', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_ept_identity_link_insert', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_ept_legal_gate_mutation', api_role
            );
        END IF;
    END LOOP;
END
$$;
