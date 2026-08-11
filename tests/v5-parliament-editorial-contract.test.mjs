import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.2 creates scoped private proposals from server-side parliamentary evidence", async () => {
  const [route, repository, editorialRepository, actions, page] = await Promise.all([
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/repositories/parliament_editorial.py"),
    source("backend/app/repositories/editorial.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/page.tsx"),
  ]);

  assert.match(route, /@router\.get\("\/parliament\/snapshots"\)/);
  assert.match(route, /@router\.post\("\/parliament\/proposals"\)/);
  assert.match(route, /Depends\(require_editorial_staff\)/);
  assert.doesNotMatch(route, /@router\.post\("\/parliament\/publish/);

  assert.match(repository, /source\.publisher = 'PARLIAMENT'/);
  assert.match(repository, /attestation\.content_sha256 = source\.content_sha256/);
  assert.match(repository, /attestation\.retrieved_at = source\.retrieved_at/);
  assert.match(repository, /COMPARED_BY_EXACT_SOURCE_ID/);
  assert.match(repository, /manifest_matches/);
  assert.match(repository, /origin_alias=_INGESTION_ALIAS/);
  assert.match(editorialRepository, /origin=EditorialOrigin\.INGESTION/);
  assert.doesNotMatch(repository, /INSERT INTO data_publication_reviews/);
  assert.doesNotMatch(repository, /INSERT INTO editorial_publication_events/);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(actions, /confirm_private_only: true/);
  assert.match(actions, /confirm_no_individual_inference: true/);
  assert.match(actions, /snapshot_id: snapshotId/);
  assert.match(actions, /scope: parliamentScope\(formData\)/);
  assert.doesNotMatch(actions, /normalized_data:[\s\S]{0,200}parliament\/proposals/);

  assert.match(page, /Posições coletivas ou sem/);
  assert.match(page, /nunca são atribuídas a políticos/);
  assert.match(page, /Atores UNKNOWN/);
  assert.match(page, /Sentidos UNKNOWN/);
  assert.match(page, /Fonte recolhida em/);
  assert.match(page, /Manifesto:/);
  assert.match(page, /permanece privada/);
});

test("V5.2 documentation keeps approval and domain publication separate", async () => {
  const documentation = await source("docs/V5_PARLIAMENT_EDITORIAL_ADAPTER.md");
  assert.match(documentation, /O resultado de uma importação é sempre um `EditorialCase` em `PENDING`/);
  assert.match(documentation, /não existe \*fuzzy matching\*/);
  assert.match(documentation, /não[\s\S]*publica, retira ou altera fotografias públicas/);
  assert.match(documentation, /A operação seguinte continua separada desta V5\.2/);
  assert.match(documentation, /O adaptador V5\.3 só[\s\S]*processo `APPROVED`/);
});
