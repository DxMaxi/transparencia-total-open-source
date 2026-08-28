import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.43 publishes one exact AUTHOR relation in one ADMIN MFA transaction", async () => {
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
    types,
  ] = await Promise.all([
    source("prisma/schema.prisma"),
    source(
      "prisma/migrations/20260827170000_v5_politician_initiative_authorship_publication/migration.sql",
    ),
    source("backend/app/models/editorial.py"),
    source("backend/app/repositories/politician_initiative_authorship_publication.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/api/routes/editorial.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/iniciativas/page.tsx"),
    source("backend/tests/test_parliament_initiative_authorship_integration.py"),
    source("backend/app/repositories/postgres.py"),
    source("components/politician-profile.tsx"),
    source("lib/editorial-types.ts"),
  ]);

  assert.match(schema, /model PoliticianInitiativeAuthorship/);
  for (const field of [
    "personId",
    "initiativeId",
    "sourceObservationId",
    "sourceRecordSha256",
  ]) {
    assert.match(schema, new RegExp(field));
  }
  assert.match(migration, /politician_initiative_authorships_append_only/);
  assert.match(migration, /relation_allowed[\s\S]*AUTHOR/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration, /SET search_path = pg_catalog/);
  assert.match(migration, /REVOKE ALL PRIVILEGES[\s\S]*FROM PUBLIC/);

  assert.match(model, /class PoliticianInitiativeAuthorshipPublicationRequest/);
  for (const confirmation of [
    "confirm_source_reviewed",
    "confirm_exact_official_ids_only",
    "confirm_official_author_relation",
    "confirm_public_initiative_reviewed",
    "confirm_no_name_or_party_matching",
    "confirm_no_collective_position_inference",
    "confirm_append_only_publication",
    "confirm_publication",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(action, new RegExp(`"${confirmation}"`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
  }

  assert.match(dependencies, /PoliticianInitiativeAuthorshipPublicationRepository/);
  assert.match(
    routes,
    /@router\.get\("\/parliament\/initiative-authorship-cases\/\{case_id\}\/publication"\)/,
  );
  assert.match(routes, /@router\.post\([\s\S]*initiative-authorship-cases/);
  assert.match(routes, /Depends\(require_editorial_admin\)/);

  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /INSERT INTO politician_initiative_authorships/);
  assert.match(repository, /POLITICIAN_INITIATIVE_AUTHORSHIP/);
  assert.match(repository, /INSERT INTO data_publication_reviews/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /EditorialAction\.PUBLISH/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(repository, /person\.source_id = observation\.official_deputy_id/);
  assert.match(repository, /initiative\.source_id = observation\.initiative_source_id/);
  assert.match(repository, /activity_review\.publishable = TRUE/);
  assert.doesNotMatch(repository, /INSERT INTO (people|parties|parliamentary_initiatives|mandates)/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /expected_activity_snapshot_sha256/);
  assert.match(page, /Publicar autoria com prova/);
  assert.match(page, /autoria não prova voto, apoio ou posição coletiva/i);
  assert.match(integration, /invalid_payload/);
  assert.match(integration, /events_before/);
  assert.match(integration, /UPDATE politician_initiative_authorships/);
  assert.match(integration, /public_profile\["initiatives"\]/);
  assert.match(publicRepository, /FROM politician_initiative_authorships AS authorship/);
  assert.match(
    publicRepository,
    /to_regclass\('public\.politician_initiative_authorships'\) IS NOT NULL/,
  );
  assert.match(publicRepository, /entity_type = 'POLITICIAN_INITIATIVE_AUTHORSHIP'/);
  assert.match(publicProfile, /Autoria individual verificável/);
  assert.match(types, /PoliticianInitiativeAuthorshipPublicationPreview/);
});

test("V5.43 documents a fail-closed projection without real activation", async () => {
  const [documentation, checklist, plan, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_INITIATIVE_AUTHORSHIP_PUBLICATION.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /fonte[s]? de autoria e de atividade/i);
  assert.match(documentation, /data de recolha/i);
  assert.match(documentation, /SHA-256/);
  assert.match(documentation, /append-only/i);
  assert.match(documentation, /não demonstra sentido de voto/i);
  assert.match(documentation, /não executa migrações nem operações sobre staging ou produção/i);
  assert.match(documentation, /retirada específica[\s\S]*V5\.44/i);
  assert.match(checklist, /\[x\] V5\.43 — publicação ADMIN\+MFA/);
  assert.match(plan, /V5_POLITICIAN_INITIATIVE_AUTHORSHIP_PUBLICATION\.md/);
  assert.match(readme, /V5\.1 a V5\.\d+ preparadas/);
});
