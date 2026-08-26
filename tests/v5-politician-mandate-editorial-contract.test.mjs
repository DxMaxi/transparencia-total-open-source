import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.33 creates one private mandate case from an exact official period", async () => {
  const [model, routes, dependencies, repository, action, page, types, integration] =
    await Promise.all([
      source("backend/app/models/editorial.py"),
      source("backend/app/api/routes/editorial.py"),
      source("backend/app/api/dependencies.py"),
      source("backend/app/repositories/politician_mandate_editorial.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/parlamento/deputados/mandatos/page.tsx"),
      source("lib/editorial-types.ts"),
      source("backend/tests/test_politician_mandate_editorial_integration.py"),
    ]);

  assert.match(model, /class PoliticianMandateEditorialProposalRequest/);
  for (const confirmation of [
    "confirm_private_only",
    "confirm_exact_official_id_only",
    "confirm_period_semantics_require_human_review",
    "confirm_no_party_inference",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }
  assert.match(model, /source_period_sha256: str = Field\(pattern=r"\^\[0-9a-f\]\{64\}\$"\)/);
  assert.match(routes, /@router\.get\("\/parliament\/mandate-candidates"\)/);
  assert.match(routes, /@router\.post\("\/parliament\/mandate-proposals"/);
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(dependencies, /PoliticianMandateEditorialRepository/);

  assert.match(repository, /source\.publisher = 'PARLIAMENT'/);
  assert.match(repository, /jsonb_array_elements\(observation\.mandate_situations\)/);
  assert.match(repository, /person\.source_id = observation\.source_id/);
  assert.match(repository, /review\.entity_type = 'PERSON'/);
  assert.match(repository, /review\.source_document_id = snapshot\.source_document_id/);
  assert.match(repository, /attestation\.content_sha256 = source\.content_sha256/);
  assert.match(repository, /EditorialCaseKind\.POLITICIAN_PROFILE/);
  assert.match(repository, /PARLIAMENT_MANDATE_SITUATION/);
  assert.match(repository, /HUMAN_REVIEW_REQUIRED/);
  assert.match(repository, /EXACT_AR_DEP_ID_ONLY/);
  assert.doesNotMatch(repository, /INSERT INTO (people|mandates|data_publication_reviews)/i);
  assert.doesNotMatch(repository, /INSERT INTO editorial_publication_events/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /source_period_sha256: sourcePeriodSha256/);
  assert.match(action, /\/parliament\/mandate-proposals/);
  assert.doesNotMatch(action, /normalized_data:[\s\S]{0,250}mandate-proposals/);
  assert.match(page, /Uma data observada não é uma conclusão jurídica/);
  assert.match(page, /não cria qualquer linha na cronologia pública/i);
  assert.match(types, /PoliticianMandateEditorialCandidate/);
  assert.match(types, /PoliticianMandateEditorialProposalResult/);

  assert.match(integration, /mandates_after == mandates_before/);
  assert.match(integration, /reviews_after == reviews_before/);
  assert.match(integration, /publication_events == 0/);
  assert.match(integration, /decisions == 3/);
});

test("V5.33 documentation keeps approval separate from mandate publication", async () => {
  const [documentation, checklist, plan, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_MANDATE_EDITORIAL.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /`DepId` oficial exato/);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(documentation, /cria zero:[\s\S]*mandatos/i);
  assert.match(documentation, /revisão `MANDATE`/);
  assert.match(documentation, /operação de domínio separada/i);
  assert.match(checklist, /\[x\] V5\.33 — intervalos oficiais/);
  assert.match(plan, /V5_POLITICIAN_MANDATE_EDITORIAL\.md/);
  assert.match(readme, /V5\.1 a V5\.35 preparadas/);
});
