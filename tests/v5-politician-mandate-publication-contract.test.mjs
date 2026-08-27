import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.34 publishes one exact mandate in one ADMIN MFA transaction", async () => {
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
  ] = await Promise.all([
    source("prisma/schema.prisma"),
    source("prisma/migrations/20260826073000_v5_mandate_publication_evidence/migration.sql"),
    source("backend/app/models/editorial.py"),
    source("backend/app/repositories/politician_mandate_publication.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/api/routes/editorial.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/mandatos/page.tsx"),
    source("backend/tests/test_politician_mandate_publication_integration.py"),
    source("backend/app/repositories/postgres.py"),
    source("components/politician-profile.tsx"),
  ]);

  for (const field of [
    "sourceObservationId",
    "sourcePeriodOrdinal",
    "sourcePeriodSha256",
  ]) {
    assert.match(schema, new RegExp(field));
  }
  assert.match(schema, /@@unique\(\[sourceObservationId, sourcePeriodOrdinal\]\)/);
  assert.match(migration, /mandates_source_period_bundle_check/);
  assert.match(migration, /mandates_period_order_check/);
  assert.match(migration, /mandates_source_observation_id_fkey/);
  assert.match(migration, /mandates_append_only/);
  assert.match(migration, /data_publication_reviews_append_only/);
  assert.match(migration, /SET search_path = pg_catalog/);
  assert.match(migration, /REVOKE ALL PRIVILEGES[\s\S]*FROM PUBLIC/);

  assert.match(model, /class PoliticianMandatePublicationRequest/);
  for (const confirmation of [
    "confirm_source_reviewed",
    "confirm_human_period_interpretation",
    "confirm_exact_official_id_only",
    "confirm_no_party_inference",
    "confirm_append_only_publication",
    "confirm_publication",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }
  assert.match(dependencies, /PoliticianMandatePublicationRepository/);
  assert.match(routes, /@router\.get\("\/parliament\/mandate-cases\/\{case_id\}\/publication"\)/);
  assert.match(routes, /@router\.post\([\s\S]*mandate-cases\/\{case_id\}\/publication/);
  assert.match(routes, /Depends\(require_editorial_admin\)/);

  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /version\.normalized_json AS normalized_data/);
  assert.doesNotMatch(repository, /version\.normalized_data/);
  assert.match(repository, /INSERT INTO mandates/);
  assert.match(repository, /'MANDATE'/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /EditorialAction\.PUBLISH/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(repository, /source_observation_id = \$2/);
  assert.match(repository, /source_period_ordinal = \$3/);
  assert.match(repository, /source_period_sha256 = \$4/);
  assert.match(repository, /latest_person_review\.publishable = TRUE/);
  assert.match(repository, /person\.source_id = observation\.source_id/);
  assert.doesNotMatch(repository, /(?:UPDATE|DELETE FROM) mandates/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /expected_publication_proof_sha256/);
  assert.match(page, /Publicar mandato com prova/);
  assert.match(page, /ADMIN com MFA/);
  assert.match(integration, /expected_publication_proof_sha256.*"0" \* 64/s);
  assert.match(integration, /SELECT COUNT\(\*\) FROM mandates WHERE source_observation_id/);
  assert.match(integration, /pytest\.raises\(asyncpg\.PostgresError, match="append-only"\)/);
  assert.match(integration, /public_profile\["mandates"\]\[0\]\["source_period_sha256"\]/);
  assert.match(publicRepository, /to_jsonb\(mandate\) ->> 'source_period_sha256'/);
  assert.match(publicProfile, /Fonte recolhida em/);
  assert.match(publicProfile, /Fonte SHA-256/);
  assert.match(publicProfile, /Intervalo SHA-256/);
  assert.match(publicProfile, /Prova do intervalo: dados indisponíveis/);
});

test("V5.34 remains operationally gated after the separate immutable withdrawal", async () => {
  const [documentation, checklist, plan, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_MANDATE_PUBLICATION.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /fonte oficial/i);
  assert.match(documentation, /data de recolha/i);
  assert.match(documentation, /SHA-256/);
  assert.match(documentation, /append-only/i);
  assert.match(documentation, /não publica dados reais/i);
  assert.match(documentation, /retirada imutável[\s\S]*V5\.35/i);
  assert.match(checklist, /\[x\] V5\.34 — publicação transacional/);
  assert.match(checklist, /\[x\] V5\.35 — retirada transacional e imutável/);
  assert.match(plan, /V5_POLITICIAN_MANDATE_PUBLICATION\.md/);
  assert.match(readme, /V5\.1 a V5\.40 preparadas/);
});
