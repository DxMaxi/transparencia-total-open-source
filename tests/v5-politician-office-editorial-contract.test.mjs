import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.36 creates one private office case from exact official identifiers", async () => {
  const [model, routes, dependencies, repository, action, page, types, integration] =
    await Promise.all([
      source("backend/app/models/editorial.py"),
      source("backend/app/api/routes/editorial.py"),
      source("backend/app/api/dependencies.py"),
      source("backend/app/repositories/politician_office_editorial.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/parlamento/deputados/cargos/page.tsx"),
      source("lib/editorial-types.ts"),
      source("backend/tests/test_politician_office_editorial_integration.py"),
    ]);

  assert.match(model, /class PoliticianOfficeEditorialProposalRequest/);
  for (const confirmation of [
    "confirm_private_only",
    "confirm_exact_official_ids_only",
    "confirm_observed_period_requires_human_review",
    "confirm_no_mandate_or_party_inference",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }
  assert.match(model, /source_period_sha256: str = Field\(pattern=r"\^\[0-9a-f\]\{64\}\$"\)/);
  assert.match(routes, /@router\.get\("\/parliament\/office-candidates"\)/);
  assert.match(routes, /@router\.post\("\/parliament\/office-proposals"/);
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(dependencies, /PoliticianOfficeEditorialRepository/);

  assert.match(repository, /source\.publisher = 'PARLIAMENT'/);
  assert.match(repository, /jsonb_array_elements\(observation\.offices\)/);
  assert.match(repository, /office\.period ->> 'title'/);
  assert.match(repository, /person\.source_id = observation\.source_id/);
  assert.match(repository, /review\.entity_type = 'PERSON'/);
  assert.match(repository, /attestation\.content_sha256 = source\.content_sha256/);
  assert.match(repository, /PARLIAMENT_OFFICE_PERIOD/);
  assert.match(repository, /EXACT_AR_DEP_ID_ONLY/);
  assert.match(repository, /EXACT_AR_CAR_ID_ONLY/);
  assert.match(repository, /office_creation_performed": False/);
  assert.doesNotMatch(repository, /INSERT INTO (people|mandates|data_publication_reviews)/i);
  assert.doesNotMatch(repository, /INSERT INTO editorial_publication_events/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /source_period_sha256: sourcePeriodSha256/);
  assert.match(action, /\/parliament\/office-proposals/);
  assert.doesNotMatch(action, /normalized_data:[\s\S]{0,250}office-proposals/);
  assert.match(page, /Cargo observado não é mandato/);
  assert.match(page, /não cria cargo público, mandato, filiação/i);
  assert.match(types, /PoliticianOfficeEditorialCandidate/);
  assert.match(types, /PoliticianOfficeEditorialProposalResult/);

  assert.match(integration, /mandates_after == mandates_before/);
  assert.match(integration, /reviews_after == reviews_before/);
  assert.match(integration, /publication_events == 0/);
  assert.match(integration, /decisions == 3/);
});

test("V5.36 documents an editorial gate without activating real office data", async () => {
  const [documentation, checklist, plan, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_OFFICE_EDITORIAL.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /`DepId` e `CarId` oficiais exatos/);
  assert.match(documentation, /URL oficial, a data de recolha, o SHA-256/);
  assert.match(documentation, /cria zero:[\s\S]*cargos ou mandatos públicos/i);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(documentation, /não existe fuzzy matching/i);
  assert.match(documentation, /PostgreSQL descartável/);
  assert.match(documentation, /não recolhe nem[\s\S]*staging ou produção/i);
  assert.match(checklist, /\[x\] V5\.36 — cada `DepCargo`/);
  assert.match(plan, /V5_POLITICIAN_OFFICE_EDITORIAL\.md/);
  assert.match(readme, /V5\.1 a V5\.36 preparadas/);
});
