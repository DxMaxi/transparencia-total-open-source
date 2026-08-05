-- V4.3: porta de elegibilidade para promoção de contratos BASE do staging privado
--
-- Esta migração NÃO cria nenhuma tabela pública nova: PublicContract, Organisation,
-- InterestEntity, PublicContractParty, DataPublicationReview e AuditEvent já existem
-- desde a V2 (grafo cívico). O que faltava era a porta de elegibilidade ao nível do
-- lote — uma decisão humana explícita e reversível de que "este lote pode entrar em
-- consideração para promoção", distinta e anterior à decisão por contrato individual.
--
-- A promoção contrato-a-contrato em si (staging -> PublicContract) é feita pela
-- camada de aplicação numa única transação (ver backend/app/repositories/base_promotion.py),
-- nunca automaticamente a partir da ingestão.

ALTER TABLE "base_staging_batches"
    ADD COLUMN "publication_eligible" BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE "base_staging_batches"
    ADD COLUMN "eligibility_reviewed_by" TEXT;

ALTER TABLE "base_staging_batches"
    ADD COLUMN "eligibility_reviewed_at" TIMESTAMP(3);

-- Coerência: só pode haver revisor/data se (e só se) o lote estiver marcado elegível,
-- e vice-versa. Evita um lote "elegível" sem ninguém identificável por trás da decisão.
ALTER TABLE "base_staging_batches"
    ADD CONSTRAINT "base_staging_batches_eligibility_consistency"
    CHECK (
        (publication_eligible = false AND eligibility_reviewed_by IS NULL AND eligibility_reviewed_at IS NULL)
        OR
        (publication_eligible = true AND eligibility_reviewed_by IS NOT NULL AND eligibility_reviewed_at IS NOT NULL)
    );

-- O trigger append-only original de base_staging_batches (reject_base_staging_mutation,
-- partilhado com base_contract_snapshots e base_contract_party_snapshots) bloqueava
-- QUALQUER UPDATE. Isso entra em conflito com a decisão de elegibilidade, que é uma
-- anotação editorial posterior, distinta dos dados recolhidos.
--
-- Correção: substituir SÓ o trigger de base_staging_batches por uma versão que continua
-- a proibir DELETE sempre, e a proibir UPDATE a qualquer coluna que não seja uma das três
-- de elegibilidade. base_contract_snapshots e base_contract_party_snapshots continuam
-- exatamente como estavam — imutáveis sem exceção, sem tocar na função partilhada.

DROP TRIGGER "base_staging_batches_append_only" ON "base_staging_batches";

CREATE FUNCTION "reject_base_staging_batch_mutation_except_eligibility"()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'base_staging_batches é staging append-only; DELETE é proibido';
    END IF;

    IF OLD.id IS DISTINCT FROM NEW.id
        OR OLD.source_document_id IS DISTINCT FROM NEW.source_document_id
        OR OLD.sync_run_id IS DISTINCT FROM NEW.sync_run_id
        OR OLD.resource_year IS DISTINCT FROM NEW.resource_year
        OR OLD.resource_title IS DISTINCT FROM NEW.resource_title
        OR OLD.resource_format IS DISTINCT FROM NEW.resource_format
        OR OLD.parser_version IS DISTINCT FROM NEW.parser_version
        OR OLD.normalised_sha256 IS DISTINCT FROM NEW.normalised_sha256
        OR OLD.identifier_digests_stored IS DISTINCT FROM NEW.identifier_digests_stored
        OR OLD.contract_count IS DISTINCT FROM NEW.contract_count
        OR OLD.party_count IS DISTINCT FROM NEW.party_count
        OR OLD.collected_at IS DISTINCT FROM NEW.collected_at
        OR OLD.created_at IS DISTINCT FROM NEW.created_at
    THEN
        RAISE EXCEPTION
            'base_staging_batches só permite UPDATE às colunas de elegibilidade de publicação; os dados recolhidos são append-only';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "base_staging_batches_append_only_except_eligibility"
BEFORE UPDATE OR DELETE ON "base_staging_batches"
FOR EACH ROW EXECUTE FUNCTION "reject_base_staging_batch_mutation_except_eligibility"();
