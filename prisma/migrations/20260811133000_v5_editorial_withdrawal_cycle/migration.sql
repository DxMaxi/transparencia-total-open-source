-- V5.4: uma publicação pode ser retirada, corrigida numa nova versão e publicada de novo.
-- Os eventos continuam únicos por versão, ação e alvo; nenhum histórico é alterado.
DROP INDEX "editorial_publication_events_case_action_target_key";

CREATE UNIQUE INDEX "editorial_publication_events_case_version_action_target_key"
ON "editorial_publication_events"(
    "case_id", "version_id", "action", "target_type", "target_id"
);

CREATE OR REPLACE FUNCTION "validate_editorial_version_insert"()
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
        'REJECTED'::"EditorialState",
        'WITHDRAWN'::"EditorialState"
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

CREATE OR REPLACE FUNCTION "validate_editorial_decision_insert"()
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
                    'REJECTED'::"EditorialState",
                    'WITHDRAWN'::"EditorialState"
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
