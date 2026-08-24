import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.29 only inspects complete politician profile snapshots behind MFA", async () => {
  const [routes, dependencies, repository, page, types, integration] = await Promise.all([
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/repositories/politician_profile_publication.py"),
    source("app/admin/revisao/parlamento/deputados/prontidao/page.tsx"),
    source("lib/editorial-types.ts"),
    source("backend/tests/test_politician_profile_editorial_integration.py"),
  ]);

  assert.match(routes, /@router\.get\("\/parliament\/deputy-snapshots\/publication-readiness"\)/);
  assert.match(
    routes,
    /@router\.get\("\/parliament\/deputy-snapshots\/\{snapshot_id\}\/publication-readiness"\)/,
  );
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.doesNotMatch(routes, /@router\.post\("\/parliament\/deputy-snapshots/);
  assert.match(dependencies, /PoliticianProfilePublicationReadinessRepository/);

  assert.match(repository, /attestation\.content_sha256 = source\.content_sha256/);
  assert.match(repository, /attestation\.retrieval_url = source\.url/);
  assert.match(repository, /attestation\.retrieved_at = source\.retrieved_at/);
  assert.match(repository, /editorial_case\.current_state/);
  assert.match(repository, /latest_decision\.source_confirmed/);
  assert.match(repository, /EXACT_AR_DEP_ID_ONLY/);
  assert.match(repository, /LEGACY_PUBLICATION_REQUIRES_RECONCILIATION/);
  assert.match(repository, /mandate_inference_allowed/);
  assert.doesNotMatch(repository, /\b(?:INSERT INTO|UPDATE\s+[A-Za-z_]|DELETE FROM)\b/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(types, /PoliticianProfilePublicationReadiness/);
  assert.match(page, /Uma fotografia parcial nunca aparece como uma lista completa/);
  assert.match(page, /Ainda não existe aqui uma ação de publicação/);
  assert.match(page, /não prova omissão nem incumprimento/i);
  assert.doesNotMatch(page, /type="submit"[\s\S]{0,120}public/i);

  assert.match(integration, /pending_readiness\["eligible"\] is False/);
  assert.match(integration, /approved_readiness\["eligible"\] is True/);
  assert.match(integration, /people_after == people_before/);
  assert.match(integration, /mandates_after == mandates_before/);
});

test("V5.29 documentation keeps readiness separate from publication", async () => {
  const documentation = await source(
    "docs/V5_POLITICIAN_PROFILE_PUBLICATION_READINESS.md",
  );
  assert.match(documentation, /fotografia inteira/i);
  assert.match(documentation, /`APPROVED`/);
  assert.match(documentation, /não publica/i);
  assert.match(documentation, /sem correspondência aproximada/i);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(documentation, /reconciliação/i);
});
