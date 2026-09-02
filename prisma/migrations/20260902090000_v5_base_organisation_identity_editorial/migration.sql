-- V5.52: prova privada e editorial da identidade de organizações.
--
-- A observação conserva apenas um HMAC-SHA-256 do NIPC, nunca o valor fiscal
-- em claro. Uma observação e a respetiva aprovação editorial não criam uma
-- organização pública, parte de contrato, correspondência, nó ou relação.

ALTER TYPE "SourcePublisher" ADD VALUE IF NOT EXISTS 'JUSTICE_REGISTRY';
ALTER TYPE "DocumentKind" ADD VALUE IF NOT EXISTS 'ORGANISATION_REGISTRY';
ALTER TYPE "EditorialCaseKind" ADD VALUE IF NOT EXISTS 'ORGANISATION_IDENTITY';

-- A coluna V2 nunca pode ser convertida silenciosamente. Se tiver qualquer
-- valor, a migração para e exige investigação; se estiver vazia é removida.
DO $$
BEGIN
    LOCK TABLE "organisations" IN ACCESS EXCLUSIVE MODE;
    IF EXISTS (SELECT 1 FROM "organisations" WHERE "public_nipc" IS NOT NULL) THEN
        RAISE EXCEPTION
            'organisations.public_nipc contém valores legados; investigar sem copiar, publicar ou apagar automaticamente';
    END IF;
    DROP INDEX IF EXISTS "organisations_public_nipc_idx";
    ALTER TABLE "organisations" DROP COLUMN "public_nipc";
END
$$;

-- Recusa nove algarismos consecutivos/separados após NFKC. Os intervalos
-- explícitos Nd (Unicode 16) evitam depender da locale PostgreSQL. Texto
-- numérico não ASCII é recusado de forma conservadora neste âmbito privado.
CREATE FUNCTION "base_organisation_identity_safe_text"(value TEXT)
RETURNS BOOLEAN AS $$
    SELECT normalize(value, NFKC) !~ '[0-9]([^[:alnum:]]*[0-9]){8}'
       AND value !~ '[٠-٩۰-۹߀-߉०-९০-৯੦-੯૦-૯୦-୯௦-௯౦-౯೦-೯൦-൯෦-෯๐-๙໐-໙༠-༩၀-၉႐-႙០-៩᠐-᠙᥆-᥏᧐-᧙᪀-᪉᪐-᪙᭐-᭙᮰-᮹᱀-᱉᱐-᱙꘠-꘩꣐-꣙꤀-꤉꧐-꧙꧰-꧹꩐-꩙꯰-꯹０-９𐒠-𐒩𐴰-𐴹𐵀-𐵉𑁦-𑁯𑃰-𑃹𑄶-𑄿𑇐-𑇙𑋰-𑋹𑑐-𑑙𑓐-𑓙𑙐-𑙙𑛀-𑛉𑛐-𑛣𑜰-𑜹𑣠-𑣩𑥐-𑥙𑯰-𑯹𑱐-𑱙𑵐-𑵙𑶠-𑶩𑽐-𑽙𖄰-𖄹𖩠-𖩩𖫀-𖫉𖭐-𖭙𖵰-𖵹𜳰-𜳹𝟎-𝟿𞅀-𞅉𞋰-𞋹𞓰-𞓹𞗱-𞗺𞥐-𞥙🯰-🯹]'
       AND regexp_replace(normalize(value, NFKC), '[^[:alnum:]]', '', 'g')
           !~ '[0-9a-fA-F]{64}'
       AND value !~ '[[:cntrl:]]';
$$ LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog;

