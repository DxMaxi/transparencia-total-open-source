import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("V5.49 defines an exact private temporal scope for Portal BASE", async () => {
  const [manifestText, service, repository, migration, workflow, validator] = await Promise.all([
    read("data/base-contracts-scope-v1.json"),
    read("backend/app/services/base_catalogue_scope.py"),
    read("backend/app/repositories/base_catalogue_staging.py"),
    read("prisma/migrations/20260830090000_v5_base_temporal_scope/migration.sql"),
    read(".github/workflows/staging-editorial-operations.yml"),
    read("scripts/validate-staging-workflow-inputs.mjs"),
  ]);
  const manifest = JSON.parse(manifestText);

  assert.equal(manifest.dataset_id, "66d72d488ca4b7cb2de28712");
  assert.equal(manifest.first_year, 2012);
  assert.equal(manifest.resource_format, "ZIP");
  assert.equal(manifest.licence_code, "other-pd");
  assert.equal(manifest.update_frequency, "weekly");
  assert.match(service, /CURRENT_ROLLING_YEAR/);
  assert.match(service, /HISTORICAL_CLOSED_YEAR/);
  assert.match(service, /Dados indisponíveis/);
  assert.match(service, /verify_base_catalogue_scope/);
  assert.match(repository, /publication_eligible[^\n]+False/);
  assert.doesNotMatch(repository, /INSERT INTO public_contracts/);
  assert.doesNotMatch(repository, /INSERT INTO interest_relationships/);
  assert.doesNotMatch(repository, /INSERT INTO contract_match_reviews/);
  assert.match(migration, /append-only/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/g);
  assert.match(migration, /DEFERRABLE INITIALLY DEFERRED/g);
  assert.doesNotMatch(migration, /INSERT INTO "public_contracts"/);
  assert.match(workflow, /stage-base-catalogue-scope/);
  assert.match(validator, /STAGING-STAGE-BASE-CATALOGUE-SCOPE/);
});

test("V5.49 staging command is fail-closed and separate from contract ingestion", async () => {
  const script = await read("backend/scripts/stage_base_catalogue_scope.py");

  assert.match(script, /ENVIRONMENT tem de ser staging/);
  assert.match(script, /validate_staging_target/);
  assert.match(script, /require_scope_schema/);
  assert.match(script, /archive_raw_document/);
  assert.match(script, /--confirm-private-staging/);
  assert.doesNotMatch(script, /BaseGovCollector/);
  assert.doesNotMatch(script, /store_base_collection/);
});
