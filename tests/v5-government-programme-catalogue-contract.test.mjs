import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("V5.48 keeps the complete government programme catalogue private", async () => {
  const [migration, schema, repository, staging, production, manifest] = await Promise.all([
    read("prisma/migrations/20260829183000_v5_government_programme_catalogue_staging/migration.sql"),
    read("prisma/schema.prisma"),
    read("backend/app/repositories/government_programme_staging.py"),
    read(".github/workflows/staging-editorial-operations.yml"),
    read(".github/workflows/production-operations.yml"),
    read("data/xxv-government-programme-catalogue-v2.json"),
  ]);
  const catalogue = JSON.parse(manifest);

  assert.equal(catalogue.expected_candidate_count, 1590);
  assert.equal(catalogue.blocks.length, 40);
  assert.equal(
    catalogue.blocks.reduce((total, block) => total + block.expected_candidate_count, 0),
    1590,
  );
  assert.match(catalogue.source_url, /^https:\/\/portugal\.gov\.pt\//);
  assert.match(catalogue.source_sha256, /^[0-9a-f]{64}$/);
  assert.match(schema, /model GovernmentProgrammeSnapshot/);
  assert.match(schema, /model GovernmentPromiseCandidate/);
  assert.match(migration, /PRIVATE_PENDING_REVIEW/);
  assert.match(migration, /REQUIRES_HUMAN_DEFINITION/);
  assert.match(migration, /PRIVATE_NOT_PUBLISHED/);
  assert.match(migration, /DEFERRABLE INITIALLY DEFERRED/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/g);
  assert.match(migration, /append-only/);
  assert.match(repository, /require_catalogue_schema/);
  assert.match(repository, /public_promises_created["']:\s*0/);
  assert.match(repository, /promise_reviews_created["']:\s*0/);
  assert.doesNotMatch(repository, /INSERT INTO promises\b/);
  assert.doesNotMatch(repository, /INSERT INTO promise_reviews\b/);
  assert.match(staging, /stage-government-programme-catalogue/);
  assert.match(staging, /--confirm-private-staging/);
  assert.doesNotMatch(production, /publish-government-programme/);
});

test("V5.48 pins exact PDF extraction and disables the old publisher", async () => {
  const [requirements, service, removedPublisher] = await Promise.all([
    read("backend/requirements.txt"),
    read("backend/app/services/government_programme_catalogue.py"),
    read("backend/scripts/publish_government_programme.py"),
  ]);

  assert.match(requirements, /^pypdf==6\.10\.0$/m);
  assert.match(service, /source_sha256 != manifest\.source_sha256/);
  assert.match(service, /verify_manifest/);
  assert.match(service, /expected_block_sha256/);
  assert.match(removedPublisher, /Operação V4 desativada/);
  assert.match(removedPublisher, /aprovação e publicação são fases editoriais separadas/);
  assert.doesNotMatch(removedPublisher, /INSERT|PromiseReview|ACCEPT/);
});
