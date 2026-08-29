import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.45 persists the official person id without rewriting old vote records", async () => {
  const [
    schema,
    migration,
    model,
    sync,
    currentPersistence,
    bulkPersistence,
    historicalRepository,
    historicalNormalizer,
    persistenceTests,
    historicalIntegration,
  ] = await Promise.all([
    source("prisma/schema.prisma"),
    source(
      "prisma/migrations/20260828124500_v5_exact_nominal_vote_identity/migration.sql",
    ),
    source("backend/app/models/parliamentary.py"),
    source("backend/scripts/sync_parliament_activity.py"),
    source("backend/app/repositories/parliament_activity.py"),
    source("backend/app/repositories/parliament_activity_bulk.py"),
    source("backend/app/repositories/parliament_resource_normalization.py"),
    source("backend/app/services/parliament_resource_vote_normalization.py"),
    source("backend/tests/test_parliament_activity_repository.py"),
    source("backend/tests/test_parliament_resource_normalization_integration.py"),
  ]);

  assert.match(schema, /actorSourceId\s+String\?\s+@map\("actor_source_id"\)/);
  assert.match(schema, /@@index\(\[actorType, actorSourceId\]\)/);
  assert.match(migration, /ADD COLUMN "actor_source_id" TEXT/);
  assert.match(migration, /vote_records_actor_source_id_not_blank/);
  assert.match(migration, /vote_records_person_official_id_per_event_key/);
  assert.match(migration, /WHERE "actor_type" = 'PERSON'/);
  assert.match(migration, /Não existe backfill/i);
  assert.doesNotMatch(migration, /UPDATE\s+"?vote_records"?/i);
  assert.doesNotMatch(migration, /DELETE\s+FROM\s+"?vote_records"?/i);

  assert.match(model, /default="parliament-activity-v6"/);
  assert.match(sync, /CODE_VERSION = "parliament-activity-v6"/);
  assert.match(sync, /_exact_vote_identity_schema_is_ready/);
  assert.match(sync, /SCHEMA_MIGRATION_REQUIRED/);
  assert.match(sync, /publication": "NOT_ATTEMPTED"/);
  assert.match(currentPersistence, /record\.actor_source_id/);
  assert.match(currentPersistence, /person_records_without_official_id/);
  assert.match(currentPersistence, /mismatched_person_links/);
  assert.match(currentPersistence, /nova versão do parser/);
  assert.match(bulkPersistence, /actor_label, actor_source_id/);
  assert.match(historicalRepository, /parliament-historical-votes-v2/);
  assert.match(historicalNormalizer, /record\.actor_source_id/);
  assert.match(persistenceTests, /insert_call\.args\[5\] == "dep-1"/);
  assert.match(historicalIntegration, /actor_source_id/);
});

test("V5.45 blocks unproven identities and projects only exact nominal votes", async () => {
  const [
    editorial,
    publication,
    publicProfile,
    publicParliament,
    admin,
    types,
    stagingTests,
  ] = await Promise.all([
    source("backend/app/repositories/parliament_editorial.py"),
    source("backend/app/repositories/parliament_editorial_publication.py"),
    source("backend/app/repositories/postgres.py"),
    source("backend/app/repositories/public_parliament.py"),
    source("app/admin/revisao/parlamento/page.tsx"),
    source("lib/editorial-types.ts"),
    source("backend/tests/test_parliament_vote_staging.py"),
  ]);

  for (const metric of [
    "exact_person_records",
    "unproven_person_records",
    "mismatched_person_links",
  ]) {
    assert.match(editorial, new RegExp(metric));
    assert.match(admin, new RegExp(metric));
    assert.match(types, new RegExp(metric));
  }
  assert.match(publication, /UNPROVEN_PERSON_RECORDS/);
  assert.match(publication, /MISMATCHED_PERSON_LINKS/);
  assert.match(publicProfile, /"parliament-activity-v6"/);
  assert.match(publicProfile, /"parliament-historical-votes-v2"/);
  assert.match(
    publicProfile,
    /to_jsonb\(available_record\) ->> 'actor_source_id'/,
  );
  assert.match(publicProfile, /to_jsonb\(vr\) ->> 'actor_source_id'/);
  assert.match(publicParliament, /to_jsonb\(record\) ->> 'actor_source_id'/);
  assert.match(publicParliament, /party\.source_id/);
  assert.doesNotMatch(publicProfile, /available_record\.actor_source_id|vr\.actor_source_id/);
  assert.doesNotMatch(publicParliament, /record\.actor_source_id/);
  assert.doesNotMatch(publicProfile, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);
  assert.match(stagingTests, /person_identifiers_fully_preserved/);
  assert.match(stagingTests, /person_links_match_official_identifiers/);
});

test("V5.45 keeps publication human and documents unavailable historical coverage", async () => {
  const [documentation, profiles, checklist, plan, handoff, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_NOMINAL_VOTE_IDENTITY.md"),
    source("docs/V5_POLITICIAN_PROFILES.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("docs/PROJECT_HANDOFF.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /não cria uma porta de publicação paralela/i);
  assert.match(documentation, /proposta `PENDING`/);
  assert.match(documentation, /ADMIN` com MFA/);
  assert.match(documentation, /retirada append-only/i);
  assert.match(
    documentation,
    /Sem todos[\s\S]*estes elementos, a resposta é `dados indisponíveis`/i,
  );
  assert.match(documentation, /não executa migração em staging ou produção/i);
  assert.match(documentation, /não transforma posição partidária em voto individual/i);
  assert.match(profiles, /actor_source_id = people\.source_id/);
  assert.match(checklist, /\[x\] V5\.45/);
  assert.match(checklist, /\[x\] Posições coletivas permanecem fora/);
  assert.match(plan, /V5_POLITICIAN_NOMINAL_VOTE_IDENTITY\.md/);
  assert.match(handoff, /A V5\.45 fecha a prova dos votos nominais/);
  assert.match(readme, /V5\.1 a V5\.\d+ preparadas/);
});
