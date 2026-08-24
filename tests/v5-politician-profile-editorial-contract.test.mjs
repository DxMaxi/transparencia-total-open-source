import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.28 sends one exact deputy observation to a private profile case", async () => {
  const [models, routes, repository, dependencies, actions, page, integration] = await Promise.all([
    source("backend/app/models/editorial.py"),
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/repositories/politician_profile_editorial.py"),
    source("backend/app/api/dependencies.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/page.tsx"),
    source("backend/tests/test_politician_profile_editorial_integration.py"),
  ]);

  assert.match(models, /class PoliticianProfileEditorialProposalRequest/);
  assert.match(models, /confirm_private_only: Literal\[True\]/);
  assert.match(models, /confirm_exact_official_id_only: Literal\[True\]/);
  assert.match(models, /confirm_no_mandate_inference: Literal\[True\]/);
  assert.match(routes, /@router\.get\("\/parliament\/deputies"\)/);
  assert.match(routes, /@router\.post\("\/parliament\/deputy-proposals"/);
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(dependencies, /PoliticianProfileEditorialRepository/);

  assert.match(repository, /source\.publisher = 'PARLIAMENT'/);
  assert.match(repository, /attestation\.content_sha256 = source\.content_sha256/);
  assert.match(repository, /attestation\.retrieved_at = source\.retrieved_at/);
  assert.match(repository, /EditorialCaseKind\.POLITICIAN_PROFILE/);
  assert.match(repository, /subject_type=_SUBJECT_TYPE/);
  assert.match(repository, /origin_alias=_INGESTION_ALIAS/);
  assert.match(repository, /EXACT_AR_DEP_ID_ONLY/);
  assert.match(repository, /"mandate_inference_allowed": False/);
  assert.doesNotMatch(repository, /INSERT INTO (people|mandates|data_publication_reviews)/i);
  assert.doesNotMatch(repository, /INSERT INTO editorial_publication_events/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(actions, /observation_id: observationId/);
  assert.match(actions, /confirm_exact_official_id_only: true/);
  assert.match(actions, /confirm_no_mandate_inference: true/);
  assert.doesNotMatch(actions, /normalized_data:[\s\S]{0,250}deputy-proposals/);
  assert.match(page, /DepId exato, sem correspondência de nomes/);
  assert.match(page, /Aprovar não cria nem publica uma pessoa ou um mandato/);
  assert.match(page, /Limitações e anomalias preservadas/);
  assert.match(page, /esta observação não prova um mandato/);

  assert.match(integration, /people_after == people_before/);
  assert.match(integration, /mandates_after == mandates_before/);
  assert.match(integration, /publication_events == 0/);
  assert.match(integration, /current_state"\] == "PENDING"/);
});

test("V5.28 documentation keeps review separate from identity, mandate and publication", async () => {
  const documentation = await source("docs/V5_POLITICIAN_PROFILE_EDITORIAL.md");
  assert.match(documentation, /`DepId` oficial exato/);
  assert.match(documentation, /não cria `Person`, `Mandate`/);
  assert.match(documentation, /`PENDING`/);
  assert.match(documentation, /não é publicação/);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(documentation, /não existe correspondência\s+aproximada/i);
});
