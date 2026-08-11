-- Transparência Total V5: fundação privada do painel e do circuito editorial.
--
-- Ingestão, aprovação e publicação permanecem operações diferentes. Esta
-- migração cria o histórico editorial e reserva os eventos de publicação,
-- mas não promove qualquer dado para as tabelas públicas.

CREATE TYPE "StaffRole" AS ENUM ('ADMIN', 'REVIEWER');

CREATE TYPE "EditorialCaseKind" AS ENUM (
    'PARLIAMENT_ACTIVITY',
    'PARLIAMENT_VOTE',
    'POLITICIAN_PROFILE',
    'GOVERNMENT_PROMISE',
    'PUBLIC_CONTRACT',
    'INTEREST_RELATIONSHIP',
    'RIGHT_OF_REPLY',
    'AI_EXPLANATION',
    'OTHER'
);

CREATE TYPE "EditorialState" AS ENUM (
    'PENDING',
    'IN_REVIEW',
    'APPROVED',
    'REJECTED',
    'PUBLISHED',
    'WITHDRAWN'
);

CREATE TYPE "EditorialDecisionAction" AS ENUM (
    'SUBMIT',
    'START_REVIEW',
    'APPROVE',
    'REJECT',
    'CORRECT',
    'PUBLISH',
    'WITHDRAW'
);

CREATE TYPE "EditorialPublicationAction" AS ENUM ('PUBLISH', 'WITHDRAW');
CREATE TYPE "EditorialOrigin" AS ENUM ('HUMAN', 'INGESTION', 'AI');

CREATE TABLE "staff_profiles" (
    "id" TEXT NOT NULL,
    "auth_user_id" UUID NOT NULL,
    "public_alias" TEXT NOT NULL,
    "role" "StaffRole" NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT TRUE,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "staff_profiles_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "staff_profiles_alias_check"
        CHECK ("public_alias" ~ '^[a-z0-9][a-z0-9._-]{2,79}$')
);

CREATE UNIQUE INDEX "staff_profiles_auth_user_id_key"
ON "staff_profiles"("auth_user_id");

CREATE UNIQUE INDEX "staff_profiles_public_alias_key"
ON "staff_profiles"("public_alias");

CREATE INDEX "staff_profiles_active_role_idx"
ON "staff_profiles"("active", "role");

CREATE TABLE "editorial_cases" (
    "id" TEXT NOT NULL,
    "kind" "EditorialCaseKind" NOT NULL,
    "subject_type" TEXT NOT NULL,
    "subject_id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "origin" "EditorialOrigin" NOT NULL,
    "created_by_id" TEXT,
    "created_by_alias" TEXT NOT NULL,
    "current_version_id" TEXT,
    "current_state" "EditorialState" NOT NULL DEFAULT 'PENDING',
    "revision" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "editorial_cases_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "editorial_cases_subject_type_check"
        CHECK ("subject_type" ~ '^[A-Z][A-Z0-9_]{1,63}$'),
    CONSTRAINT "editorial_cases_subject_id_check"
        CHECK (length(trim("subject_id")) BETWEEN 1 AND 200),
    CONSTRAINT "editorial_cases_creator_alias_check"
        CHECK (length(trim("created_by_alias")) BETWEEN 3 AND 80),
    CONSTRAINT "editorial_cases_revision_check" CHECK ("revision" >= 0)
);

CREATE UNIQUE INDEX "editorial_cases_current_version_id_key"
ON "editorial_cases"("current_version_id");

CREATE UNIQUE INDEX "editorial_cases_subject_source_key"
ON "editorial_cases"("kind", "subject_type", "subject_id", "source_document_id");

CREATE INDEX "editorial_cases_current_state_created_at_id_idx"
ON "editorial_cases"("current_state", "created_at", "id");

CREATE INDEX "editorial_cases_kind_current_state_created_at_id_idx"
ON "editorial_cases"("kind", "current_state", "created_at", "id");

