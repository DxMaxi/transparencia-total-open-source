import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.42 preserves exact initiative authorship in a private append-only snapshot", async () => {
  const [model, service, repository, schema, migration, script, unit] = await Promise.all([
    source("backend/app/models/parliamentary_initiative_authorship.py"),
    source("backend/app/services/parliament_initiative_authorship.py"),
    source("backend/app/repositories/parliament_initiative_authorship.py"),
    source("prisma/schema.prisma"),
    source("prisma/migrations/20260827130000_v5_parliament_initiative_authorship/migration.sql"),
    source("backend/scripts/sync_parliament_initiative_authorship.py"),
    source("backend/tests/test_parliament_initiative_authorship.py"),
  ]);

  assert.match(model, /PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION/);
  assert.match(model, /class ParliamentInitiativeAuthorObservation/);
  assert.match(model, /official_deputy_id/);
  assert.match(model, /ParliamentInitiativeAuthorRelation\.AUTHOR/);
  assert.match(service, /_field\(value, "idCadastro"\)/);
  assert.match(service, /_field\(initiative, "IniId"\)/);
  assert.match(service, /catalogue_kind is not ParliamentCatalogueKind\.INITIATIVES/);
  assert.match(service, /historical_completeness.*NOT_ASSERTED/s);
  assert.match(service, /settings\.environment not in \{"test", "staging"\}/);
  assert.match(service, /editorial_cases_created": 0/);
  assert.match(service, /publication_performed": False/);

  assert.match(repository, /parliament_initiative_author_snapshots/);
  assert.match(repository, /parliament_initiative_author_observations/);
  assert.match(repository, /source_record_sha256/);
  assert.match(repository, /people_created": 0/);
  assert.match(repository, /editorial_cases_created": 0/);
  assert.match(repository, /publication_performed": False/);
  assert.doesNotMatch(
    repository,
    /INSERT INTO (people|parties|mandates|editorial_cases|data_publication_reviews)/i,
  );

  assert.match(schema, /model ParliamentInitiativeAuthorSnapshot/);
  assert.match(schema, /model ParliamentInitiativeAuthorObservation/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/g);
  assert.match(migration, /reject_parliament_snapshot_mutation/g);
  assert.match(migration, /REVOKE ALL PRIVILEGES/g);
  assert.doesNotMatch(migration, /CREATE POLICY/);
  assert.match(script, /--confirm-private-staging/);
  assert.match(script, /settings\.environment != "staging"/);
  assert.match(unit, /idCadastro e nome oficiais/);
  assert.match(unit, /autorias divergentes/);
  assert.match(unit, /publication_performed.*is False/s);
});

test("V5.42 creates only a PENDING proposal reconstructed from exact official ids", async () => {
  const [
    request,
    editorial,
    routes,
    dependencies,
    action,
    page,
    integration,
    documentation,
    checklist,
    plan,
    readme,
    types,
  ] = await Promise.all([
    source("backend/app/models/editorial.py"),
    source("backend/app/repositories/politician_initiative_authorship_editorial.py"),
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/api/dependencies.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/iniciativas/page.tsx"),
    source("backend/tests/test_parliament_initiative_authorship_integration.py"),
    source("docs/V5_POLITICIAN_INITIATIVE_AUTHORSHIP.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
    source("lib/editorial-types.ts"),
  ]);

  assert.match(request, /class PoliticianInitiativeAuthorshipEditorialProposalRequest/);
  for (const confirmation of [
    "confirm_private_only",
    "confirm_exact_initiative_id",
    "confirm_exact_official_deputy_id",
    "confirm_official_author_relation",
    "confirm_no_name_or_party_matching",
    "confirm_no_collective_position_inference",
  ]) {
    assert.match(request, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(action, new RegExp(`"${confirmation}"`));
    assert.match(page, new RegExp(`${confirmation}`));
  }

  assert.match(editorial, /PARLIAMENT_INITIATIVE_AUTHORSHIP/);
  assert.match(editorial, /EXACT_AR_IDCADASTRO_ONLY/);
  assert.match(editorial, /EXACT_AR_INIID_ONLY/);
  assert.match(editorial, /SOURCE_DECLARED_AUTHOR_ONLY/);
  assert.match(editorial, /person\.source_id = observation\.official_deputy_id/);
  assert.match(editorial, /item\.source_id = observation\.initiative_source_id/);
  assert.match(editorial, /PRIVATE_PENDING_REVIEW/);
  assert.match(editorial, /initiative_authorship_created": False/);
  assert.doesNotMatch(editorial, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(routes, /@router\.get\("\/parliament\/initiative-authorship-candidates"\)/);
  assert.match(routes, /"\/parliament\/initiative-authorship-proposals"/);
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(dependencies, /PoliticianInitiativeAuthorshipEditorialRepository/);
  assert.match(page, /IniId \+ idCadastro exatos/);
  assert.match(page, /autoria não prova voto, apoio ou posição coletiva/i);
  assert.match(page, /Criar proposta PENDING/);

  assert.match(integration, /repeated\["snapshot_created"\] is False/);
  assert.match(integration, /Nome deliberadamente diferente/);
  assert.match(integration, /current_state"\] == "PENDING"/);
  assert.match(integration, /publication_events == 0/);
  assert.match(integration, /COUNT\(\*\) FROM data_publication_reviews/);
  assert.match(integration, /UPDATE parliament_initiative_author_observations/);
  assert.match(integration, /DELETE FROM parliament_initiative_author_snapshots/);

  assert.match(documentation, /URL oficial.*Verificado em.*SHA-256/s);
  assert.match(
    documentation,
    /765d35b6b0525a17feb78d8757e0e41a979bd6716514f5a6ffbbdd670a20265f/,
  );
  assert.match(documentation, /não existe fuzzy matching/i);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(documentation, /PostgreSQL\s+descartável/);
  assert.match(checklist, /\[x\] V5\.42 — `iniAutorDeputados`/);
  assert.match(plan, /V5_POLITICIAN_INITIATIVE_AUTHORSHIP\.md/);
  assert.match(readme, /V5\.1 a V5\.42 preparadas/);
  assert.match(types, /PoliticianInitiativeAuthorshipEditorialCandidate/);
  assert.match(types, /PoliticianInitiativeAuthorshipEditorialProposalResult/);
});
