import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.32 republishes only through a new immutable profile snapshot", async () => {
  const [integration, publication, withdrawal, publicRepository] = await Promise.all([
    source("backend/tests/test_politician_profile_snapshot_publication_integration.py"),
    source("backend/app/repositories/politician_profile_snapshot_publication.py"),
    source("backend/app/repositories/politician_profile_snapshot_withdrawal.py"),
    source("backend/app/repositories/public_politicians.py"),
  ]);

  assert.match(integration, /PARLIAMENT_DEPUTY_REPUBLICATION_/);
  assert.match(integration, /next_content_sha256/);
  assert.match(integration, /next_snapshot_id/);
  assert.match(integration, /next_observation_id/);
  assert.match(integration, /people_to_reuse_by_exact_depid.*1/s);
  assert.match(integration, /republished\["people_created"\] == 0/);
  assert.match(integration, /republished\["memberships_created"\] == 1/);
  assert.match(integration, /old_state.*WITHDRAWN/s);
  assert.match(integration, /new_state.*PUBLISHED/s);
  assert.match(integration, /old_version_id != next_version_id/);
  assert.match(integration, /\["PUBLISH", "WITHDRAW"\]/);
  assert.match(integration, /next_actions.*\["PUBLISH"\]/s);
  assert.match(integration, /old_snapshot_after_republication\["eligible"\] is False/);

  assert.match(publication, /person\.source_id = observation\.source_id/);
  assert.doesNotMatch(publication, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);
  assert.match(withdrawal, /EditorialState\.WITHDRAWN/);
  assert.match(publicRepository, /latest_sources/);
  assert.match(publicRepository, /latest_review\.publishable = TRUE/);
});

test("V5.32 documents a tested gate without claiming a real republication", async () => {
  const [documentation, checklist, plan, handoff, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_PROFILE_SNAPSHOT_REPUBLICATION.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("docs/PROJECT_HANDOFF.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /nova fotografia imutável/i);
  assert.match(documentation, /nunca volta ao estado ativo/i);
  assert.match(documentation, /DepId.*oficial.*inequívoco/is);
  assert.match(documentation, /zero mandatos e zero ligações[\s\S]*partidárias/i);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(documentation, /não declara que uma fotografia real foi[\s\S]*republicada/i);
  assert.match(checklist, /\[x\] V5\.32 — republicação exige uma nova fonte/);
  assert.match(plan, /V5_POLITICIAN_PROFILE_SNAPSHOT_REPUBLICATION\.md/);
  assert.match(handoff, /V5\.32/);
  assert.match(readme, /V5\.1 a V5\.37 preparadas/);
});