CREATE INDEX "editorial_cases_source_document_id_idx"
ON "editorial_cases"("source_document_id");

CREATE INDEX "editorial_cases_created_by_id_idx"
ON "editorial_cases"("created_by_id");

CREATE TABLE "editorial_versions" (
    "id" TEXT NOT NULL,
    "case_id" TEXT NOT NULL,
    "version_number" INTEGER NOT NULL,
    "normalized_json" JSONB NOT NULL,
    "normalized_sha256" CHAR(64) NOT NULL,
    "previous_version_id" TEXT,
    "origin" "EditorialOrigin" NOT NULL,
    "created_by_id" TEXT,
    "created_by_alias" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "editorial_versions_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "editorial_versions_version_number_check" CHECK ("version_number" > 0),
    CONSTRAINT "editorial_versions_json_object_check"
        CHECK (jsonb_typeof("normalized_json") = 'object'),
    CONSTRAINT "editorial_versions_sha256_check"
        CHECK ("normalized_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "editorial_versions_creator_alias_check"
        CHECK (length(trim("created_by_alias")) BETWEEN 3 AND 80)
);

CREATE UNIQUE INDEX "editorial_versions_previous_version_id_key"
ON "editorial_versions"("previous_version_id");

CREATE UNIQUE INDEX "editorial_versions_case_id_version_number_key"
ON "editorial_versions"("case_id", "version_number");

CREATE UNIQUE INDEX "editorial_versions_case_id_normalized_sha256_key"
ON "editorial_versions"("case_id", "normalized_sha256");

CREATE INDEX "editorial_versions_created_by_id_idx"
ON "editorial_versions"("created_by_id");

CREATE TABLE "editorial_decisions" (
    "id" TEXT NOT NULL,
    "case_id" TEXT NOT NULL,
    "version_id" TEXT NOT NULL,
    "action" "EditorialDecisionAction" NOT NULL,
    "previous_state" "EditorialState",
    "resulting_state" "EditorialState" NOT NULL,
    "case_revision" INTEGER NOT NULL,
    "rationale" TEXT NOT NULL,
    "source_confirmed" BOOLEAN NOT NULL DEFAULT FALSE,
    "actor_id" TEXT NOT NULL,
    "actor_alias" TEXT NOT NULL,
    "decision_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "editorial_decisions_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "editorial_decisions_revision_check" CHECK ("case_revision" > 0),
    CONSTRAINT "editorial_decisions_rationale_check"
        CHECK (length(trim("rationale")) BETWEEN 20 AND 2000),
    CONSTRAINT "editorial_decisions_actor_alias_check"
        CHECK (length(trim("actor_alias")) BETWEEN 3 AND 80),
    CONSTRAINT "editorial_decisions_sha256_check"
        CHECK ("decision_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX "editorial_decisions_decision_sha256_key"
ON "editorial_decisions"("decision_sha256");

CREATE UNIQUE INDEX "editorial_decisions_case_id_case_revision_key"
ON "editorial_decisions"("case_id", "case_revision");

CREATE INDEX "editorial_decisions_case_id_created_at_id_idx"
ON "editorial_decisions"("case_id", "created_at", "id");

CREATE INDEX "editorial_decisions_resulting_state_created_at_idx"
ON "editorial_decisions"("resulting_state", "created_at");

CREATE INDEX "editorial_decisions_version_id_idx"
ON "editorial_decisions"("version_id");

CREATE INDEX "editorial_decisions_actor_id_idx"
ON "editorial_decisions"("actor_id");

CREATE TABLE "editorial_publication_events" (
    "id" TEXT NOT NULL,
    "case_id" TEXT NOT NULL,
    "version_id" TEXT NOT NULL,
    "action" "EditorialPublicationAction" NOT NULL,
    "target_type" TEXT NOT NULL,
    "target_id" TEXT NOT NULL,
    "rationale" TEXT NOT NULL,
    "actor_id" TEXT NOT NULL,
    "actor_alias" TEXT NOT NULL,
    "event_sha256" CHAR(64) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "editorial_publication_events_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "editorial_publication_events_target_type_check"
        CHECK ("target_type" ~ '^[A-Z][A-Z0-9_]{1,63}$'),
    CONSTRAINT "editorial_publication_events_target_id_check"
        CHECK (length(trim("target_id")) BETWEEN 1 AND 200),
    CONSTRAINT "editorial_publication_events_rationale_check"
        CHECK (length(trim("rationale")) BETWEEN 20 AND 2000),
    CONSTRAINT "editorial_publication_events_actor_alias_check"
        CHECK (length(trim("actor_alias")) BETWEEN 3 AND 80),
    CONSTRAINT "editorial_publication_events_sha256_check"
        CHECK ("event_sha256" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX "editorial_publication_events_event_sha256_key"
ON "editorial_publication_events"("event_sha256");

CREATE UNIQUE INDEX "editorial_publication_events_case_action_target_key"
ON "editorial_publication_events"("case_id", "action", "target_type", "target_id");

CREATE INDEX "editorial_publication_events_case_id_created_at_id_idx"
ON "editorial_publication_events"("case_id", "created_at", "id");

CREATE INDEX "editorial_publication_events_target_type_target_id_created_at_idx"
ON "editorial_publication_events"("target_type", "target_id", "created_at");

CREATE INDEX "editorial_publication_events_version_id_idx"
ON "editorial_publication_events"("version_id");

CREATE INDEX "editorial_publication_events_actor_id_idx"
ON "editorial_publication_events"("actor_id");

ALTER TABLE "editorial_cases"
ADD CONSTRAINT "editorial_cases_source_document_id_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_cases"
ADD CONSTRAINT "editorial_cases_created_by_id_fkey"
FOREIGN KEY ("created_by_id") REFERENCES "staff_profiles"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_versions"
ADD CONSTRAINT "editorial_versions_case_id_fkey"
FOREIGN KEY ("case_id") REFERENCES "editorial_cases"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_versions"
ADD CONSTRAINT "editorial_versions_previous_version_id_fkey"
FOREIGN KEY ("previous_version_id") REFERENCES "editorial_versions"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_versions"
ADD CONSTRAINT "editorial_versions_created_by_id_fkey"
FOREIGN KEY ("created_by_id") REFERENCES "staff_profiles"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_cases"
ADD CONSTRAINT "editorial_cases_current_version_id_fkey"
FOREIGN KEY ("current_version_id") REFERENCES "editorial_versions"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_decisions"
ADD CONSTRAINT "editorial_decisions_case_id_fkey"
FOREIGN KEY ("case_id") REFERENCES "editorial_cases"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_decisions"
ADD CONSTRAINT "editorial_decisions_version_id_fkey"
FOREIGN KEY ("version_id") REFERENCES "editorial_versions"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_decisions"
ADD CONSTRAINT "editorial_decisions_actor_id_fkey"
FOREIGN KEY ("actor_id") REFERENCES "staff_profiles"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_publication_events"
ADD CONSTRAINT "editorial_publication_events_case_id_fkey"
FOREIGN KEY ("case_id") REFERENCES "editorial_cases"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_publication_events"
ADD CONSTRAINT "editorial_publication_events_version_id_fkey"
FOREIGN KEY ("version_id") REFERENCES "editorial_versions"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "editorial_publication_events"
ADD CONSTRAINT "editorial_publication_events_actor_id_fkey"
FOREIGN KEY ("actor_id") REFERENCES "staff_profiles"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

-- Num projeto Supabase, a identidade interna aponta para auth.users. O bloco é
-- deliberadamente condicional para os testes em PostgreSQL convencional.
DO $$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL THEN
        ALTER TABLE "staff_profiles"
        ADD CONSTRAINT "staff_profiles_auth_user_id_fkey"
        FOREIGN KEY ("auth_user_id") REFERENCES auth.users("id")
        ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END
$$;

CREATE FUNCTION "validate_editorial_case_insert"()
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
          AND source."publisher" IN (
              'PARLIAMENT', 'DRE', 'TRANSPARENCY_ENTITY', 'BASE_GOV',
              'COURT_OF_AUDIT', 'EUROPEAN_PARLIAMENT', 'PUBLIC_PROSECUTOR',
              'COURT', 'SNS', 'MUNICIPALITY', 'OTHER_OFFICIAL'
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

CREATE TRIGGER "editorial_cases_validate_insert"
BEFORE INSERT ON "editorial_cases"
FOR EACH ROW EXECUTE FUNCTION "validate_editorial_case_insert"();

CREATE FUNCTION "validate_editorial_version_insert"()
RETURNS TRIGGER AS $$
DECLARE
    case_record RECORD;
    last_version INTEGER;
    staff_alias TEXT;
BEGIN
    SELECT "current_version_id", "current_state"
    INTO case_record
    FROM "editorial_cases"
    WHERE "id" = NEW."case_id"
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'processo editorial não encontrado';
    END IF;

    SELECT COALESCE(max("version_number"), 0)
    INTO last_version
    FROM "editorial_versions"
    WHERE "case_id" = NEW."case_id";

    IF NEW."version_number" <> last_version + 1 THEN
        RAISE EXCEPTION 'a numeração editorial tem de ser contínua';
    END IF;

    IF last_version = 0 THEN
        IF NEW."previous_version_id" IS NOT NULL OR case_record."current_version_id" IS NOT NULL THEN
            RAISE EXCEPTION 'a primeira versão não pode ter antecessora';
        END IF;
    ELSIF NEW."previous_version_id" IS DISTINCT FROM case_record."current_version_id" THEN
        RAISE EXCEPTION 'a correção tem de suceder à versão atualmente projetada';
    ELSIF case_record."current_state" NOT IN (
        'IN_REVIEW'::"EditorialState",
        'APPROVED'::"EditorialState",
        'REJECTED'::"EditorialState"
    ) THEN
        RAISE EXCEPTION 'o estado atual não admite uma nova versão editorial';
    END IF;

    IF NEW."origin" = 'HUMAN'::"EditorialOrigin" THEN
        IF NEW."created_by_id" IS NULL THEN
            RAISE EXCEPTION 'uma versão humana exige identidade staff';
        END IF;
        SELECT "public_alias"
        INTO staff_alias
        FROM "staff_profiles"
        WHERE "id" = NEW."created_by_id" AND "active" = TRUE;
        IF staff_alias IS NULL OR staff_alias <> NEW."created_by_alias" THEN
            RAISE EXCEPTION 'identidade staff inativa ou alias do autor incoerente';
        END IF;
    ELSIF NEW."created_by_id" IS NOT NULL THEN
        RAISE EXCEPTION 'versões de ingestão ou IA não podem fingir autoria humana';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "editorial_versions_validate_insert"
BEFORE INSERT ON "editorial_versions"
FOR EACH ROW EXECUTE FUNCTION "validate_editorial_version_insert"();

CREATE FUNCTION "validate_editorial_decision_insert"()
RETURNS TRIGGER AS $$
DECLARE
    case_record RECORD;
    version_record RECORD;
    staff_record RECORD;
BEGIN
    SELECT "current_version_id", "current_state", "revision"
    INTO case_record
    FROM "editorial_cases"
    WHERE "id" = NEW."case_id"
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'processo editorial não encontrado';
    END IF;

    SELECT "case_id", "version_number", "previous_version_id"
    INTO version_record
    FROM "editorial_versions"
    WHERE "id" = NEW."version_id";

    IF NOT FOUND OR version_record."case_id" <> NEW."case_id" THEN
        RAISE EXCEPTION 'a decisão exige uma versão do mesmo processo';
    END IF;

    SELECT "public_alias", "role", "active"
    INTO staff_record
    FROM "staff_profiles"
    WHERE "id" = NEW."actor_id";

    IF NOT FOUND OR staff_record."active" = FALSE
       OR staff_record."public_alias" <> NEW."actor_alias" THEN
        RAISE EXCEPTION 'a decisão exige identidade staff ativa e coerente';
    END IF;

    IF NEW."case_revision" <> case_record."revision" + 1 THEN
        RAISE EXCEPTION 'a revisão editorial esperada já não é a atual';
    END IF;

    IF NEW."action" = 'SUBMIT'::"EditorialDecisionAction" THEN
        IF case_record."revision" <> 0
           OR case_record."current_version_id" IS NOT NULL
           OR version_record."version_number" <> 1
           OR NEW."previous_state" IS NOT NULL
           OR NEW."resulting_state" <> 'PENDING'::"EditorialState"
           OR NEW."source_confirmed" = TRUE THEN
            RAISE EXCEPTION 'transição SUBMIT inválida';
        END IF;
    ELSE
        IF NEW."previous_state" IS DISTINCT FROM case_record."current_state" THEN
            RAISE EXCEPTION 'o estado anterior da decisão já não é o atual';
        END IF;

        IF NEW."action" = 'START_REVIEW'::"EditorialDecisionAction" THEN
            IF case_record."current_state" <> 'PENDING'::"EditorialState"
               OR NEW."resulting_state" <> 'IN_REVIEW'::"EditorialState"
               OR NEW."version_id" IS DISTINCT FROM case_record."current_version_id"
               OR NEW."source_confirmed" = TRUE THEN
                RAISE EXCEPTION 'transição START_REVIEW inválida';
            END IF;
        ELSIF NEW."action" = 'APPROVE'::"EditorialDecisionAction" THEN
            IF case_record."current_state" <> 'IN_REVIEW'::"EditorialState"
               OR NEW."resulting_state" <> 'APPROVED'::"EditorialState"
               OR NEW."version_id" IS DISTINCT FROM case_record."current_version_id"
               OR NEW."source_confirmed" = FALSE THEN
                RAISE EXCEPTION 'transição APPROVE inválida';
            END IF;
        ELSIF NEW."action" = 'REJECT'::"EditorialDecisionAction" THEN
            IF case_record."current_state" <> 'IN_REVIEW'::"EditorialState"
               OR NEW."resulting_state" <> 'REJECTED'::"EditorialState"
               OR NEW."version_id" IS DISTINCT FROM case_record."current_version_id"
               OR NEW."source_confirmed" = TRUE THEN
                RAISE EXCEPTION 'transição REJECT inválida';
            END IF;
        ELSIF NEW."action" = 'CORRECT'::"EditorialDecisionAction" THEN
            IF case_record."current_state" NOT IN (
                    'IN_REVIEW'::"EditorialState",
                    'APPROVED'::"EditorialState",
                    'REJECTED'::"EditorialState"
               )
               OR NEW."resulting_state" <> 'PENDING'::"EditorialState"
               OR version_record."previous_version_id" IS DISTINCT FROM case_record."current_version_id"
               OR NEW."source_confirmed" = TRUE THEN
                RAISE EXCEPTION 'transição CORRECT inválida';
            END IF;
        ELSIF NEW."action" = 'PUBLISH'::"EditorialDecisionAction" THEN
            IF staff_record."role" <> 'ADMIN'::"StaffRole"
               OR case_record."current_state" <> 'APPROVED'::"EditorialState"
               OR NEW."resulting_state" <> 'PUBLISHED'::"EditorialState"
               OR NEW."version_id" IS DISTINCT FROM case_record."current_version_id"
               OR NEW."source_confirmed" = FALSE THEN
                RAISE EXCEPTION 'transição PUBLISH inválida';
            END IF;
        ELSIF NEW."action" = 'WITHDRAW'::"EditorialDecisionAction" THEN
            IF staff_record."role" <> 'ADMIN'::"StaffRole"
               OR case_record."current_state" <> 'PUBLISHED'::"EditorialState"
               OR NEW."resulting_state" <> 'WITHDRAWN'::"EditorialState"
               OR NEW."version_id" IS DISTINCT FROM case_record."current_version_id"
               OR NEW."source_confirmed" = TRUE THEN
                RAISE EXCEPTION 'transição WITHDRAW inválida';
            END IF;
        ELSE
            RAISE EXCEPTION 'ação editorial desconhecida';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "editorial_decisions_validate_insert"
BEFORE INSERT ON "editorial_decisions"
FOR EACH ROW EXECUTE FUNCTION "validate_editorial_decision_insert"();

CREATE FUNCTION "protect_editorial_case_projection"()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'editorial_cases preserva o histórico; DELETE é proibido';
    END IF;

    IF NEW."id" IS DISTINCT FROM OLD."id"
       OR NEW."kind" IS DISTINCT FROM OLD."kind"
       OR NEW."subject_type" IS DISTINCT FROM OLD."subject_type"
       OR NEW."subject_id" IS DISTINCT FROM OLD."subject_id"
       OR NEW."source_document_id" IS DISTINCT FROM OLD."source_document_id"
       OR NEW."origin" IS DISTINCT FROM OLD."origin"
       OR NEW."created_by_id" IS DISTINCT FROM OLD."created_by_id"
       OR NEW."created_by_alias" IS DISTINCT FROM OLD."created_by_alias"
       OR NEW."created_at" IS DISTINCT FROM OLD."created_at" THEN
        RAISE EXCEPTION 'os dados de origem do processo editorial são imutáveis';
    END IF;

    IF NEW."revision" <> OLD."revision" + 1 THEN
        RAISE EXCEPTION 'a projeção editorial exige incremento unitário da revisão';
    END IF;

    IF NEW."current_version_id" IS NULL THEN
        RAISE EXCEPTION 'a projeção editorial exige uma versão atual';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM "editorial_decisions" AS decision
        WHERE decision."case_id" = NEW."id"
          AND decision."case_revision" = NEW."revision"
          AND decision."version_id" = NEW."current_version_id"
          AND decision."resulting_state" = NEW."current_state"
          AND (
              (OLD."revision" = 0 AND decision."action" = 'SUBMIT'::"EditorialDecisionAction")
              OR decision."previous_state" = OLD."current_state"
          )
    ) THEN
        RAISE EXCEPTION 'a projeção editorial exige decisão imutável correspondente';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "editorial_cases_protect_projection"
BEFORE UPDATE OR DELETE ON "editorial_cases"
FOR EACH ROW EXECUTE FUNCTION "protect_editorial_case_projection"();

CREATE FUNCTION "reject_editorial_history_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% é histórico editorial append-only; UPDATE e DELETE são proibidos',
        TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "editorial_versions_append_only"
BEFORE UPDATE OR DELETE ON "editorial_versions"
FOR EACH ROW EXECUTE FUNCTION "reject_editorial_history_mutation"();

CREATE TRIGGER "editorial_decisions_append_only"
BEFORE UPDATE OR DELETE ON "editorial_decisions"
FOR EACH ROW EXECUTE FUNCTION "reject_editorial_history_mutation"();

CREATE TRIGGER "editorial_publication_events_append_only"
BEFORE UPDATE OR DELETE ON "editorial_publication_events"
FOR EACH ROW EXECUTE FUNCTION "reject_editorial_history_mutation"();

CREATE FUNCTION "validate_editorial_publication_event_insert"()
RETURNS TRIGGER AS $$
DECLARE
    case_state "EditorialState";
    version_case_id TEXT;
    staff_record RECORD;
BEGIN
    SELECT "current_state"
    INTO case_state
    FROM "editorial_cases"
    WHERE "id" = NEW."case_id"
      AND "current_version_id" = NEW."version_id";

    SELECT "case_id"
    INTO version_case_id
    FROM "editorial_versions"
    WHERE "id" = NEW."version_id";

    SELECT "public_alias", "role", "active"
    INTO staff_record
    FROM "staff_profiles"
    WHERE "id" = NEW."actor_id";

    IF case_state IS NULL OR version_case_id IS DISTINCT FROM NEW."case_id" THEN
        RAISE EXCEPTION 'o evento de publicação exige a versão atual do mesmo processo';
    END IF;
    IF NOT FOUND OR staff_record."active" = FALSE
       OR staff_record."role" <> 'ADMIN'::"StaffRole"
       OR staff_record."public_alias" <> NEW."actor_alias" THEN
        RAISE EXCEPTION 'o evento de publicação exige administrador ativo';
    END IF;
    IF (NEW."action" = 'PUBLISH'::"EditorialPublicationAction"
        AND case_state <> 'PUBLISHED'::"EditorialState")
       OR (NEW."action" = 'WITHDRAW'::"EditorialPublicationAction"
        AND case_state <> 'WITHDRAWN'::"EditorialState") THEN
        RAISE EXCEPTION 'o evento de publicação não corresponde ao estado editorial';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "editorial_publication_events_validate_insert"
BEFORE INSERT ON "editorial_publication_events"
FOR EACH ROW EXECUTE FUNCTION "validate_editorial_publication_event_insert"();

-- A restrição diferida permite ao adaptador escrever decisão, projeção e evento
-- na mesma transação, mas impede que um estado público seja confirmado no COMMIT
-- sem o respetivo evento append-only.
CREATE FUNCTION "require_editorial_publication_event"()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW."current_state" = 'PUBLISHED'::"EditorialState"
       AND NOT EXISTS (
           SELECT 1
           FROM "editorial_publication_events" AS publication
           WHERE publication."case_id" = NEW."id"
             AND publication."version_id" = NEW."current_version_id"
             AND publication."action" = 'PUBLISH'::"EditorialPublicationAction"
       ) THEN
        RAISE EXCEPTION 'o estado PUBLISHED exige evento de publicação imutável';
    END IF;
    IF NEW."current_state" = 'WITHDRAWN'::"EditorialState"
       AND NOT EXISTS (
           SELECT 1
           FROM "editorial_publication_events" AS publication
           WHERE publication."case_id" = NEW."id"
             AND publication."version_id" = NEW."current_version_id"
             AND publication."action" = 'WITHDRAW'::"EditorialPublicationAction"
       ) THEN
        RAISE EXCEPTION 'o estado WITHDRAWN exige evento de retirada imutável';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE CONSTRAINT TRIGGER "editorial_cases_require_publication_event"
AFTER UPDATE ON "editorial_cases"
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION "require_editorial_publication_event"();

-- As tabelas editoriais são servidas apenas pela API privada. Não recebem
-- políticas nem privilégios para clientes browser, mesmo autenticados.
ALTER TABLE "staff_profiles" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "editorial_cases" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "editorial_versions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "editorial_decisions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "editorial_publication_events" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "staff_profiles" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "editorial_cases" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "editorial_versions" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "editorial_decisions" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON "editorial_publication_events" FROM PUBLIC;

REVOKE ALL PRIVILEGES ON FUNCTION "validate_editorial_case_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_editorial_version_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_editorial_decision_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "protect_editorial_case_projection"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "reject_editorial_history_mutation"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "validate_editorial_publication_event_insert"() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION "require_editorial_publication_event"() FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I FROM %I', 'staff_profiles', api_role);
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I FROM %I', 'editorial_cases', api_role);
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I FROM %I', 'editorial_versions', api_role);
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I FROM %I', 'editorial_decisions', api_role);
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I FROM %I', 'editorial_publication_events', api_role);
        END IF;
    END LOOP;
END
$$;
