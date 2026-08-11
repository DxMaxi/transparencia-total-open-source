import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.3 publishes only the server-derived approved parliamentary scope", async () => {
  const [route, dependency, repository, v4Gate] = await Promise.all([
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/repositories/parliament_editorial_publication.py"),
    source("backend/app/repositories/parliament_publication.py"),
  ]);

  assert.match(route, /@router\.get\("\/parliament\/cases\/\{case_id\}\/publication"\)/);
  assert.match(route, /@router\.post\("\/parliament\/cases\/\{case_id\}\/publication"\)/);
  assert.match(route, /Depends\(require_editorial_admin\)/);
  assert.doesNotMatch(route, /@router\.post\("\/cases\/\{case_id\}\/publish"\)/);
  assert.match(dependency, /session\.role is not StaffRole\.ADMIN/);
  assert.match(dependency, /Depends\(require_editorial_staff\)/);

  assert.match(repository, /_SCOPES = \{/);
  assert.match(repository, /EditorialState\.APPROVED/);
  assert.match(repository, /str\(case\["origin"\]\) != "INGESTION"/);
  assert.match(repository, /manifest_matches/);
  assert.match(repository, /inconsistent_actor_links/);
  assert.match(repository, /PUBLICATION_PROOF_MISMATCH/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /append_scope_decision/);
  assert.match(repository, /EditorialAction\.PUBLISH/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(v4Gate, /INSERT INTO data_publication_reviews/);
  assert.match(v4Gate, /INSERT INTO audit_events/);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);
});

test("V5.3 panel requires all proofs and never publishes automatically", async () => {
  const [actions, page, types, documentation] = await Promise.all([
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/[case_id]/page.tsx"),
    source("lib/editorial-types.ts"),
    source("docs/V5_PARLIAMENT_SCOPE_PUBLICATION.md"),
  ]);

  for (const confirmation of [
    "confirm_source_reviewed",
    "confirm_no_individual_inference",
    "confirm_publication",
  ]) {
    assert.match(actions, new RegExp(confirmation));
    assert.match(page, new RegExp(confirmation));
  }
  for (const digest of [
    "expected_source_sha256",
    "expected_snapshot_sha256",
    "expected_editorial_sha256",
    "expected_publication_proof_sha256",
  ]) {
    assert.match(actions, new RegExp(digest));
    assert.match(page, new RegExp(digest));
  }
  assert.match(actions, /\/parliament\/cases\/\$\{encodeURIComponent\(id\)\}\/publication/);
  assert.match(page, /staff\.role === "ADMIN"/);
  assert.match(page, /disabled=\{!preview\.eligible\}/);
  assert.match(types, /automatic_publication: false/);
  assert.match(documentation, /uma única transação/);
  assert.match(documentation, /não executa qualquer publicação real/i);
  assert.match(documentation, /PostgreSQL descartável, sem acesso de escrita à produção/i);
});
