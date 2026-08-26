import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.31 withdraws only a complete published profile snapshot with ADMIN MFA", async () => {
  const [model, routes, dependencies, repository, publicRepository, action, page, types, integration] =
    await Promise.all([
      source("backend/app/models/editorial.py"),
      source("backend/app/api/routes/editorial.py"),
      source("backend/app/api/dependencies.py"),
      source("backend/app/repositories/politician_profile_snapshot_withdrawal.py"),
      source("backend/app/repositories/public_politicians.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/parlamento/deputados/prontidao/page.tsx"),
      source("lib/editorial-types.ts"),
      source("backend/tests/test_politician_profile_snapshot_publication_integration.py"),
    ]);

  assert.match(model, /class PoliticianProfileSnapshotWithdrawalRequest\(BaseModel\):/);
  for (const confirmation of [
    "confirm_complete_snapshot",
    "confirm_no_selective_removal",
    "confirm_public_effect_reviewed",
    "confirm_people_and_history_preserved",
    "confirm_withdrawal",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }

  assert.match(
    routes,
    /@router\.get\("\/parliament\/deputy-snapshots\/\{snapshot_id\}\/withdrawal"\)/,
  );
  assert.match(
    routes,
    /@router\.post\("\/parliament\/deputy-snapshots\/\{snapshot_id\}\/withdrawal"\)/,
  );
  assert.match(routes, /withdraw_parliament_deputy_snapshot[\s\S]*require_editorial_admin/);
  assert.match(dependencies, /PoliticianProfileSnapshotWithdrawalRepository/);

  assert.match(
    repository,
    /async with self\.pool\.acquire\(\) as connection, connection\.transaction\(\):/,
  );
  assert.match(repository, /politician-profile-snapshot-publication:/);
  assert.match(repository, /parliament-people-publication:/);
  assert.match(repository, /EditorialAction\.WITHDRAW/);
  assert.match(repository, /EditorialState\.WITHDRAWN/);
  assert.match(repository, /INSERT INTO data_publication_reviews/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(repository, /'WITHDRAW'::"EditorialPublicationAction"/);
  assert.match(repository, /FALLBACK_TO_PREVIOUS_SNAPSHOT/);
  assert.match(repository, /DATA_UNAVAILABLE/);
  assert.match(repository, /archive\.retrieved_at = source\.retrieved_at/);
  assert.match(publicRepository, /archive\.retrieved_at = source\.retrieved_at/);
  assert.match(publicRepository, /profile_archive\.retrieved_at = source\.retrieved_at/);
  assert.match(repository, /public_effect_sha256/);
  assert.match(repository, /withdrawal_proof_sha256/);
  assert.doesNotMatch(repository, /DELETE\s+FROM\s+(people|parliamentary_membership_snapshots)/i);
  assert.doesNotMatch(repository, /UPDATE\s+(people|parliamentary_membership_snapshots)/i);
  assert.doesNotMatch(repository, /DELETE\s+FROM\s+editorial_versions/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /withdrawPoliticianProfileSnapshot/);
  assert.match(action, /method: "POST"/);
  assert.match(action, /revalidatePath\("\/politicos"\)/);
  assert.match(page, /Retirar a fotografia completa/);
  assert.match(page, /Nenhuma pessoa foi escolhida ou omitida individualmente/);
  assert.match(page, /pessoas, fontes, versões e histórico serão preservados/i);
  assert.match(types, /PoliticianProfileSnapshotWithdrawalPreview/);
  assert.match(types, /PoliticianProfileSnapshotWithdrawalResult/);

  assert.match(integration, /expected_public_effect_sha256": "e" \* 64/);
  assert.match(integration, /counts_after_failed_withdrawal == counts_before_failed_withdrawal/);
  assert.match(integration, /\["PUBLISH", "WITHDRAW"\]/);
  assert.match(integration, /no_longer_public\["total"\] == 0/);
  assert.match(integration, /people_deleted.*== 0/);
  assert.match(integration, /COUNT\(\*\) FROM mandates/);
});

test("V5.31 documents immutable withdrawal without claiming a real operation", async () => {
  const [documentation, checklist, plan, handoff, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_PROFILE_SNAPSHOT_WITHDRAWAL.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("docs/PROJECT_HANDOFF.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /fotografia completa/i);
  assert.match(documentation, /não existe retirada de uma pessoa escolhida/i);
  assert.match(documentation, /não executa qualquer retirada real/i);
  assert.match(documentation, /nova[\s*]+fotografia imutável/i);
  assert.match(documentation, /pessoas[\s\S]*histórico[\s\S]*preservad/i);
  assert.match(documentation, /deployment nunca chamam esta operação automaticamente/i);
  assert.match(checklist, /\[x\] V5\.31 — retirada não seletiva/);
  assert.match(plan, /V5_POLITICIAN_PROFILE_SNAPSHOT_WITHDRAWAL\.md/);
  assert.match(handoff, /V5\.31/);
  assert.match(readme, /V5\.1 a V5\.35 preparadas/);
  assert.match(readme, /V5_POLITICIAN_PROFILE_SNAPSHOT_WITHDRAWAL\.md/);
});
