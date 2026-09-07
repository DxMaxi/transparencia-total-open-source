-- V5.53: publicação própria, sem tornar pública a identidade privada V5.52.
ALTER TYPE "EditorialCaseKind" ADD VALUE IF NOT EXISTS 'ORGANISATION_PUBLICATION';

DO $$ BEGIN
  LOCK TABLE organisations, interest_entities IN ACCESS EXCLUSIVE MODE;
  IF EXISTS (SELECT 1 FROM organisations WHERE verification_status::text = 'VERIFIED'
             OR id ~ '^base_public_org_[0-9a-f]{32}$')
     OR EXISTS (SELECT 1 FROM editorial_publication_events WHERE target_type = 'BASE_PUBLIC_ORGANISATION') THEN
    RAISE EXCEPTION 'organizações legadas exigem avaliação própria; não converter nem apagar';
  END IF;
END $$;

ALTER TABLE organisations ADD COLUMN publication_status "PublicationStatus" NOT NULL DEFAULT 'DRAFT',
  ADD COLUMN current_publication_snapshot_id TEXT;

CREATE TABLE base_public_organisation_publication_snapshots (
  id TEXT PRIMARY KEY,
  organisation_id TEXT NOT NULL CONSTRAINT base_org_publication_organisation_fk REFERENCES organisations(id) ON DELETE RESTRICT,
  identity_observation_id TEXT NOT NULL CONSTRAINT base_org_publication_observation_fk REFERENCES base_organisation_identity_observations(id) ON DELETE RESTRICT,
  identity_case_id TEXT NOT NULL CONSTRAINT base_org_publication_identity_case_fk REFERENCES editorial_cases(id) ON DELETE RESTRICT,
  identity_version_id TEXT NOT NULL CONSTRAINT base_org_publication_identity_version_fk REFERENCES editorial_versions(id) ON DELETE RESTRICT,
  identity_decision_id TEXT NOT NULL CONSTRAINT base_org_publication_identity_decision_fk REFERENCES editorial_decisions(id) ON DELETE RESTRICT,
  editorial_case_id TEXT NOT NULL CONSTRAINT base_org_publication_editorial_case_fk REFERENCES editorial_cases(id) ON DELETE RESTRICT,
  editorial_version_id TEXT NOT NULL CONSTRAINT base_org_publication_editorial_version_fk REFERENCES editorial_versions(id) ON DELETE RESTRICT,
  source_document_id TEXT NOT NULL CONSTRAINT base_org_publication_source_fk REFERENCES source_documents(id) ON DELETE RESTRICT,
  legal_name TEXT NOT NULL CHECK (length(btrim(legal_name)) BETWEEN 1 AND 300 AND base_organisation_identity_safe_text(legal_name)),
  kind "InterestEntityKind" NOT NULL CHECK (kind::text IN ('PUBLIC_BODY','COMPANY','NON_PROFIT','EUROPEAN_BODY','OTHER')),
  registry_record_id TEXT NOT NULL CHECK (registry_record_id ~ '^[A-Za-z][A-Za-z0-9._:/-]{2,199}$' AND base_organisation_identity_safe_text(registry_record_id)),
  official_url TEXT NOT NULL CHECK (official_url ~* '^https://publicacoes\.mj\.pt/DetalhePublicacao\.aspx$' AND official_url LIKE 'https://publicacoes.mj.pt/%' AND length(official_url) = octet_length(official_url)),
  source_record_sha256 CHAR(64) NOT NULL CHECK (source_record_sha256 ~ '^[0-9a-f]{64}$'),
  publication_proof_sha256 CHAR(64) NOT NULL CHECK (publication_proof_sha256 ~ '^[0-9a-f]{64}$'),
  public_record_sha256 CHAR(64) NOT NULL CHECK (public_record_sha256 ~ '^[0-9a-f]{64}$'),
  created_by_alias TEXT NOT NULL CHECK (length(btrim(created_by_alias)) BETWEEN 3 AND 80 AND base_organisation_identity_safe_text(created_by_alias)),
  created_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (organisation_id ~ '^base_public_org_[0-9a-f]{32}$')
);
CREATE UNIQUE INDEX base_org_publication_identity_version_key ON base_public_organisation_publication_snapshots(identity_version_id);
CREATE UNIQUE INDEX base_org_publication_editorial_version_key ON base_public_organisation_publication_snapshots(editorial_version_id);
CREATE UNIQUE INDEX base_org_publication_proof_key ON base_public_organisation_publication_snapshots(publication_proof_sha256);
CREATE UNIQUE INDEX base_org_publication_record_key ON base_public_organisation_publication_snapshots(public_record_sha256);
CREATE INDEX base_public_org_snapshot_org_idx ON base_public_organisation_publication_snapshots(organisation_id, created_at);
CREATE INDEX base_public_org_snapshot_observation_idx ON base_public_organisation_publication_snapshots(identity_observation_id);
CREATE INDEX base_public_org_snapshot_case_idx ON base_public_organisation_publication_snapshots(editorial_case_id);
CREATE INDEX base_public_org_snapshot_source_idx ON base_public_organisation_publication_snapshots(source_document_id);
ALTER TABLE organisations ADD CONSTRAINT organisations_publication_snapshot_fk
  FOREIGN KEY (current_publication_snapshot_id) REFERENCES base_public_organisation_publication_snapshots(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX organisations_current_publication_snapshot_key ON organisations(current_publication_snapshot_id);
-- Dados legados não recebem publicação V5.53: a nova consulta exige o namespace e fotografia.
ALTER TABLE organisations ADD CONSTRAINT organisations_publication_state_check CHECK (
  (current_publication_snapshot_id IS NULL AND publication_status::text = 'DRAFT') OR
  (current_publication_snapshot_id IS NOT NULL AND publication_status::text IN ('PUBLISHED','WITHDRAWN')
   AND verification_status::text = 'VERIFIED' AND source_id IS NULL AND id ~ '^base_public_org_[0-9a-f]{32}$')
);

CREATE OR REPLACE FUNCTION validate_editorial_case_insert() RETURNS TRIGGER AS $$
DECLARE staff_alias TEXT;
BEGIN
  IF NEW.current_version_id IS NOT NULL OR NEW.revision <> 0 OR NEW.current_state <> 'PENDING'::"EditorialState" THEN
    RAISE EXCEPTION 'um processo editorial nasce privado, PENDING, sem versão projetada e na revisão zero';
  END IF;
  IF NEW.kind::text NOT IN ('ORGANISATION_IDENTITY','ORGANISATION_PUBLICATION') AND EXISTS (
    SELECT 1 FROM source_documents WHERE id = NEW.source_document_id AND publisher::text = 'JUSTICE_REGISTRY'
  ) THEN RAISE EXCEPTION 'a prova IRN exige circuito organizacional específico'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM source_documents source JOIN source_archive_attestations archive
      ON archive.source_document_id = source.id AND archive.content_sha256 = source.content_sha256
      AND archive.retrieval_url = source.url AND archive.retrieved_at = source.retrieved_at
    WHERE source.id = NEW.source_document_id AND source.url ~ '^https://'
      AND source.publisher::text IN ('PARLIAMENT','DRE','TRANSPARENCY_ENTITY','BASE_GOV',
        'COURT_OF_AUDIT','EUROPEAN_PARLIAMENT','PUBLIC_PROSECUTOR','COURT','SNS','MUNICIPALITY','OTHER_OFFICIAL','JUSTICE_REGISTRY')
      AND source.kind <> 'NEWS_ARTICLE'
  ) THEN RAISE EXCEPTION 'o processo editorial exige fonte oficial com URL, data, SHA-256 e arquivo atestado'; END IF;
  IF NEW.origin = 'HUMAN'::"EditorialOrigin" THEN
    IF NEW.created_by_id IS NULL THEN RAISE EXCEPTION 'uma proposta humana exige identidade staff'; END IF;
    SELECT public_alias INTO staff_alias FROM staff_profiles WHERE id = NEW.created_by_id AND active = TRUE;
    IF staff_alias IS NULL OR staff_alias <> NEW.created_by_alias THEN RAISE EXCEPTION 'identidade staff inativa ou alias do criador incoerente'; END IF;
  ELSIF NEW.created_by_id IS NOT NULL THEN RAISE EXCEPTION 'propostas de ingestão ou IA não podem fingir autoria humana'; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION validate_base_organisation_publication_case_insert() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.kind::text <> 'ORGANISATION_PUBLICATION' THEN RETURN NEW; END IF;
  IF NEW.origin::text <> 'INGESTION' OR NEW.created_by_id IS NOT NULL
    OR NEW.subject_type <> 'BASE_ORGANISATION_IDENTITY_VERSION'
    OR NOT base_organisation_identity_safe_text(NEW.created_by_alias)
    OR NOT EXISTS (
      SELECT 1 FROM editorial_cases ic JOIN editorial_versions iv ON iv.id = ic.current_version_id AND iv.case_id = ic.id
      JOIN editorial_decisions d ON d.case_id = ic.id AND d.version_id = iv.id AND d.case_revision = ic.revision
      JOIN base_organisation_identity_observations o ON o.id = ic.subject_id AND o.source_document_id = ic.source_document_id
      WHERE iv.id = NEW.subject_id AND ic.kind::text = 'ORGANISATION_IDENTITY'
        AND ic.subject_type = 'BASE_ORGANISATION_IDENTITY_OBSERVATION' AND ic.current_state::text = 'APPROVED'
        AND d.action::text = 'APPROVE' AND d.resulting_state::text = 'APPROVED' AND d.source_confirmed
        AND ic.source_document_id = NEW.source_document_id
    ) THEN RAISE EXCEPTION 'a proposta exige versão de identidade privada aprovada exata'; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;
