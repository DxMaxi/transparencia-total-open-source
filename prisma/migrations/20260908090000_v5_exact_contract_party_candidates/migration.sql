-- V5.54: uma igualdade exata cria só um candidato privado PENDING_REVIEW.
-- O identificador protegido permanece exclusivamente nas duas tabelas de origem.

DO $$
BEGIN
    LOCK TABLE "public_contracts", "organisations", "public_contract_parties",
      "contract_match_reviews", "interest_relationships", "interest_entities"
      IN ACCESS EXCLUSIVE MODE;
    IF EXISTS (
      SELECT 1 FROM "public_contracts" contract
      WHERE contract."current_publication_snapshot_id" IS NOT NULL
        AND (
          EXISTS (SELECT 1 FROM "public_contract_parties" party
                  WHERE party."public_contract_id" = contract."id")
          OR EXISTS (SELECT 1 FROM "contract_match_reviews" review
                     WHERE review."public_contract_id" = contract."id")
          OR EXISTS (SELECT 1 FROM "interest_relationships" relationship
                     WHERE relationship."public_contract_id" = contract."id")
        )
    ) OR EXISTS (
      SELECT 1 FROM "interest_entities" entity
      JOIN "organisations" organisation ON organisation."id" = entity."organisation_id"
      WHERE organisation."id" ~ '^base_public_org_[0-9a-f]{32}$'
    ) THEN
      RAISE EXCEPTION
        'a V5.54 exige zero materialização prévia; não converter, apagar ou legitimar linhas';
    END IF;
END $$;

