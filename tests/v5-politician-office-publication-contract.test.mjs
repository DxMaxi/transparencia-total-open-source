import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.37 publishes one exact office period in one ADMIN MFA transaction", async () => {
  const [
    schema,
    migration,
    model,
    repository,
    dependencies,
    routes,
    action,
    page,
    integration,
    publicRepository,
    publicProfile,
    publicTypes,
  ] = await Promise.all([
    source("prisma/schema.prisma"),
    source("prisma/migrations/20260826173000_v5_parliament_office_publication/migration.sql"),
    source("backend/app/models/editorial.py"),
    source("backend/app/repositories/politician_office_publication.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/api/routes/editorial.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/cargos/page.tsx"),
    source("backend/tests/test_politician_office_editorial_integration.py"),
    source("backend/app/repositories/postgres.py"),
    source("components/politician-profile.tsx"),
    source("types/domain.ts"),
  ]);

  assert.match(schema, /model ParliamentaryOfficePeriod/);
  for (const field of [
    "sourceObservationId",
    "sourcePeriodOrdinal",
    "officialOfficeId",
    "constituencySourceId",
    "sourcePeriodSha256",
  ]) {
    assert.match(schema, new RegExp(field));
  }
  assert.match(schema, /@@unique\(\[sourceObservationId, sourcePeriodOrdinal\]\)/);
  assert.match(migration, /parliamentary_office_periods_period_order/);
  assert.match(migration, /parliamentary_office_periods_source_period_sha256_format/);
  assert.match(migration, /parliamentary_office_periods_append_only/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration, /SET search_path = pg_catalog/);
  assert.match(migration, /REVOKE ALL PRIVILEGES[\s\S]*FROM PUBLIC/);

  assert.match(model, /class PoliticianOfficePublicationRequest/);
  for (const confirmation of [
    "confirm_source_reviewed",
    "confirm_human_office_interpretation",
    "confirm_exact_official_ids_only",
    "confirm_no_mandate_or_party_inference",
    "confirm_append_only_publication",
    "confirm_publication",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }
  assert.match(dependencies, /PoliticianOfficePublicationRepository/);
  assert.match(routes, /@router\.get\("\/parliament\/office-cases\/\{case_id\}\/publication"\)/);
  assert.match(routes, /@router\.post\([\s\S]*office-cases\/\{case_id\}\/publication/);
  assert.match(routes, /Depends\(require_editorial_admin\)/);

  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /INSERT INTO parliamentary_office_periods/);
  assert.match(repository, /'PARLIAMENT_OFFICE'/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /EditorialAction\.PUBLISH/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(repository, /source_office\.period ->> 'source_id'/);
  assert.match(repository, /latest_person_review\.publishable = TRUE/);
  assert.match(repository, /person\.source_id = observation\.source_id/);
  assert.doesNotMatch(repository, /INSERT INTO mandates/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /expected_publication_proof_sha256/);
  assert.match(page, /Publicar cargo com prova/);
  assert.match(page, /ADMIN com MFA/);
  assert.match(integration, /counts_after_failed_publication == counts_before_failed_publication/);
  assert.match(integration, /UPDATE parliamentary_office_periods/);
  assert.match(integration, /public_profile\["parliamentary_offices"\]/);
  assert.match(publicRepository, /FROM parliamentary_office_periods office/);
  assert.match(publicRepository, /entity_type = 'PARLIAMENT_OFFICE'/);
  assert.match(publicRepository, /entity_type = 'PERSON'[\s\S]*person_review\.publishable = TRUE/);
  assert.match(publicRepository, /observation\.constituency_source_id = office\.constituency_source_id/);
  assert.match(publicProfile, /Cargos parlamentares observados/);
  assert.match(publicProfile, /CarId/);
  assert.match(publicProfile, /Período SHA-256/);
  assert.match(publicTypes, /interface ParliamentaryOfficeRecord/);
});

test("V5.37 documents a separate office projection without real activation", async () => {
  const [documentation, checklist, plan, handoff, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_OFFICE_PUBLICATION.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("docs/PROJECT_HANDOFF.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /fonte\s+oficial/i);
  assert.match(documentation, /data de recolha/i);
  assert.match(documentation, /SHA-256/);
  assert.match(documentation, /append-only/i);
  assert.match(documentation, /não é um\s+mandato/i);
  assert.match(documentation, /não publica dados reais/i);
  assert.match(documentation, /retirada[\s\S]*V5\.38/i);
  assert.match(checklist, /\[x\] V5\.37 — publicação transacional/);
  assert.match(plan, /V5_POLITICIAN_OFFICE_PUBLICATION\.md/);
  assert.match(handoff, /V5\.37 acrescenta a publicação específica/);
  assert.match(readme, /V5\.1 a V5\.41 preparadas/);
});
