import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.30 publishes a complete profile snapshot only through an ADMIN MFA transaction", async () => {
  const [model, routes, dependencies, repository, action, page, types, integration] =
    await Promise.all([
      source("backend/app/models/editorial.py"),
      source("backend/app/api/routes/editorial.py"),
      source("backend/app/api/dependencies.py"),
      source("backend/app/repositories/politician_profile_snapshot_publication.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/parlamento/deputados/prontidao/page.tsx"),
      source("lib/editorial-types.ts"),
      source("backend/tests/test_politician_profile_snapshot_publication_integration.py"),
    ]);

  assert.match(model, /class PoliticianProfileSnapshotPublicationRequest\(BaseModel\):/);
  for (const confirmation of [
    "confirm_source_reviewed",
    "confirm_complete_snapshot",
    "confirm_exact_official_id_only",
    "confirm_no_mandate_inference",
    "confirm_no_party_inference",
    "confirm_publication",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }

  assert.match(
    routes,
    /@router\.get\("\/parliament\/deputy-snapshots\/\{snapshot_id\}\/publication"\)/,
  );
  assert.match(
    routes,
    /@router\.post\("\/parliament\/deputy-snapshots\/\{snapshot_id\}\/publication"\)/,
  );
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(routes, /Depends\(require_editorial_admin\)/);
  assert.match(dependencies, /PoliticianProfileSnapshotPublicationRepository/);

  assert.match(
    repository,
    /async with self\.pool\.acquire\(\) as connection, connection\.transaction\(\):/,
  );
  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /parliament-people-publication:/);
  assert.match(repository, /self\.readiness\.inspect\([\s\S]{0,120}connection=connection/);
  assert.match(
    repository,
    /LEFT JOIN people AS person ON person\.source_id = observation\.source_id/,
  );
  assert.match(repository, /INSERT INTO people/);
  assert.match(repository, /hashlib\.sha256\(source_id\.encode\(["']utf-8["']\)\)/);
  assert.match(repository, /INSERT INTO parliamentary_membership_snapshots/);
  assert.match(repository, /VALUES \(\$1, \$2, \$3, \$4, NULL, \$5, \$6, \$7, \$8\)/);
  assert.match(repository, /INSERT INTO data_publication_reviews/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /_insert_decision/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(repository, /except asyncpg\.UniqueViolationError/);
  assert.doesNotMatch(repository, /INSERT INTO\s+mandates/i);
  assert.doesNotMatch(repository, /INSERT INTO\s+parties/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /publishPoliticianProfileSnapshot/);
  assert.match(action, /method: "POST"/);
  assert.match(action, /revalidatePath\("\/politicos"\)/);
  assert.match(page, /fotografia inteira, não uma seleção de perfis/i);
  assert.match(page, /Nenhuma observação será convertida em início, fim ou continuidade de mandato/);
  assert.match(page, /Nenhuma sigla ou nome de grupo será convertido automaticamente em filiação/);
  assert.match(page, /Mandatos ou filiações criados/);
  assert.match(types, /PoliticianProfileSnapshotPublicationPreview/);
  assert.match(types, /PoliticianProfileSnapshotPublicationResult/);

  assert.match(integration, /expected_publication_proof_sha256": "e" \* 64/);
  assert.match(integration, /counts_after_failed_attempt == counts_before_failed_attempt/);
  assert.match(integration, /official_deputy_id not in str\(row\["slug"\]\)/);
  assert.match(integration, /row\["party_id"\] is None/);
  assert.match(integration, /COUNT\(\*\) FROM mandates/);
  assert.match(integration, /PublicPoliticianRepository/);
  assert.match(integration, /"Sem filiação indicada"/);
});

test("V5.30 documentation preserves the boundary between code and real publication", async () => {
  const [documentation, checklist, plan, handoff, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_PROFILE_SNAPSHOT_PUBLICATION.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("docs/PROJECT_HANDOFF.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /fotografia completa/i);
  assert.match(documentation, /`DepId` oficial exato/);
  assert.match(documentation, /uma única transação/i);
  assert.match(documentation, /não cria `Mandate`/i);
  assert.match(documentation, /não associa\s+qualquer partido/i);
  assert.match(documentation, /não executa uma publicação real/i);
  assert.match(documentation, /retirada e republicação/i);
  assert.match(checklist, /\[x\] V5\.30 — publicação transacional da fotografia completa/);
  assert.match(plan, /V5_POLITICIAN_PROFILE_SNAPSHOT_PUBLICATION\.md/);
  assert.match(handoff, /V5\.30/);
  assert.match(readme, /V5\.1 a V5\.33 preparadas/);
  assert.match(readme, /V5_POLITICIAN_PROFILE_SNAPSHOT_PUBLICATION\.md/);
});