CREATE TABLE "base_contract_organisation_match_candidates" (
    "id" TEXT NOT NULL,
    "public_contract_id" TEXT NOT NULL,
    "contract_publication_snapshot_id" TEXT NOT NULL,
    "contract_party_snapshot_id" TEXT NOT NULL,
    "organisation_id" TEXT NOT NULL,
    "organisation_publication_snapshot_id" TEXT NOT NULL,
    "organisation_identity_observation_id" TEXT NOT NULL,
    "contract_source_document_id" TEXT NOT NULL,
    "organisation_source_document_id" TEXT NOT NULL,
    "method" "MatchMethod" NOT NULL DEFAULT 'EXACT_PROTECTED_IDENTIFIER',
    "decision" "MatchDecision" NOT NULL DEFAULT 'PENDING_REVIEW',
    "contract_source_record_sha256" CHAR(64) NOT NULL,
    "organisation_source_record_sha256" CHAR(64) NOT NULL,
    "candidate_proof_sha256" CHAR(64) NOT NULL,
    "rationale" TEXT NOT NULL,
    "created_by_id" TEXT NOT NULL,
    "created_by_alias" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "base_contract_organisation_match_candidates_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "base_contract_org_candidate_id_check"
      CHECK ("id" ~ '^base_contract_org_candidate_[0-9a-f]{32}$'),
    CONSTRAINT "base_contract_org_candidate_contract_id_check"
      CHECK ("public_contract_id" ~ '^base_contract_[0-9a-f]{64}$'),
    CONSTRAINT "base_contract_org_candidate_organisation_id_check"
      CHECK ("organisation_id" ~ '^base_public_org_[0-9a-f]{32}$'),
    CONSTRAINT "base_contract_org_candidate_method_check"
      CHECK ("method"::text = 'EXACT_PROTECTED_IDENTIFIER'),
    CONSTRAINT "base_contract_org_candidate_decision_check"
      CHECK ("decision"::text = 'PENDING_REVIEW'),
    CONSTRAINT "base_contract_org_candidate_sources_distinct_check"
      CHECK ("contract_source_document_id" <> "organisation_source_document_id"),
    CONSTRAINT "base_contract_org_candidate_contract_record_hash_check"
      CHECK ("contract_source_record_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_contract_org_candidate_org_record_hash_check"
      CHECK ("organisation_source_record_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_contract_org_candidate_proof_hash_check"
      CHECK ("candidate_proof_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "base_contract_org_candidate_rationale_check"
      CHECK (length(btrim("rationale")) BETWEEN 20 AND 1000
             AND base_organisation_identity_safe_text("rationale")),
    CONSTRAINT "base_contract_org_candidate_alias_check"
      CHECK (length(btrim("created_by_alias")) BETWEEN 3 AND 80
             AND base_organisation_identity_safe_text("created_by_alias")),
    CONSTRAINT "base_contract_org_candidate_contract_fk"
      FOREIGN KEY ("public_contract_id") REFERENCES "public_contracts"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_contract_publication_fk"
      FOREIGN KEY ("contract_publication_snapshot_id")
      REFERENCES "base_public_contract_publication_snapshots"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_party_fk"
      FOREIGN KEY ("contract_party_snapshot_id")
      REFERENCES "base_contract_party_snapshots"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_organisation_fk"
      FOREIGN KEY ("organisation_id") REFERENCES "organisations"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_organisation_publication_fk"
      FOREIGN KEY ("organisation_publication_snapshot_id")
      REFERENCES "base_public_organisation_publication_snapshots"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_identity_observation_fk"
      FOREIGN KEY ("organisation_identity_observation_id")
      REFERENCES "base_organisation_identity_observations"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_contract_source_fk"
      FOREIGN KEY ("contract_source_document_id")
      REFERENCES "source_documents"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_organisation_source_fk"
      FOREIGN KEY ("organisation_source_document_id")
      REFERENCES "source_documents"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "base_contract_org_candidate_staff_fk"
      FOREIGN KEY ("created_by_id") REFERENCES "staff_profiles"("id")
      ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "base_contract_org_candidate_exact_pair_key"
  ON "base_contract_organisation_match_candidates"
  ("contract_publication_snapshot_id", "contract_party_snapshot_id",
   "organisation_publication_snapshot_id");
CREATE UNIQUE INDEX "base_contract_org_candidate_proof_key"
  ON "base_contract_organisation_match_candidates"("candidate_proof_sha256");
CREATE INDEX "base_contract_org_candidate_contract_idx"
  ON "base_contract_organisation_match_candidates"("public_contract_id", "created_at");
CREATE INDEX "base_contract_org_candidate_party_idx"
  ON "base_contract_organisation_match_candidates"("contract_party_snapshot_id");
CREATE INDEX "base_contract_org_candidate_organisation_idx"
  ON "base_contract_organisation_match_candidates"("organisation_id", "created_at");
CREATE INDEX "base_contract_org_candidate_org_publication_idx"
  ON "base_contract_organisation_match_candidates"("organisation_publication_snapshot_id");
CREATE INDEX "base_contract_org_candidate_observation_idx"
  ON "base_contract_organisation_match_candidates"("organisation_identity_observation_id");
CREATE INDEX "base_contract_org_candidate_contract_source_idx"
  ON "base_contract_organisation_match_candidates"("contract_source_document_id");
CREATE INDEX "base_contract_org_candidate_org_source_idx"
  ON "base_contract_organisation_match_candidates"("organisation_source_document_id");
CREATE INDEX "base_contract_org_candidate_staff_idx"
  ON "base_contract_organisation_match_candidates"("created_by_id");
CREATE INDEX "base_contract_org_candidate_queue_idx"
  ON "base_contract_organisation_match_candidates"("decision", "created_at");

CREATE FUNCTION "validate_base_contract_organisation_match_candidate_insert"()
RETURNS TRIGGER AS $$
DECLARE
    protected_digest TEXT;
    exact_active_organisations INTEGER;
    expected_proof TEXT;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'a criação do candidato exige transação READ COMMITTED curta';
    END IF;

    PERFORM pg_advisory_xact_lock(
      hashtextextended(
        'base-contract-organisation-candidate:' || NEW."contract_party_snapshot_id"
        || ':' || NEW."organisation_id",
        0
      )
    );

    SELECT party."protected_identifier_digest"
      INTO protected_digest
    FROM "base_contract_party_snapshots" party
    WHERE party."id" = NEW."contract_party_snapshot_id";

    IF protected_digest IS NULL OR protected_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'a parte contratual não possui identificador protegido exato';
    END IF;

    IF NEW."method"::text <> 'EXACT_PROTECTED_IDENTIFIER'
       OR NEW."decision"::text <> 'PENDING_REVIEW' THEN
        RAISE EXCEPTION 'o candidato nasce exclusivamente por igualdade exata e PENDING_REVIEW';
    END IF;

    -- Usa a mesma fechadura da publicação organizacional V5.53. Tem de ser
    -- adquirida antes da linha da organização para não inverter essa ordem e
    -- provocar deadlock com uma publicação ou republicação concorrente.
    PERFORM pg_advisory_xact_lock(
      hashtextextended('base-organisation-publication:' || protected_digest, 0)
    );

    -- Ordem fixa: identidade, contrato, organização. As retiradas concorrentes
    -- aguardam o COMMIT e o candidato nunca observa dois estados da projeção.
    PERFORM 1 FROM "public_contracts"
      WHERE "id" = NEW."public_contract_id" FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'contrato público candidato não encontrado';
    END IF;
    PERFORM 1 FROM "organisations"
      WHERE "id" = NEW."organisation_id" FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'organização pública candidata não encontrada';
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM "public_contracts" contract
      JOIN "base_public_contract_publication_snapshots" contract_publication
        ON contract_publication."id" = contract."current_publication_snapshot_id"
       AND contract_publication."public_contract_id" = contract."id"
      JOIN "base_contract_snapshots" contract_snapshot
        ON contract_snapshot."id" = contract_publication."contract_snapshot_id"
      JOIN "base_staging_batches" contract_batch
        ON contract_batch."id" = contract_snapshot."batch_id"
       AND contract_batch."source_document_id" = contract_publication."source_document_id"
      JOIN "base_contract_party_snapshots" party
        ON party."contract_snapshot_id" = contract_snapshot."id"
       AND party."id" = NEW."contract_party_snapshot_id"
      JOIN "source_documents" contract_source
        ON contract_source."id" = contract_publication."source_document_id"
      JOIN "source_archive_attestations" contract_archive
        ON contract_archive."source_document_id" = contract_source."id"
       AND contract_archive."content_sha256" = contract_source."content_sha256"
       AND contract_archive."retrieval_url" = contract_source."url"
       AND contract_archive."retrieved_at" = contract_source."retrieved_at"
      JOIN "organisations" organisation
        ON organisation."id" = NEW."organisation_id"
      JOIN "base_public_organisation_publication_snapshots" organisation_publication
        ON organisation_publication."id" = organisation."current_publication_snapshot_id"
       AND organisation_publication."organisation_id" = organisation."id"
      JOIN "base_organisation_identity_observations" identity
        ON identity."id" = organisation_publication."identity_observation_id"
       AND identity."source_document_id" = organisation_publication."source_document_id"
      JOIN "source_documents" organisation_source
        ON organisation_source."id" = organisation_publication."source_document_id"
      JOIN "source_archive_attestations" organisation_archive
        ON organisation_archive."source_document_id" = organisation_source."id"
       AND organisation_archive."content_sha256" = organisation_source."content_sha256"
       AND organisation_archive."retrieval_url" = organisation_source."url"
       AND organisation_archive."retrieved_at" = organisation_source."retrieved_at"
      WHERE contract."id" = NEW."public_contract_id"
        AND contract."publication_status"::text = 'PUBLISHED'
        AND contract."verification_status"::text = 'VERIFIED'
        AND contract_publication."id" = NEW."contract_publication_snapshot_id"
        AND contract_publication."source_document_id" = NEW."contract_source_document_id"
        AND contract_publication."source_record_sha256"
              = NEW."contract_source_record_sha256"
        AND contract_source."publisher"::text = 'BASE_GOV'
        AND contract_source."kind"::text = 'OPEN_DATASET'
        AND contract_source."url" ~ '^https://'
        AND organisation."publication_status"::text = 'PUBLISHED'
        AND organisation."verification_status"::text = 'VERIFIED'
        AND organisation_publication."id"
              = NEW."organisation_publication_snapshot_id"
        AND organisation_publication."identity_observation_id"
              = NEW."organisation_identity_observation_id"
        AND organisation_publication."source_document_id"
              = NEW."organisation_source_document_id"
        AND organisation_publication."source_record_sha256"
              = NEW."organisation_source_record_sha256"
        AND organisation_source."publisher"::text = 'JUSTICE_REGISTRY'
        AND organisation_source."kind"::text = 'ORGANISATION_REGISTRY'
        AND organisation_source."url" ~* '^https://publicacoes\.mj\.pt/DetalhePublicacao\.aspx$'
        AND organisation_source."id" <> contract_source."id"
        AND identity."identifier_scheme" = 'PORTUGUESE_FISCAL_IDENTIFIER'
        AND identity."identity_scope" = 'ORGANISATION_IDENTITY_ONLY'
        AND identity."link_status" = 'UNLINKED_PRIVATE'
        AND identity."publication_eligible" = FALSE
        AND identity."protected_identifier_digest" = party."protected_identifier_digest"
    ) THEN
        RAISE EXCEPTION 'as duas publicações, fontes, arquivos ou identidades deixaram de coincidir';
    END IF;

    SELECT COUNT(DISTINCT organisation."id")
      INTO exact_active_organisations
    FROM "organisations" organisation
    JOIN "base_public_organisation_publication_snapshots" publication
      ON publication."id" = organisation."current_publication_snapshot_id"
     AND publication."organisation_id" = organisation."id"
    JOIN "base_organisation_identity_observations" identity
      ON identity."id" = publication."identity_observation_id"
    JOIN "source_documents" source ON source."id" = publication."source_document_id"
    WHERE organisation."publication_status"::text = 'PUBLISHED'
      AND organisation."verification_status"::text = 'VERIFIED'
      AND source."publisher"::text = 'JUSTICE_REGISTRY'
      AND source."kind"::text = 'ORGANISATION_REGISTRY'
      AND identity."protected_identifier_digest" = protected_digest;

    IF exact_active_organisations <> 1 THEN
        RAISE EXCEPTION 'o identificador protegido não corresponde a uma única organização ativa';
    END IF;

    IF EXISTS (
         SELECT 1 FROM "public_contract_parties"
         WHERE "public_contract_id" = NEW."public_contract_id"
       ) OR EXISTS (
         SELECT 1 FROM "contract_match_reviews"
         WHERE "public_contract_id" = NEW."public_contract_id"
       ) OR EXISTS (
         SELECT 1 FROM "interest_relationships"
         WHERE "public_contract_id" = NEW."public_contract_id"
       ) OR EXISTS (
         SELECT 1 FROM "interest_entities"
         WHERE "organisation_id" = NEW."organisation_id"
       ) THEN
        RAISE EXCEPTION 'a V5.54 não admite materialização pública ou no grafo';
    END IF;

    PERFORM 1 FROM "staff_profiles" staff
      WHERE staff."id" = NEW."created_by_id"
        AND staff."active" = TRUE
        AND staff."public_alias" = NEW."created_by_alias"
      FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'o candidato exige um perfil editorial ativo e coerente';
    END IF;


    -- Recalcula no PostgreSQL o mesmo objeto canónico de campos escalares.
    SELECT encode(sha256(convert_to('{' || string_agg(
      to_jsonb(entry.key)::text || ':' || entry.value::text, ',' ORDER BY entry.key COLLATE "C"
    ) || '}', 'UTF8')), 'hex') INTO expected_proof
    FROM "base_public_contract_publication_snapshots" cp
    JOIN "source_documents" cs ON cs.id = cp.source_document_id
    JOIN LATERAL (
      SELECT attestation_sha256 FROM source_archive_attestations
      WHERE source_document_id=cs.id AND content_sha256=cs.content_sha256
        AND retrieval_url=cs.url AND retrieved_at=cs.retrieved_at
      ORDER BY archived_at DESC, id DESC LIMIT 1
    ) ca ON TRUE
    JOIN "base_public_organisation_publication_snapshots" op
      ON op.id = NEW.organisation_publication_snapshot_id
    JOIN "source_documents" os ON os.id = op.source_document_id
    JOIN LATERAL (
      SELECT attestation_sha256 FROM source_archive_attestations
      WHERE source_document_id=os.id AND content_sha256=os.content_sha256
        AND retrieval_url=os.url AND retrieved_at=os.retrieved_at
      ORDER BY archived_at DESC, id DESC LIMIT 1
    ) oa ON TRUE
    CROSS JOIN LATERAL jsonb_each(jsonb_build_object(
        'schema_version', 'v5.54-base-contract-organisation-match-candidate/v1',
        'public_contract_id', NEW."public_contract_id",
        'contract_publication_snapshot_id', NEW."contract_publication_snapshot_id",
        'contract_party_snapshot_id', NEW."contract_party_snapshot_id",
        'organisation_id', NEW."organisation_id",
        'organisation_publication_snapshot_id', NEW."organisation_publication_snapshot_id",
        'organisation_identity_observation_id', NEW."organisation_identity_observation_id",
        'contract_source_document_id', NEW."contract_source_document_id",
        'organisation_source_document_id', NEW."organisation_source_document_id",
        'contract_source_record_sha256', NEW."contract_source_record_sha256",
        'organisation_source_record_sha256', NEW."organisation_source_record_sha256",
        'contract_source_sha256', cs.content_sha256,
        'organisation_source_sha256', os.content_sha256,
        'contract_archive_attestation_sha256', ca.attestation_sha256,
        'organisation_archive_attestation_sha256', oa.attestation_sha256,
        'contract_publication_proof_sha256', cp.publication_proof_sha256,
        'organisation_publication_proof_sha256', op.publication_proof_sha256,
        'method', 'EXACT_PROTECTED_IDENTIFIER',
        'decision', 'PENDING_REVIEW',
        'two_active_publications', TRUE,
        'independent_official_sources', TRUE,
        'protected_identifier_compared_privately', TRUE,
        'protected_identifier_exposed', FALSE,
        'name_matching_used', FALSE,
        'fuzzy_matching_used', FALSE,
        'public_party_created', FALSE,
        'match_review_created', FALSE,
        'public_relationship_created', FALSE
    )) entry
    WHERE cp.id = NEW.contract_publication_snapshot_id;
    IF expected_proof IS NULL OR expected_proof <> NEW.candidate_proof_sha256 THEN
      RAISE EXCEPTION 'a prova canónica do candidato deixou de coincidir';
    END IF;

    NEW."created_at" := (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "base_contract_org_candidates_validate_insert"
BEFORE INSERT ON "base_contract_organisation_match_candidates"
FOR EACH ROW EXECUTE FUNCTION "validate_base_contract_organisation_match_candidate_insert"();

CREATE FUNCTION "reject_base_contract_organisation_match_candidate_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'um candidato V5.54 é privado e append-only; crie uma decisão posterior';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "base_contract_org_candidates_append_only_rows"
BEFORE UPDATE OR DELETE ON "base_contract_organisation_match_candidates"
FOR EACH ROW EXECUTE FUNCTION "reject_base_contract_organisation_match_candidate_mutation"();
CREATE TRIGGER "base_contract_org_candidates_append_only_truncate"
BEFORE TRUNCATE ON "base_contract_organisation_match_candidates"
FOR EACH STATEMENT EXECUTE FUNCTION "reject_base_contract_organisation_match_candidate_mutation"();

-- Congela toda a âncora semântica BASE usada por uma fotografia pública.
-- Uma correção tem de criar SourceDocument e fotografia novos.
CREATE FUNCTION "protect_v554_base_contract_source"()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
      SELECT 1 FROM "base_public_contract_publication_snapshots" publication
      WHERE publication."source_document_id" = OLD."id"
    ) AND (
      NEW."publisher" IS DISTINCT FROM OLD."publisher"
      OR NEW."kind" IS DISTINCT FROM OLD."kind"
      OR NEW."title" IS DISTINCT FROM OLD."title"
      OR NEW."official_identifier" IS DISTINCT FROM OLD."official_identifier"
      OR NEW."url" IS DISTINCT FROM OLD."url"
      OR NEW."retrieved_at" IS DISTINCT FROM OLD."retrieved_at"
      OR NEW."published_at" IS DISTINCT FROM OLD."published_at"
      OR NEW."content_sha256" IS DISTINCT FROM OLD."content_sha256"
      OR NEW."mime_type" IS DISTINCT FROM OLD."mime_type"
      OR NEW."raw_storage_key" IS DISTINCT FROM OLD."raw_storage_key"
      OR NEW."parser_version" IS DISTINCT FROM OLD."parser_version"
    ) THEN
      RAISE EXCEPTION 'uma fonte BASE publicada é imutável; crie nova fonte e fotografia';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "source_documents_protect_v554_base_contract_source"
BEFORE UPDATE ON "source_documents"
FOR EACH ROW EXECUTE FUNCTION "protect_v554_base_contract_source"();

-- As tabelas legadas e do grafo continuam fechadas até uma porta posterior.
CREATE FUNCTION "reject_v554_contract_graph_materialisation"()
RETURNS TRIGGER AS $$
DECLARE
    old_contract_is_v551 BOOLEAN := FALSE;
    new_contract_is_v551 BOOLEAN := FALSE;
BEGIN
    IF TG_OP <> 'INSERT' AND OLD."public_contract_id" IS NOT NULL THEN
      SELECT EXISTS (
        SELECT 1 FROM "base_public_contract_publication_snapshots"
        WHERE "public_contract_id" = OLD."public_contract_id"
      ) INTO old_contract_is_v551;
    END IF;

    IF TG_OP <> 'DELETE' AND NEW."public_contract_id" IS NOT NULL THEN
      SELECT EXISTS (
        SELECT 1 FROM "base_public_contract_publication_snapshots"
        WHERE "public_contract_id" = NEW."public_contract_id"
      ) INTO new_contract_is_v551;
    END IF;

    IF old_contract_is_v551 OR new_contract_is_v551 THEN
      RAISE EXCEPTION 'a V5.54 cria apenas candidato privado; a materialização exige outra porta';
    END IF;
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE TRIGGER "contract_match_reviews_block_v554_materialisation"
BEFORE INSERT OR UPDATE OR DELETE ON "contract_match_reviews"
FOR EACH ROW EXECUTE FUNCTION "reject_v554_contract_graph_materialisation"();
CREATE TRIGGER "interest_relationships_block_v554_materialisation"
BEFORE INSERT OR UPDATE OR DELETE ON "interest_relationships"
FOR EACH ROW EXECUTE FUNCTION "reject_v554_contract_graph_materialisation"();

CREATE FUNCTION "reject_v554_graph_truncate"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'as partes, correspondências e relações históricas não admitem TRUNCATE';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "public_contract_parties_no_truncate"
BEFORE TRUNCATE ON "public_contract_parties"
FOR EACH STATEMENT EXECUTE FUNCTION "reject_v554_graph_truncate"();
CREATE TRIGGER "contract_match_reviews_no_truncate"
BEFORE TRUNCATE ON "contract_match_reviews"
FOR EACH STATEMENT EXECUTE FUNCTION "reject_v554_graph_truncate"();
CREATE TRIGGER "interest_relationships_no_truncate"
BEFORE TRUNCATE ON "interest_relationships"
FOR EACH STATEMENT EXECUTE FUNCTION "reject_v554_graph_truncate"();

CREATE FUNCTION "reject_v554_source_archive_truncate"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'as atestações do arquivo oficial são append-only e não admitem TRUNCATE';
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;

CREATE TRIGGER "source_archive_attestations_no_truncate"
BEFORE TRUNCATE ON "source_archive_attestations"
FOR EACH STATEMENT EXECUTE FUNCTION "reject_v554_source_archive_truncate"();

ALTER TABLE "base_contract_organisation_match_candidates" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE "base_contract_organisation_match_candidates" FROM PUBLIC;

DO $$
DECLARE
    role_name TEXT;
    function_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['PUBLIC', 'anon', 'authenticated'] LOOP
      IF role_name = 'PUBLIC' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
        EXECUTE format(
          'REVOKE ALL ON TABLE public.base_contract_organisation_match_candidates FROM %s',
          CASE WHEN role_name = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(role_name) END
        );
        FOREACH function_name IN ARRAY ARRAY[
          'validate_base_contract_organisation_match_candidate_insert',
          'reject_base_contract_organisation_match_candidate_mutation',
          'protect_v554_base_contract_source',
          'reject_v554_contract_graph_materialisation',
          'reject_v554_graph_truncate',
          'reject_v554_source_archive_truncate'
        ] LOOP
          EXECUTE format(
            'REVOKE ALL ON FUNCTION public.%I() FROM %s',
            function_name,
            CASE WHEN role_name = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(role_name) END
          );
        END LOOP;
      END IF;
    END LOOP;
END $$;
