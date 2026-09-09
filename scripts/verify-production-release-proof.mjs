import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const [runPath, migrationPath, roundtripPath] = process.argv.slice(2);
const [run, migration, roundtrip] = await Promise.all(
  [runPath, migrationPath, roundtripPath].map(async (path) => JSON.parse(await readFile(path, "utf8"))),
);
assert.equal(run.conclusion, "success");
assert.equal(run.event, "workflow_dispatch");
assert.equal(run.path, ".github/workflows/database-restore-drill.yml");
assert.equal(run.head_repository.full_name, "DxMaxi/transparencia-total-open-source");
assert.match(run.head_sha, /^[a-f0-9]{40}$/);
const age = Date.now() - Date.parse(run.updated_at);
assert.ok(age >= 0 && age < 24 * 60 * 60 * 1000, "O ensaio tem de ter menos de 24 horas.");
for (const proof of [migration, roundtrip]) {
  assert.equal(proof.outcome, "PASS");
  assert.equal(proof.commit, run.head_sha);
  assert.equal(proof.workflow_run_id, String(run.id));
  assert.equal(proof.production_target_used, false);
  assert.equal(proof.original_content_preserved, true);
  assert.equal(proof.browser_privileges_safe, true);
  assert.equal(proof.row_level_security_verified, true);
  assert.ok(proof.migration_checksums_verified >= 33);
}
console.log(run.head_sha);
