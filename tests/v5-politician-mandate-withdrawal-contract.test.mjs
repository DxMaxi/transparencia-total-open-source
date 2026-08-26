import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.35 withdraws one exact mandate and preserves every historical row", async () => {
  const [
    model,
    repository,
    publicationRepository,
    dependencies,
    routes,
    action,
    page,
    integration,
    publicRepository,
  ] = await Promise.all([
    source("backend/app/models/editorial.py"),
    source("backend/app/repositories/politician_mandate_withdrawal.py"),
    source("backend/app/repositories/politician_mandate_publication.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/api/routes/editorial.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/mandatos/page.tsx"),
    source("backend/tests/test_politician_mandate_publication_integration.py"),
    source("backend/app/repositories/postgres.py"),
  ]);

  assert.match(model, /class PoliticianMandateWithdrawalRequest/);
  for (const confirmation of [
    "confirm_source_and_publication_reviewed",
    "confirm_exact_mandate",
    "confirm_public_effect_reviewed",
    "confirm_mandate_and_history_preserved",
    "confirm_no_selective_identity_change",
    "confirm_withdrawal",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }

  assert.match(dependencies, /PoliticianMandateWithdrawalRepository/);
  assert.match(routes, /@router\.get\("\/parliament\/mandate-cases\/\{case_id\}\/withdrawal"\)/);
  assert.match(routes, /@router\.post\([\s\S]*mandate-cases\/\{case_id\}\/withdrawal/);
  assert.match(routes, /Depends\(require_editorial_admin\)/);

  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /VALUES \(\$1, 'MANDATE',[\s\S]*FALSE/);
  assert.match(repository, /'MANDATE', \$2, 'WITHDRAWN'/);
  assert.match(repository, /EditorialAction\.WITHDRAW/);
  assert.match(repository, /'WITHDRAW'::"EditorialPublicationAction"/);
  assert.match(repository, /mandate_preserved/);
  assert.match(repository, /still_public/);
  assert.match(repository, /"mandates_deleted": 0/);
  assert.match(repository, /"people_deleted": 0/);
  assert.match(repository, /"memberships_deleted": 0/);
  assert.doesNotMatch(repository, /(?:UPDATE|DELETE FROM) mandates/i);
  assert.doesNotMatch(repository, /(?:UPDATE|DELETE FROM) data_publication_reviews/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(publicationRepository, /def _mandate_publication_proof_sha256/);
  assert.match(publicationRepository, /action="PUBLISH"/);
  assert.match(action, /expected_withdrawal_proof_sha256/);
  assert.match(page, /Retirar mandato e preservar histórico/);
  assert.match(page, /Categoria permitida pela governação/);
  assert.match(page, /ADMIN com MFA/);
  assert.match(integration, /expected_public_effect_sha256.*"0" \* 64/s);
  assert.match(integration, /\[row\["publishable"\] for row in reviews\] == \[True, False\]/);
  assert.match(integration, /public_profile_after_withdrawal\["mandates"\] == \[\]/);
  assert.match(publicRepository, /ORDER BY candidate\.reviewed_at DESC, candidate\.id DESC/);
});

test("V5.35 closes the mandate gate without activating real data", async () => {
  const [documentation, checklist, plan, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_MANDATE_WITHDRAWAL.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /fonte oficial/i);
  assert.match(documentation, /data de recolha/i);
  assert.match(documentation, /SHA-256/);
  assert.match(documentation, /append-only/i);
  assert.match(documentation, /não (?:é )?apagad/i);
  assert.match(documentation, /não executa[\s\S]*dados reais/i);
  assert.match(checklist, /\[x\] V5\.35 — retirada transacional e imutável/);
  assert.match(plan, /V5_POLITICIAN_MANDATE_WITHDRAWAL\.md/);
  assert.match(readme, /V5\.1 a V5\.35 preparadas/);
  assert.doesNotMatch(readme, /V5\.1 a V5\.34 preparadas/);
});
