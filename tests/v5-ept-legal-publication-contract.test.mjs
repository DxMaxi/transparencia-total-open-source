import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.47 keeps the legal assessment and exact identity proof private and append-only", async () => {
  const [schema, migration, models, repository] = await Promise.all([
    source("prisma/schema.prisma"),
    source("prisma/migrations/20260829113000_v5_ept_legal_publication_gate/migration.sql"),
    source("backend/app/models/ept_declaration.py"),
    source("backend/app/repositories/ept_declaration_publication.py"),
  ]);

  assert.match(schema, /model EptIndependentLegalAssessment/);
  assert.match(schema, /model EptExactIdentityLink/);
  assert.match(schema, /officialSubjectDigest\s+String[^]*@db\.Char\(64\)/);
  assert.doesNotMatch(schema, /officialSubjectIdentifier\s+String/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration, /BEFORE UPDATE OR DELETE/);
  assert.match(migration, /UPDATE e DELETE são proibidos/);
  assert.match(migration, /REVOKE ALL PRIVILEGES[^]*FROM PUBLIC/);
  assert.match(migration, /ARRAY\['anon', 'authenticated'\]/);
  assert.match(migration, /ON DELETE RESTRICT/);
  assert.match(migration, /review\."entity_type" = 'PERSON'/);
  assert.match(migration, /review\."source_document_id" = evidence\."id"/);
  assert.match(migration, /review\."publishable"/);
  assert.match(migration, /evidence\."official_identifier" = person\."source_id"/);
  assert.match(migration, /avaliação EPT não pode ter uma data futura/);
  assert.match(migration, /LANGUAGE plpgsql SET search_path = pg_catalog, public/);

  assert.match(models, /official_subject_identifier: SecretStr/);
  assert.match(models, /assessment_document_storage_key: SecretStr/);
  assert.match(models, /confirm_system_did_not_issue_legal_opinion: Literal\[True\]/);
  assert.match(models, /confirm_no_name_or_fuzzy_matching: Literal\[True\]/);
  assert.match(repository, /hmac_private_reference_identifier/);
  assert.match(repository, /secrets\.compare_digest/);
  assert.match(repository, /raw_identifier_persisted[^]*False/);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|rapidfuzz|fuzzywuzzy/i);
});

test("V5.47 publishes or withdraws only through the scoped ADMIN plus MFA gate", async () => {
  const [repository, routes, dependencies, postgres, actions, page, docs, checklist] =
    await Promise.all([
      source("backend/app/repositories/ept_declaration_publication.py"),
      source("backend/app/api/routes/editorial.py"),
      source("backend/app/api/dependencies.py"),
      source("backend/app/repositories/postgres.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/declaracoes/ept-gate-actions.tsx"),
      source("docs/V5_EPT_LEGAL_PUBLICATION_GATE.md"),
      source("docs/V5_RELEASE_CHECKLIST.md"),
    ]);

  assert.match(repository, /actor\.role is not StaffRole\.ADMIN/);
  assert.match(repository, /actor\.assurance_level != "aal2"/);
  assert.match(repository, /_TARGET_TYPE = "EPT_PUBLIC_INTEREST_DECLARATION"/);
  assert.match(repository, /INSERT INTO asset_declaration_metadata/);
  assert.match(repository, /INSERT INTO data_publication_reviews/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /EditorialAction\.PUBLISH/);
  assert.match(repository, /EditorialAction\.WITHDRAW/);
  assert.match(repository, /identity_link_deleted[^]*False/);
  assert.match(repository, /legal_assessment_deleted[^]*False/);
  assert.match(postgres, /target_type = 'EPT_PUBLIC_INTEREST_DECLARATION'/);
  assert.match(postgres, /publication_event\.action = 'PUBLISH'/);

  for (const endpoint of [
    "legal-assessments",
    "identity-links",
    "publication",
    "withdrawal",
  ]) {
    assert.match(routes, new RegExp(`ept/cases/\\{case_id\\}/${endpoint}`));
  }
  assert.match(routes, /Depends\(require_editorial_admin\)/);
  assert.match(dependencies, /EptDeclarationPublicationGateRepository/);
  assert.match(actions, /recordEptLegalAssessment/);
  assert.match(actions, /recordEptExactIdentityLink/);
  assert.match(actions, /publishEptPublicInterest/);
  assert.match(actions, /withdrawEptPublicInterest/);
  assert.match(page, /Este formulário não cria um parecer/);
  assert.match(page, /Não serão publicados rendimentos, património ou identificadores protegidos/);
  assert.match(docs, /não constitui\s+aconselhamento jurídico/i);
  assert.match(docs, /dados indisponíveis/);
  assert.match(checklist, /\[x\] V5\.47/);
  assert.match(checklist, /\[ \] Antes de tratar um caso real/);
});
