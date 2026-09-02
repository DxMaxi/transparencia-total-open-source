-- V5.51: promoção e retirada específicas dos contratos Portal BASE.
--
-- A linha public_contracts continua a ser a projeção de consulta. Cada conjunto
-- de campos que alguma vez foi publicado fica preservado nesta fotografia
-- append-only, ligada ao snapshot privado, à versão editorial e à fonte exatos.

CREATE TABLE "base_public_contract_publication_snapshots" (
    "id" TEXT NOT NULL,
    "public_contract_id" TEXT NOT NULL,
    "contract_snapshot_id" TEXT NOT NULL,
    "editorial_case_id" TEXT NOT NULL,
    "editorial_version_id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "object" TEXT NOT NULL,
    "procedure" "PublicContractProcedure" NOT NULL DEFAULT 'UNKNOWN',
    "cpv_code" TEXT,
    "base_value" DECIMAL(20,2),
    "contract_value" DECIMAL(20,2),
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "decision_at" TIMESTAMP(3),
    "signed_at" TIMESTAMP(3),
    "published_at" TIMESTAMP(3),
    "execution_days" INTEGER,
    "direct_official_url" TEXT,
    "source_record_sha256" CHAR(64) NOT NULL,
    "publication_proof_sha256" CHAR(64) NOT NULL,
    "created_by_alias" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_public_contract_publication_snapshots_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_public_contract_publication_source_id_check"
      CHECK (length(btrim("source_id")) BETWEEN 1 AND 500),
    CONSTRAINT "base_public_contract_publication_object_check"
      CHECK (length(btrim("object")) BETWEEN 1 AND 20000),
    CONSTRAINT "base_public_contract_publication_currency_check"
      CHECK ("currency" ~ '^[A-Z]{3}$'),
    CONSTRAINT "base_public_contract_publication_values_check"
      CHECK (("base_value" IS NULL OR "base_value" >= 0)
         AND ("contract_value" IS NULL OR "contract_value" >= 0)),
    CONSTRAINT "base_public_contract_publication_execution_days_check"
      CHECK ("execution_days" IS NULL OR "execution_days" >= 0),
    CONSTRAINT "base_public_contract_publication_hashes_check"
      CHECK ("source_record_sha256" ~ '^[0-9a-f]{64}$'
         AND "publication_proof_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_public_contract_publication_alias_check"
      CHECK (length(btrim("created_by_alias")) BETWEEN 3 AND 80),
    CONSTRAINT "base_public_contract_publication_direct_url_check"
      CHECK ("direct_official_url" IS NULL OR "direct_official_url" LIKE 'https://%')
);

CREATE UNIQUE INDEX "base_public_contract_publication_contract_snapshot_key"
ON "base_public_contract_publication_snapshots"("contract_snapshot_id");

CREATE UNIQUE INDEX "base_public_contract_publication_editorial_version_key"
ON "base_public_contract_publication_snapshots"("editorial_version_id");

CREATE UNIQUE INDEX "base_public_contract_publication_proof_key"
ON "base_public_contract_publication_snapshots"("publication_proof_sha256");

CREATE INDEX "base_public_contract_publication_contract_created_idx"
ON "base_public_contract_publication_snapshots"("public_contract_id", "created_at");

CREATE INDEX "base_public_contract_publication_source_created_idx"
ON "base_public_contract_publication_snapshots"("source_id", "created_at");

CREATE INDEX "base_public_contract_publication_source_document_idx"
ON "base_public_contract_publication_snapshots"("source_document_id");

CREATE INDEX "base_public_contract_publication_case_created_idx"
ON "base_public_contract_publication_snapshots"("editorial_case_id", "created_at");

ALTER TABLE "base_public_contract_publication_snapshots"
ADD CONSTRAINT "base_public_contract_publication_contract_fkey"
FOREIGN KEY ("public_contract_id") REFERENCES "public_contracts"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "base_public_contract_publication_snapshots"
ADD CONSTRAINT "base_public_contract_publication_snapshot_fkey"
FOREIGN KEY ("contract_snapshot_id") REFERENCES "base_contract_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "base_public_contract_publication_snapshots"
ADD CONSTRAINT "base_public_contract_publication_case_fkey"
FOREIGN KEY ("editorial_case_id") REFERENCES "editorial_cases"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "base_public_contract_publication_snapshots"
ADD CONSTRAINT "base_public_contract_publication_version_fkey"
FOREIGN KEY ("editorial_version_id") REFERENCES "editorial_versions"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "base_public_contract_publication_snapshots"
ADD CONSTRAINT "base_public_contract_publication_source_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "public_contracts"
ADD COLUMN "current_publication_snapshot_id" TEXT;

-- Falha fechada perante qualquer publicação BASE anterior sem fotografia V5.51.
-- A migração não converte, apaga nem legitima silenciosamente linhas legadas:
-- essas linhas têm de ser investigadas antes de voltar a tentar a migração.
ALTER TABLE "public_contracts"
ADD CONSTRAINT "public_contracts_base_publication_state_check"
CHECK (
    (
        "current_publication_snapshot_id" IS NULL
        AND "publication_status" NOT IN (
            'PUBLISHED'::"PublicationStatus", 'WITHDRAWN'::"PublicationStatus"
        )
        AND "verification_status" <> 'VERIFIED'::"VerificationStatus"
    )
    OR
    (
        "current_publication_snapshot_id" IS NOT NULL
        AND "publication_status" IN (
            'PUBLISHED'::"PublicationStatus", 'WITHDRAWN'::"PublicationStatus"
        )
        AND "verification_status" = 'VERIFIED'::"VerificationStatus"
    )
);

CREATE UNIQUE INDEX "public_contracts_current_publication_snapshot_key"
ON "public_contracts"("current_publication_snapshot_id");

ALTER TABLE "public_contracts"
ADD CONSTRAINT "public_contracts_current_publication_snapshot_fkey"
FOREIGN KEY ("current_publication_snapshot_id")
REFERENCES "base_public_contract_publication_snapshots"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE FUNCTION "reject_base_public_contract_publication_snapshot_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
      'base_public_contract_publication_snapshots é histórico append-only; UPDATE e DELETE são proibidos';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "base_public_contract_publication_snapshots_append_only"
BEFORE UPDATE OR DELETE ON "base_public_contract_publication_snapshots"
FOR EACH ROW EXECUTE FUNCTION "reject_base_public_contract_publication_snapshot_mutation"();

CREATE TRIGGER "base_public_contract_publication_snapshots_no_truncate"
BEFORE TRUNCATE ON "base_public_contract_publication_snapshots"
FOR EACH STATEMENT EXECUTE FUNCTION "reject_base_public_contract_publication_snapshot_mutation"();

CREATE FUNCTION "validate_base_public_contract_projection"()
RETURNS TRIGGER AS $$
DECLARE
    publication RECORD;
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD."current_publication_snapshot_id" IS NOT NULL THEN
            RAISE EXCEPTION 'um contrato com histórico publicado não pode ser apagado';
        END IF;
        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD."current_publication_snapshot_id" IS NOT NULL
       AND NEW."current_publication_snapshot_id" IS NULL THEN
        RAISE EXCEPTION 'a referência à fotografia pública não pode ser removida';
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD."current_publication_snapshot_id" IS NOT NULL
       AND NEW."current_publication_snapshot_id"
           IS DISTINCT FROM OLD."current_publication_snapshot_id"
       AND (
           OLD."publication_status" <> 'WITHDRAWN'::"PublicationStatus"
           OR NEW."publication_status" <> 'PUBLISHED'::"PublicationStatus"
       ) THEN
        RAISE EXCEPTION
          'uma nova fotografia exige transição explícita de retirada para publicação';
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD."publication_status" = 'WITHDRAWN'::"PublicationStatus"
       AND NEW."publication_status" = 'PUBLISHED'::"PublicationStatus"
       AND NEW."current_publication_snapshot_id"
           IS NOT DISTINCT FROM OLD."current_publication_snapshot_id" THEN
        RAISE EXCEPTION 'uma republicação exige uma nova fotografia imutável';
    END IF;

    IF NEW."current_publication_snapshot_id" IS NULL THEN
        IF NEW."publication_status" IN (
            'PUBLISHED'::"PublicationStatus", 'WITHDRAWN'::"PublicationStatus"
        ) OR NEW."verification_status" = 'VERIFIED'::"VerificationStatus" THEN
            RAISE EXCEPTION 'um contrato público exige fotografia de publicação imutável';
        END IF;
        RETURN NEW;
    END IF;

    SELECT * INTO publication
    FROM "base_public_contract_publication_snapshots"
    WHERE "id" = NEW."current_publication_snapshot_id";

    IF NOT FOUND OR publication."public_contract_id" <> NEW."id" THEN
        RAISE EXCEPTION 'a fotografia pública não pertence ao contrato projetado';
    END IF;

    IF NEW."source_id" IS DISTINCT FROM publication."source_id"
       OR NEW."object" IS DISTINCT FROM publication."object"
       OR NEW."procedure" IS DISTINCT FROM publication."procedure"
       OR NEW."cpv_code" IS DISTINCT FROM publication."cpv_code"
       OR NEW."base_value" IS DISTINCT FROM publication."base_value"
       OR NEW."contract_value" IS DISTINCT FROM publication."contract_value"
       OR NEW."currency" IS DISTINCT FROM publication."currency"
       OR NEW."decision_at" IS DISTINCT FROM publication."decision_at"
       OR NEW."signed_at" IS DISTINCT FROM publication."signed_at"
       OR NEW."published_at" IS DISTINCT FROM publication."published_at"
       OR NEW."execution_days" IS DISTINCT FROM publication."execution_days"
       OR NEW."source_document_id" IS DISTINCT FROM publication."source_document_id" THEN
        RAISE EXCEPTION 'a projeção do contrato diverge da fotografia pública imutável';
    END IF;

    IF NEW."publication_status" NOT IN (
        'PUBLISHED'::"PublicationStatus", 'WITHDRAWN'::"PublicationStatus"
    ) OR NEW."verification_status" <> 'VERIFIED'::"VerificationStatus" THEN
        RAISE EXCEPTION 'uma projeção com fotografia exige estado verificado e público ou retirado';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "public_contracts_validate_base_projection"
BEFORE INSERT OR UPDATE OR DELETE ON "public_contracts"
FOR EACH ROW EXECUTE FUNCTION "validate_base_public_contract_projection"();

-- A projeção e o evento são escritos em momentos distintos da mesma transação.
-- Esta verificação diferida observa o estado final no COMMIT e exige que o
-- último evento pertença ao processo e à versão guardados na fotografia atual.
CREATE FUNCTION "validate_base_public_contract_latest_event"()
RETURNS TRIGGER AS $$
DECLARE
    snapshot_case_id TEXT;
    snapshot_version_id TEXT;
    latest_action TEXT;
    latest_case_id TEXT;
    latest_version_id TEXT;
BEGIN
    IF NEW."current_publication_snapshot_id" IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT snapshot."editorial_case_id", snapshot."editorial_version_id",
           event."action"::text, event."case_id", event."version_id"
    INTO snapshot_case_id, snapshot_version_id,
         latest_action, latest_case_id, latest_version_id
    FROM "base_public_contract_publication_snapshots" AS snapshot
    LEFT JOIN LATERAL (
        SELECT publication."action", publication."case_id", publication."version_id"
        FROM "editorial_publication_events" AS publication
        WHERE publication."target_type" = 'BASE_PUBLIC_CONTRACT'
          AND publication."target_id" = NEW."id"
        ORDER BY publication."created_at" DESC, publication."id" DESC
        LIMIT 1
    ) AS event ON TRUE
    WHERE snapshot."id" = NEW."current_publication_snapshot_id";

    IF latest_case_id IS DISTINCT FROM snapshot_case_id
       OR latest_version_id IS DISTINCT FROM snapshot_version_id THEN
        RAISE EXCEPTION
          'o último evento público não pertence ao processo e versão da fotografia BASE';
    END IF;

    IF (NEW."publication_status" = 'PUBLISHED'::"PublicationStatus"
        AND latest_action IS DISTINCT FROM 'PUBLISH')
       OR (NEW."publication_status" = 'WITHDRAWN'::"PublicationStatus"
           AND latest_action IS DISTINCT FROM 'WITHDRAW') THEN
        RAISE EXCEPTION 'o estado do contrato diverge do último evento público BASE';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE CONSTRAINT TRIGGER "public_contracts_validate_base_latest_event"
AFTER INSERT OR UPDATE ON "public_contracts"
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION "validate_base_public_contract_latest_event"();

-- A V5.51 publica sempre zero partes. Mesmo uma escrita concorrente posterior
-- ao COMMIT não pode anexar, alterar ou apagar uma designação num contrato que
-- já entrou no circuito específico. A futura porta de partes terá de substituir
-- esta barreira através de uma migração própria e auditável.
CREATE FUNCTION "reject_v551_public_contract_party_mutation"()
RETURNS TRIGGER AS $$
DECLARE
    old_contract_is_v551 BOOLEAN := FALSE;
    new_contract_is_v551 BOOLEAN := FALSE;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        SELECT EXISTS (
            SELECT 1 FROM "public_contracts"
            WHERE "id" = OLD."public_contract_id"
              AND "current_publication_snapshot_id" IS NOT NULL
        ) INTO old_contract_is_v551;
    END IF;

    IF TG_OP <> 'DELETE' THEN
        SELECT EXISTS (
            SELECT 1 FROM "public_contracts"
            WHERE "id" = NEW."public_contract_id"
              AND "current_publication_snapshot_id" IS NOT NULL
        ) INTO new_contract_is_v551;
    END IF;

    IF old_contract_is_v551 OR new_contract_is_v551 THEN
        RAISE EXCEPTION
          'as partes de contratos V5.51 permanecem bloqueadas até existir porta editorial própria';
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "public_contract_parties_block_v551_mutation"
BEFORE INSERT OR UPDATE OR DELETE ON "public_contract_parties"
FOR EACH ROW EXECUTE FUNCTION "reject_v551_public_contract_party_mutation"();

ALTER TABLE "base_public_contract_publication_snapshots" ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON "base_public_contract_publication_snapshots" FROM PUBLIC;

DO $$
DECLARE
    api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I',
                'base_public_contract_publication_snapshots', api_role
            );
        END IF;
    END LOOP;
END
$$;