CREATE TRIGGER editorial_cases_validate_organisation_publication BEFORE INSERT ON editorial_cases
  FOR EACH ROW EXECUTE FUNCTION validate_base_organisation_publication_case_insert();

CREATE FUNCTION validate_base_organisation_publication_version_insert() RETURNS TRIGGER AS $$
DECLARE expected JSONB; public_id TEXT; parent editorial_cases%ROWTYPE;
BEGIN
  SELECT * INTO parent FROM editorial_cases WHERE id = NEW.case_id;
  IF parent.kind::text <> 'ORGANISATION_PUBLICATION' THEN RETURN NEW; END IF;
  public_id := NEW.normalized_json #>> '{public_fields,id}';
  IF NEW.version_number <> 1 OR NEW.previous_version_id IS NOT NULL OR NEW.origin::text <> 'INGESTION'
    OR NEW.created_by_id IS NOT NULL OR public_id IS NULL OR public_id !~ '^base_public_org_[0-9a-f]{32}$'
    OR NOT base_organisation_identity_safe_text(NEW.created_by_alias) THEN
    RAISE EXCEPTION 'a publicação exige proposta própria imutável';
  END IF;
  IF jsonb_typeof(NEW.normalized_json->'source') <> 'object'
    OR jsonb_typeof(NEW.normalized_json->'archive') <> 'object'
    OR (SELECT count(*) FROM jsonb_object_keys(NEW.normalized_json->'source')) <> 7
    OR (SELECT count(*) FROM jsonb_object_keys(NEW.normalized_json->'archive')) <> 4 THEN
    RAISE EXCEPTION 'a fonte e o arquivo exigem a projeção mínima fechada';
  END IF;
  SELECT jsonb_build_object(
    'schema_version','v5.53-organisation-publication/v1',
    'identity',jsonb_build_object('case_id',ic.id,'version_id',iv.id,'decision_id',d.id,'observation_id',o.id),
    'public_fields',jsonb_build_object('id',public_id,'legal_name',o.legal_name,'kind',o.kind::text,
      'registry_record_id',o.registry_record_id,'official_url',s.url),
    'evidence',jsonb_build_object('source_record_sha256',o.source_record_sha256,'identity_proposal_sha256',iv.normalized_sha256),
    'source',iv.normalized_json->'source','archive',iv.normalized_json->'archive',
    'constraints',jsonb_build_object('identity_remains_private',true,'zero_graph',true)
  ) INTO expected
  FROM editorial_cases ic JOIN editorial_versions iv ON iv.id = ic.current_version_id AND iv.case_id = ic.id
  JOIN editorial_decisions d ON d.case_id = ic.id AND d.version_id = iv.id AND d.case_revision = ic.revision
  JOIN base_organisation_identity_observations o ON o.id = ic.subject_id AND o.source_document_id = ic.source_document_id
  JOIN source_documents s ON s.id = o.source_document_id
  WHERE iv.id = parent.subject_id AND ic.kind::text = 'ORGANISATION_IDENTITY'
    AND ic.current_state::text = 'APPROVED' AND d.action::text = 'APPROVE' AND d.source_confirmed
    AND s.id = parent.source_document_id;
  IF expected IS NULL OR NEW.normalized_json IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'a projeção pública não coincide com a identidade aprovada';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM source_documents source JOIN source_archive_attestations archive
      ON archive.source_document_id = source.id AND archive.content_sha256 = source.content_sha256
      AND archive.retrieval_url = source.url AND archive.retrieved_at = source.retrieved_at
    WHERE source.id = parent.source_document_id AND source.publisher::text = 'JUSTICE_REGISTRY'
      AND source.kind::text = 'ORGANISATION_REGISTRY'
      AND NEW.normalized_json #>> '{source,title}' = source.title
      AND NEW.normalized_json #>> '{source,publisher}' = 'IRN'
      AND NEW.normalized_json #>> '{source,official_identifier}' = source.official_identifier
      AND NEW.normalized_json #>> '{source,url}' = source.url
      AND (NEW.normalized_json #>> '{source,retrieved_at}')::timestamptz = source.retrieved_at AT TIME ZONE 'UTC'
      AND NEW.normalized_json #>> '{source,content_sha256}' = source.content_sha256
      AND (NEW.normalized_json->'source'->'mime_type' = to_jsonb(source.mime_type)
           OR (NEW.normalized_json->'source'->'mime_type' = 'null'::jsonb AND source.mime_type IS NULL))
      AND NEW.normalized_json #>> '{archive,storage_backend}' = archive.storage_backend
      AND (NEW.normalized_json #>> '{archive,byte_size}')::bigint = archive.byte_size
      AND (NEW.normalized_json #>> '{archive,archived_at}')::timestamptz = archive.archived_at AT TIME ZONE 'UTC'
      AND NEW.normalized_json #>> '{archive,attestation_sha256}' = archive.attestation_sha256
  ) THEN RAISE EXCEPTION 'os metadados da fonte e do arquivo não coincidem com a prova preservada'; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;
CREATE TRIGGER editorial_versions_validate_organisation_publication BEFORE INSERT ON editorial_versions
  FOR EACH ROW EXECUTE FUNCTION validate_base_organisation_publication_version_insert();

CREATE FUNCTION validate_base_public_organisation_snapshot_insert() RETURNS TRIGGER AS $$
DECLARE protected_digest TEXT; candidate RECORD;
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'a publicação organizacional exige READ COMMITTED';
  END IF;
  SELECT protected_identifier_digest INTO protected_digest FROM base_organisation_identity_observations WHERE id = NEW.identity_observation_id;
  IF protected_digest IS NULL THEN RAISE EXCEPTION 'observação privada inexistente'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('base-organisation-publication:' || protected_digest, 0));
  IF EXISTS (
    SELECT 1 FROM base_public_organisation_publication_snapshots snap
    JOIN base_organisation_identity_observations obs ON obs.id = snap.identity_observation_id
    WHERE (obs.protected_identifier_digest = protected_digest AND snap.organisation_id <> NEW.organisation_id)
       OR (snap.organisation_id = NEW.organisation_id AND obs.protected_identifier_digest <> protected_digest)
  ) THEN RAISE EXCEPTION 'a identidade e a organização têm de permanecer inequívocas'; END IF;
  SELECT o.legal_name,o.kind,o.registry_record_id,o.source_record_sha256,s.url,pv.normalized_json
  INTO candidate
  FROM base_organisation_identity_observations o JOIN source_documents s ON s.id = o.source_document_id
  JOIN editorial_cases ic ON ic.id = NEW.identity_case_id AND ic.subject_id = o.id
    AND ic.kind::text = 'ORGANISATION_IDENTITY' AND ic.current_state::text = 'APPROVED'
    AND ic.current_version_id = NEW.identity_version_id AND ic.source_document_id = s.id
  JOIN editorial_versions iv ON iv.id = NEW.identity_version_id AND iv.case_id = ic.id
  JOIN editorial_decisions d ON d.id = NEW.identity_decision_id AND d.case_id = ic.id AND d.version_id = iv.id
    AND d.case_revision = ic.revision AND d.action::text = 'APPROVE' AND d.source_confirmed
  JOIN editorial_cases pc ON pc.id = NEW.editorial_case_id AND pc.kind::text = 'ORGANISATION_PUBLICATION'
    AND pc.subject_type = 'BASE_ORGANISATION_IDENTITY_VERSION' AND pc.subject_id = iv.id
    AND pc.source_document_id = s.id AND pc.current_state::text = 'APPROVED' AND pc.current_version_id = NEW.editorial_version_id
  JOIN editorial_versions pv ON pv.id = pc.current_version_id AND pv.case_id = pc.id
  JOIN editorial_decisions pd ON pd.case_id = pc.id AND pd.version_id = pv.id AND pd.case_revision = pc.revision
    AND pd.action::text = 'APPROVE' AND pd.source_confirmed
  WHERE o.id = NEW.identity_observation_id AND s.id = NEW.source_document_id
    AND s.publisher::text = 'JUSTICE_REGISTRY' AND s.kind::text = 'ORGANISATION_REGISTRY'
    AND pv.normalized_json->'source' = iv.normalized_json->'source'
    AND pv.normalized_json->'archive' = iv.normalized_json->'archive'
    AND iv.normalized_json #>> '{source,content_sha256}' = s.content_sha256
    AND iv.normalized_json #>> '{source,url}' = s.url
    AND (iv.normalized_json #>> '{source,retrieved_at}')::timestamptz = s.retrieved_at AT TIME ZONE 'UTC'
    AND EXISTS (SELECT 1 FROM source_archive_attestations a WHERE a.source_document_id = s.id
      AND a.content_sha256 = s.content_sha256 AND a.retrieval_url = s.url AND a.retrieved_at = s.retrieved_at
      AND a.attestation_sha256 = pv.normalized_json #>> '{archive,attestation_sha256}')
  FOR UPDATE OF ic,pc FOR SHARE OF s;
  IF NOT FOUND OR NEW.legal_name IS DISTINCT FROM candidate.legal_name OR NEW.kind IS DISTINCT FROM candidate.kind
    OR NEW.registry_record_id IS DISTINCT FROM candidate.registry_record_id OR NEW.official_url IS DISTINCT FROM candidate.url
    OR NEW.source_record_sha256 IS DISTINCT FROM candidate.source_record_sha256
    OR candidate.normalized_json #>> '{public_fields,id}' IS DISTINCT FROM NEW.organisation_id
    OR candidate.normalized_json #>> '{identity,decision_id}' IS DISTINCT FROM NEW.identity_decision_id THEN
    RAISE EXCEPTION 'a fotografia não corresponde à aprovação e à prova exatas';
  END IF;
  PERFORM 1 FROM organisations WHERE id = NEW.organisation_id FOR UPDATE;
  IF EXISTS (SELECT 1 FROM organisations WHERE id = NEW.organisation_id AND publication_status::text NOT IN ('DRAFT','WITHDRAWN')) THEN
    RAISE EXCEPTION 'uma nova fotografia exige retirada prévia';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;
CREATE TRIGGER base_public_organisation_snapshot_validate BEFORE INSERT ON base_public_organisation_publication_snapshots
  FOR EACH ROW EXECUTE FUNCTION validate_base_public_organisation_snapshot_insert();

CREATE FUNCTION reject_base_public_organisation_snapshot_mutation() RETURNS TRIGGER AS $$
BEGIN RAISE EXCEPTION 'as fotografias organizacionais são imutáveis'; END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;
CREATE TRIGGER base_public_organisation_snapshot_immutable BEFORE UPDATE OR DELETE ON base_public_organisation_publication_snapshots
  FOR EACH ROW EXECUTE FUNCTION reject_base_public_organisation_snapshot_mutation();
CREATE TRIGGER base_public_organisation_snapshot_no_truncate BEFORE TRUNCATE ON base_public_organisation_publication_snapshots
  FOR EACH STATEMENT EXECUTE FUNCTION reject_base_public_organisation_snapshot_mutation();

CREATE FUNCTION validate_base_public_organisation_projection() RETURNS TRIGGER AS $$
DECLARE snap base_public_organisation_publication_snapshots%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.id ~ '^base_public_org_[0-9a-f]{32}$' THEN RAISE EXCEPTION 'a organização preserva o seu histórico'; END IF;
    RETURN OLD;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.id IS DISTINCT FROM NEW.id AND (OLD.id ~ '^base_public_org_[0-9a-f]{32}$' OR NEW.id ~ '^base_public_org_[0-9a-f]{32}$') THEN
      RAISE EXCEPTION 'o identificador público é estável';
    END IF;
    IF OLD.current_publication_snapshot_id IS NOT NULL AND (
      NEW.current_publication_snapshot_id IS NULL OR
      (OLD.current_publication_snapshot_id IS DISTINCT FROM NEW.current_publication_snapshot_id
       AND NOT (OLD.publication_status::text = 'WITHDRAWN' AND NEW.publication_status::text = 'PUBLISHED')) OR
      (OLD.publication_status::text = 'WITHDRAWN' AND NEW.publication_status::text = 'PUBLISHED'
       AND OLD.current_publication_snapshot_id = NEW.current_publication_snapshot_id)
    ) THEN RAISE EXCEPTION 'a correção exige retirada e nova fotografia'; END IF;
  END IF;
  IF NEW.current_publication_snapshot_id IS NOT NULL THEN
    SELECT * INTO snap FROM base_public_organisation_publication_snapshots WHERE id = NEW.current_publication_snapshot_id;
    IF NOT FOUND OR NEW.id IS DISTINCT FROM snap.organisation_id OR NEW.source_id IS NOT NULL
      OR NEW.legal_name IS DISTINCT FROM snap.legal_name OR NEW.normalised_name IS DISTINCT FROM snap.legal_name
      OR NEW.kind IS DISTINCT FROM snap.kind OR NEW.official_url IS DISTINCT FROM snap.official_url
      OR NEW.source_document_id IS DISTINCT FROM snap.source_document_id THEN
      RAISE EXCEPTION 'a projeção não coincide com a fotografia imutável';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;
CREATE TRIGGER organisations_validate_publication BEFORE INSERT OR UPDATE OR DELETE ON organisations
  FOR EACH ROW EXECUTE FUNCTION validate_base_public_organisation_projection();

CREATE FUNCTION reject_v553_organisation_graph_link() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.organisation_id ~ '^base_public_org_[0-9a-f]{32}$' THEN
    RAISE EXCEPTION 'publicar uma organização não autoriza ligações ao grafo';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;
CREATE TRIGGER interest_entities_block_v553_organisation BEFORE INSERT OR UPDATE ON interest_entities
  FOR EACH ROW EXECUTE FUNCTION reject_v553_organisation_graph_link();

CREATE FUNCTION validate_base_public_organisation_event() RETURNS TRIGGER AS $$
DECLARE organisation_case BOOLEAN;
BEGIN
  SELECT kind::text = 'ORGANISATION_PUBLICATION' INTO organisation_case FROM editorial_cases WHERE id = NEW.case_id;
  IF (organisation_case OR NEW.target_type = 'BASE_PUBLIC_ORGANISATION') AND (
    organisation_case IS DISTINCT FROM (NEW.target_type = 'BASE_PUBLIC_ORGANISATION') OR
    NOT EXISTS (SELECT 1 FROM base_public_organisation_publication_snapshots
      WHERE editorial_case_id = NEW.case_id AND editorial_version_id = NEW.version_id AND organisation_id = NEW.target_id) OR
    NOT base_organisation_identity_safe_text(NEW.rationale) OR NOT base_organisation_identity_safe_text(NEW.actor_alias)
  ) THEN RAISE EXCEPTION 'o evento exige o âmbito e a fotografia organizacionais exatos'; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;
CREATE TRIGGER editorial_publication_events_validate_organisation BEFORE INSERT ON editorial_publication_events
  FOR EACH ROW EXECUTE FUNCTION validate_base_public_organisation_event();

CREATE FUNCTION assert_v553_organisation_final_state(target TEXT) RETURNS VOID AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM organisations o JOIN base_public_organisation_publication_snapshots s ON s.id = o.current_publication_snapshot_id AND s.organisation_id = o.id
    JOIN editorial_cases c ON c.id = s.editorial_case_id AND c.kind::text = 'ORGANISATION_PUBLICATION'
      AND c.current_version_id = s.editorial_version_id AND c.current_state::text = o.publication_status::text
    JOIN editorial_decisions d ON d.case_id = c.id AND d.version_id = s.editorial_version_id AND d.case_revision = c.revision
      AND d.resulting_state = c.current_state AND d.action::text = CASE o.publication_status::text WHEN 'PUBLISHED' THEN 'PUBLISH' WHEN 'WITHDRAWN' THEN 'WITHDRAW' END
    JOIN editorial_publication_events e ON e.case_id = c.id AND e.version_id = s.editorial_version_id
      AND e.target_type = 'BASE_PUBLIC_ORGANISATION' AND e.target_id = o.id AND e.action::text = d.action::text
      AND e.actor_id = d.actor_id AND e.actor_alias = d.actor_alias
    WHERE o.id = target AND o.verification_status::text = 'VERIFIED'
      AND EXISTS (SELECT 1 FROM data_publication_reviews r WHERE r.entity_type = 'BASE_PUBLIC_ORGANISATION'
        AND r.entity_id = o.id AND r.source_document_id = s.source_document_id
        AND r.publishable = (o.publication_status::text = 'PUBLISHED') AND r.reviewed_by = e.actor_alias AND r.reviewed_at = e.created_at
        AND r.legal_basis::text = 'PUBLIC_INTEREST' AND r.sensitivity::text = 'PUBLIC_OFFICIAL')
      AND EXISTS (SELECT 1 FROM audit_events a WHERE a.entity_type = 'BASE_PUBLIC_ORGANISATION' AND a.entity_id = o.id
        AND a.actor_alias = e.actor_alias AND a.created_at = e.created_at
        AND a.action = o.publication_status::text AND a.after_json->'publishable' = to_jsonb(o.publication_status::text = 'PUBLISHED')
        AND a.after_json->>'publication_proof_sha256' = s.publication_proof_sha256 AND a.after_json->>'public_record_sha256' = s.public_record_sha256)
  ) THEN RAISE EXCEPTION 'a organização exige fotografia, decisão, evento, revisão e auditoria coerentes'; END IF;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;

CREATE FUNCTION check_v553_organisation_final_state() RETURNS TRIGGER AS $$
DECLARE target TEXT;
BEGIN
  IF TG_TABLE_NAME = 'organisations' THEN
    target := NEW.id;
    IF target !~ '^base_public_org_[0-9a-f]{32}$' THEN RETURN NULL; END IF;
  ELSIF TG_TABLE_NAME = 'base_public_organisation_publication_snapshots' THEN
    target := NEW.organisation_id;
    IF NOT EXISTS (SELECT 1 FROM organisations WHERE id = target AND current_publication_snapshot_id = NEW.id) THEN
      RAISE EXCEPTION 'a nova fotografia exige projeção atual correspondente';
    END IF;
  ELSE
    IF NEW.target_type <> 'BASE_PUBLIC_ORGANISATION' THEN RETURN NULL; END IF;
    target := NEW.target_id;
    IF NOT EXISTS (SELECT 1 FROM organisations o JOIN base_public_organisation_publication_snapshots s
      ON s.id = o.current_publication_snapshot_id WHERE o.id = target
      AND s.editorial_case_id = NEW.case_id AND s.editorial_version_id = NEW.version_id
      AND o.publication_status::text = CASE NEW.action::text WHEN 'PUBLISH' THEN 'PUBLISHED' ELSE 'WITHDRAWN' END) THEN
      RAISE EXCEPTION 'o evento exige a projeção final correspondente';
    END IF;
  END IF;
  PERFORM assert_v553_organisation_final_state(target);
  RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog, public;
CREATE CONSTRAINT TRIGGER organisations_final_publication AFTER INSERT OR UPDATE ON organisations
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_v553_organisation_final_state();
CREATE CONSTRAINT TRIGGER base_org_snapshot_final_publication AFTER INSERT ON base_public_organisation_publication_snapshots
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_v553_organisation_final_state();
CREATE CONSTRAINT TRIGGER base_org_event_final_publication AFTER INSERT ON editorial_publication_events
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_v553_organisation_final_state();

CREATE FUNCTION reject_v553_proof_truncate() RETURNS TRIGGER AS $$
BEGIN RAISE EXCEPTION 'as provas editoriais e o histórico não admitem TRUNCATE'; END;
$$ LANGUAGE plpgsql SET search_path = pg_catalog;
CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events
  FOR EACH STATEMENT EXECUTE FUNCTION reject_v553_proof_truncate();
CREATE TRIGGER publication_reviews_no_truncate BEFORE TRUNCATE ON data_publication_reviews
  FOR EACH STATEMENT EXECUTE FUNCTION reject_v553_proof_truncate();
CREATE TRIGGER publication_events_no_truncate BEFORE TRUNCATE ON editorial_publication_events
  FOR EACH STATEMENT EXECUTE FUNCTION reject_v553_proof_truncate();

ALTER TABLE base_public_organisation_publication_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON base_public_organisation_publication_snapshots FROM PUBLIC;
DO $$
DECLARE role_name TEXT; function_name TEXT;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['PUBLIC','anon','authenticated'] LOOP
    IF role_name = 'PUBLIC' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL ON TABLE public.base_public_organisation_publication_snapshots FROM %s', CASE WHEN role_name = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(role_name) END);
      FOREACH function_name IN ARRAY ARRAY['validate_base_organisation_publication_case_insert',
        'validate_base_organisation_publication_version_insert','validate_base_public_organisation_snapshot_insert',
        'reject_base_public_organisation_snapshot_mutation','validate_base_public_organisation_projection',
        'reject_v553_organisation_graph_link','validate_base_public_organisation_event','check_v553_organisation_final_state'] LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION public.%I() FROM %s',function_name, CASE WHEN role_name = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(role_name) END);
      END LOOP;
      EXECUTE format('REVOKE ALL ON FUNCTION public.assert_v553_organisation_final_state(TEXT) FROM %s', CASE WHEN role_name = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(role_name) END);
      EXECUTE format('REVOKE ALL ON FUNCTION public.reject_v553_proof_truncate() FROM %s', CASE WHEN role_name = 'PUBLIC' THEN 'PUBLIC' ELSE quote_ident(role_name) END);
    END IF;
  END LOOP;
END $$;