CREATE TABLE "base_organisation_identity_observations" (
    "id" TEXT NOT NULL,
    "registry_record_id" TEXT NOT NULL,
    "legal_name" TEXT NOT NULL,
    "kind" "InterestEntityKind" NOT NULL,
    "identifier_scheme" TEXT NOT NULL DEFAULT 'PORTUGUESE_FISCAL_IDENTIFIER',
    "protected_identifier_digest" CHAR(64) NOT NULL,
    "identity_scope" TEXT NOT NULL DEFAULT 'ORGANISATION_IDENTITY_ONLY',
    "link_status" TEXT NOT NULL DEFAULT 'UNLINKED_PRIVATE',
    "publication_eligible" BOOLEAN NOT NULL DEFAULT FALSE,
    "source_document_id" TEXT NOT NULL,
    "source_record_sha256" CHAR(64) NOT NULL,
    "observation_sha256" CHAR(64) NOT NULL,
    "observed_at" TIMESTAMP(3) NOT NULL,
    "parser_version" TEXT NOT NULL,
    "policy_version" TEXT NOT NULL,
    "created_by_alias" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_organisation_identity_observations_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_organisation_identity_id_check"
        CHECK ("id" ~ '^base_org_identity_[0-9a-f]{32}$'),
    CONSTRAINT "base_organisation_identity_registry_record_check"
        CHECK (
            length(trim("registry_record_id")) BETWEEN 3 AND 200
            AND "registry_record_id" ~ '^[A-Za-z][A-Za-z0-9._:/-]{2,199}$'
            AND "base_organisation_identity_safe_text"("registry_record_id")
        ),
    CONSTRAINT "base_organisation_identity_legal_name_check"
        CHECK (
            length(trim("legal_name")) BETWEEN 1 AND 300
            AND "base_organisation_identity_safe_text"("legal_name")
        ),
    CONSTRAINT "base_organisation_identity_kind_check"
        CHECK (
            "kind"::text IN (
                'PUBLIC_BODY', 'COMPANY', 'NON_PROFIT', 'EUROPEAN_BODY', 'OTHER'
            )
        ),
    CONSTRAINT "base_organisation_identity_digest_check"
        CHECK ("protected_identifier_digest" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_organisation_identity_scheme_check"
        CHECK ("identifier_scheme" = 'PORTUGUESE_FISCAL_IDENTIFIER'),
    CONSTRAINT "base_organisation_identity_scope_check"
        CHECK ("identity_scope" = 'ORGANISATION_IDENTITY_ONLY'),
    CONSTRAINT "base_organisation_identity_link_status_check"
        CHECK ("link_status" = 'UNLINKED_PRIVATE'),
    CONSTRAINT "base_organisation_identity_publication_check"
        CHECK ("publication_eligible" IS FALSE),
    CONSTRAINT "base_organisation_identity_source_record_sha_check"
        CHECK ("source_record_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_organisation_identity_observation_sha_check"
        CHECK ("observation_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_organisation_identity_parser_version_check"
        CHECK ("parser_version" = 'base-organisation-registry-v1'),
    CONSTRAINT "base_organisation_identity_policy_version_check"
        CHECK ("policy_version" = 'base-organisation-identity-v1'),
    CONSTRAINT "base_organisation_identity_actor_alias_check"
        CHECK (
            length(trim("created_by_alias")) BETWEEN 3 AND 80
            AND "base_organisation_identity_safe_text"("created_by_alias")
            AND "base_organisation_identity_safe_text"("source_document_id")
        )
);

CREATE UNIQUE INDEX "base_organisation_identity_source_record_key"
ON "base_organisation_identity_observations"("source_document_id", "registry_record_id");

CREATE UNIQUE INDEX "base_organisation_identity_source_digest_key"
ON "base_organisation_identity_observations"
   ("source_document_id", "protected_identifier_digest");

CREATE UNIQUE INDEX "base_organisation_identity_observation_sha_key"
ON "base_organisation_identity_observations"("observation_sha256");

CREATE INDEX "base_organisation_identity_record_observed_idx"
ON "base_organisation_identity_observations"("registry_record_id", "observed_at");

CREATE INDEX "base_organisation_identity_kind_observed_idx"
ON "base_organisation_identity_observations"("kind", "observed_at");

CREATE INDEX "base_organisation_identity_digest_observed_idx"
ON "base_organisation_identity_observations"
   ("protected_identifier_digest", "observed_at");

CREATE UNIQUE INDEX "base_organisation_identity_source_record_sha_key"
ON "base_organisation_identity_observations"("source_record_sha256");

CREATE INDEX "base_organisation_identity_source_document_idx"
ON "base_organisation_identity_observations"("source_document_id");

ALTER TABLE "base_organisation_identity_observations"
ADD CONSTRAINT "base_organisation_identity_source_document_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE FUNCTION "validate_base_organisation_identity_observation_insert"()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM 1 FROM "source_documents"
    WHERE "id" = NEW."source_document_id" FOR SHARE;
    IF NOT EXISTS (
        SELECT 1
        FROM "source_documents" AS source
        JOIN "source_archive_attestations" AS archive
          ON archive."source_document_id" = source."id"
         AND archive."content_sha256" = source."content_sha256"
         AND archive."retrieval_url" = source."url"
         AND archive."retrieved_at" = source."retrieved_at"
        WHERE source."id" = NEW."source_document_id"
          AND source."publisher"::text = 'JUSTICE_REGISTRY'
          AND source."kind"::text = 'ORGANISATION_REGISTRY'
          AND source."official_identifier" = NEW."registry_record_id"
          AND source."retrieved_at" = NEW."observed_at"
          AND source."url" ~* '^https://publicacoes\.mj\.pt/DetalhePublicacao\.aspx$'
          AND source."url" LIKE 'https://publicacoes.mj.pt/%'
          AND length(source."url") = octet_length(source."url")
          AND "base_organisation_identity_safe_text"(source."title")
          AND source."mime_type" IN ('text/html', 'application/pdf', 'application/xhtml+xml')
    ) THEN
        RAISE EXCEPTION
            'a identidade organizacional exige registo individual do IRN, identificador não fiscal e arquivo atestado';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "base_organisation_identity_observations_validate_insert"
BEFORE INSERT ON "base_organisation_identity_observations"
FOR EACH ROW EXECUTE FUNCTION "validate_base_organisation_identity_observation_insert"();

-- Uma fonte IRN não pode mudar de significado, mesmo antes da observação.
-- A condição usa a própria linha, sem depender de snapshots de outra tabela.
-- Uma correção acrescenta um novo documento e uma nova observação.
CREATE FUNCTION "protect_base_organisation_identity_source"()
RETURNS TRIGGER AS $$
BEGIN
    IF (
        OLD."publisher"::text = 'JUSTICE_REGISTRY'
        OR NEW."publisher"::text = 'JUSTICE_REGISTRY'
    ) AND (
        NEW."id" IS DISTINCT FROM OLD."id"
        OR NEW."publisher" IS DISTINCT FROM OLD."publisher"
        OR NEW."kind" IS DISTINCT FROM OLD."kind"
        OR NEW."title" IS DISTINCT FROM OLD."title"
        OR NEW."official_identifier" IS DISTINCT FROM OLD."official_identifier"
        OR NEW."url" IS DISTINCT FROM OLD."url"
        OR NEW."retrieved_at" IS DISTINCT FROM OLD."retrieved_at"
        OR NEW."published_at" IS DISTINCT FROM OLD."published_at"
        OR NEW."content_sha256" IS DISTINCT FROM OLD."content_sha256"
        OR NEW."mime_type" IS DISTINCT FROM OLD."mime_type"
    ) THEN
        RAISE EXCEPTION 'a fonte de identidade organizacional é imutável; acrescente nova prova';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "source_documents_protect_base_organisation_identity"
BEFORE UPDATE ON "source_documents"
FOR EACH ROW EXECUTE FUNCTION "protect_base_organisation_identity_source"();

CREATE FUNCTION "reject_base_organisation_identity_observation_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'base_organisation_identity_observations preserva histórico privado; UPDATE, DELETE e TRUNCATE são proibidos';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "base_organisation_identity_observations_append_only_rows"
BEFORE UPDATE OR DELETE ON "base_organisation_identity_observations"
FOR EACH ROW EXECUTE FUNCTION "reject_base_organisation_identity_observation_mutation"();

CREATE TRIGGER "base_organisation_identity_observations_append_only_truncate"
BEFORE TRUNCATE ON "base_organisation_identity_observations"
FOR EACH STATEMENT EXECUTE FUNCTION "reject_base_organisation_identity_observation_mutation"();

-- O valor legado permanece legível para auditoria histórica, mas nomes
-- normalizados deixam de poder criar novos candidatos privados.
CREATE FUNCTION "reject_new_normalised_name_contract_match"()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT' AND NEW."method"::text = 'NORMALISED_NAME')
       OR (
           TG_OP = 'UPDATE'
           AND (
               OLD."method"::text = 'NORMALISED_NAME'
               OR NEW."method"::text = 'NORMALISED_NAME'
           )
       ) THEN
        RAISE EXCEPTION
            'NORMALISED_NAME é histórico e não pode criar ou alterar correspondências; exige identificador oficial exato';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "contract_match_reviews_reject_new_normalised_name"
BEFORE INSERT OR UPDATE ON "contract_match_reviews"
FOR EACH ROW EXECUTE FUNCTION "reject_new_normalised_name_contract_match"();

CREATE OR REPLACE FUNCTION "validate_editorial_case_insert"()
RETURNS TRIGGER AS $$
DECLARE
    staff_alias TEXT;
BEGIN
    IF NEW."current_version_id" IS NOT NULL
       OR NEW."revision" <> 0
       OR NEW."current_state" <> 'PENDING'::"EditorialState" THEN
        RAISE EXCEPTION
            'um processo editorial nasce privado, PENDING, sem versão projetada e na revisão zero';
    END IF;

    IF NEW."kind"::text <> 'ORGANISATION_IDENTITY' AND EXISTS (
        SELECT 1 FROM "source_documents"
        WHERE "id" = NEW."source_document_id" AND "publisher"::text = 'JUSTICE_REGISTRY'
    ) THEN
        RAISE EXCEPTION 'a prova IRN exige o circuito privado de identidade';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM "source_documents" AS source
        JOIN "source_archive_attestations" AS archive
         ON archive."source_document_id" = source."id"
         AND archive."content_sha256" = source."content_sha256"
         AND archive."retrieval_url" = source."url"
         AND archive."retrieved_at" = source."retrieved_at"
        WHERE source."id" = NEW."source_document_id"
          AND source."url" ~ '^https://'
          AND source."publisher"::text IN (
              'PARLIAMENT', 'DRE', 'TRANSPARENCY_ENTITY', 'BASE_GOV',
              'COURT_OF_AUDIT', 'EUROPEAN_PARLIAMENT', 'PUBLIC_PROSECUTOR',
              'COURT', 'SNS', 'MUNICIPALITY', 'OTHER_OFFICIAL', 'JUSTICE_REGISTRY'
          )
          AND source."kind" <> 'NEWS_ARTICLE'
    ) THEN
        RAISE EXCEPTION
            'o processo editorial exige fonte oficial com URL, data, SHA-256 e arquivo atestado';
    END IF;

    IF NEW."origin" = 'HUMAN'::"EditorialOrigin" THEN
        IF NEW."created_by_id" IS NULL THEN
            RAISE EXCEPTION 'uma proposta humana exige identidade staff';
        END IF;
        SELECT "public_alias"
        INTO staff_alias
        FROM "staff_profiles"
        WHERE "id" = NEW."created_by_id" AND "active" = TRUE;
        IF staff_alias IS NULL OR staff_alias <> NEW."created_by_alias" THEN
            RAISE EXCEPTION 'identidade staff inativa ou alias do criador incoerente';
        END IF;
    ELSIF NEW."created_by_id" IS NOT NULL THEN
        RAISE EXCEPTION 'propostas de ingestão ou IA não podem fingir autoria humana';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION "enforce_organisation_identity_case_private"()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW."kind"::text = 'ORGANISATION_IDENTITY' THEN
        IF NEW."origin"::text <> 'INGESTION'
           OR NEW."created_by_id" IS NOT NULL
           OR NEW."subject_type" <> 'BASE_ORGANISATION_IDENTITY_OBSERVATION'
           OR NOT EXISTS (
               SELECT 1 FROM "base_organisation_identity_observations"
               WHERE "id" = NEW."subject_id"
                 AND "source_document_id" = NEW."source_document_id"
           ) THEN
            RAISE EXCEPTION 'a identidade exige observação privada exata e origem INGESTION';
        END IF;
    END IF;
    IF NEW."kind"::text = 'ORGANISATION_IDENTITY'
       AND NEW."current_state"::text IN ('PUBLISHED', 'WITHDRAWN') THEN
        RAISE EXCEPTION
            'ORGANISATION_IDENTITY é uma prova privada e não admite estado público';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "editorial_cases_keep_organisation_identity_private"
BEFORE INSERT OR UPDATE ON "editorial_cases"
FOR EACH ROW EXECUTE FUNCTION "enforce_organisation_identity_case_private"();

CREATE FUNCTION "reject_organisation_identity_publication_event"()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM "editorial_cases" AS editorial_case
        WHERE editorial_case."id" = NEW."case_id"
          AND editorial_case."kind"::text = 'ORGANISATION_IDENTITY'
    ) THEN
        RAISE EXCEPTION
            'ORGANISATION_IDENTITY não pode originar eventos de publicação ou retirada';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "editorial_publication_events_reject_organisation_identity"
BEFORE INSERT OR UPDATE ON "editorial_publication_events"
FOR EACH ROW EXECUTE FUNCTION "reject_organisation_identity_publication_event"();

ALTER TABLE "base_organisation_identity_observations" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "base_organisation_identity_observations" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "base_organisation_identity_safe_text"(TEXT) FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "protect_base_organisation_identity_source"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_base_organisation_identity_observation_insert"()
FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_base_organisation_identity_observation_mutation"()
FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_new_normalised_name_contract_match"()
FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "enforce_organisation_identity_case_private"()
FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_organisation_identity_publication_event"()
FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I(TEXT) FROM %I',
                'base_organisation_identity_safe_text', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'protect_base_organisation_identity_source', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE %I FROM %I',
                'base_organisation_identity_observations', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'validate_base_organisation_identity_observation_insert', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_base_organisation_identity_observation_mutation', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_new_normalised_name_contract_match', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'enforce_organisation_identity_case_private', api_role
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON FUNCTION %I() FROM %I',
                'reject_organisation_identity_publication_event', api_role
            );
        END IF;
    END LOOP;
END
$$;
