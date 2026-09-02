import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const files = {
  actions: "app/admin/revisao/actions.ts",
  casePage: "app/admin/revisao/[case_id]/page.tsx",
  dependencies: "backend/app/api/dependencies.py",
  migration:
    "prisma/migrations/20260901090000_v5_base_contract_publication/migration.sql",
  models: "backend/app/models/editorial.py",
  package: "package.json",
  postgres: "backend/app/repositories/postgres.py",
  repository: "backend/app/repositories/base_contract_publication.py",
  routes: "backend/app/api/routes/editorial.py",
  schema: "prisma/schema.prisma",
  types: "lib/editorial-types.ts",
};

async function source(name) {
  return readFile(files[name], "utf8");
}

test("V5.51 publication is specific, admin-MFA and excludes every inferred party", async () => {
  const [models, repository, routes, dependencies] = await Promise.all([
    source("models"),
    source("repository"),
    source("routes"),
    source("dependencies"),
  ]);

  assert.match(models, /class BaseContractPublicationRequest/);
  assert.match(models, /confirm_no_party_publication: Literal\[True\]/);
  assert.match(models, /confirm_no_identity_or_name_matching: Literal\[True\]/);
  assert.match(
    models,
    /confirm_no_organisation_match_or_relationship_creation: Literal\[True\]/,
  );
  assert.match(models, /@field_validator\("rationale", "public_rationale"\)/);
  assert.match(models, /fundamentação não pode expor um HMAC protegido/);
  assert.match(repository, /_TARGET_TYPE = "BASE_PUBLIC_CONTRACT"/);
  assert.match(repository, /parties_published": 0/);
  assert.match(repository, /organisations_created": 0/);
  assert.match(repository, /match_reviews_created": 0/);
  assert.match(repository, /relationships_created": 0/);
  assert.doesNotMatch(repository, /INSERT INTO public_contract_parties/);
  assert.doesNotMatch(repository, /INSERT INTO interest_entities/);
  assert.doesNotMatch(repository, /INSERT INTO contract_match_reviews/);
  assert.doesNotMatch(repository, /INSERT INTO interest_relationships/);
  assert.match(
    routes,
    /@router\.post\("\/base\/cases\/\{case_id\}\/publication"\)[\s\S]*?async def publish_base_contract[\s\S]*?Depends\(require_editorial_admin\)/,
  );
  assert.match(
    routes,
    /@router\.post\("\/base\/cases\/\{case_id\}\/withdrawal"\)[\s\S]*?async def withdraw_base_contract[\s\S]*?Depends\(require_editorial_admin\)/,
  );
  assert.match(dependencies, /BaseContractPublicationRepository/);
});

test("V5.51 preserves immutable publication snapshots and withdrawal history", async () => {
  const [migration, schema, repository, models] = await Promise.all([
    source("migration"),
    source("schema"),
    source("repository"),
    source("models"),
  ]);

  assert.match(schema, /model BasePublicContractPublicationSnapshot/);
  assert.match(schema, /currentPublicationSnapshotId String\?\s+@unique/);
  assert.match(migration, /base_public_contract_publication_snapshots/);
  assert.match(migration, /append-only; UPDATE e DELETE são proibidos/);
  assert.match(migration, /BEFORE TRUNCATE/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration, /REVOKE ALL PRIVILEGES/);
  assert.match(migration, /validate_base_public_contract_projection/);
  assert.match(migration, /public_contract_parties_block_v551_mutation/);
  assert.match(migration, /reject_v551_public_contract_party_mutation/);
  assert.match(migration, /public_contracts_validate_base_latest_event/);
  assert.match(migration, /uma republicação exige uma nova fotografia imutável/);
  assert.match(migration, /public_contracts_base_publication_state_check/);
  assert.match(
    migration,
    /current_publication_snapshot_id" IS NULL[\s\S]*publication_status" NOT IN/,
  );
  assert.match(
    models,
    /confirm_history_and_right_of_reply_preserved: Literal\[True\]/,
  );
  assert.match(repository, /right_of_reply_deleted": False/);
  assert.match(repository, /publication_snapshot_deleted": False/);
  assert.match(
    repository,
    /UPDATE public_contracts\s+SET publication_status = 'WITHDRAWN'/s,
  );
  assert.doesNotMatch(repository, /DELETE FROM public_contracts/);
  assert.doesNotMatch(repository, /DELETE FROM rights_of_reply/);
});

test("V5.51 admin UI exposes exact proofs and public queries remain event-gated", async () => {
  const [casePage, actions, types, postgres, packageJson] = await Promise.all([
    source("casePage"),
    source("actions"),
    source("types"),
    source("postgres"),
    source("package"),
  ]);

  assert.match(casePage, /BaseContractPublicationAction/);
  assert.match(casePage, /Nenhuma designação de parte será publicada/);
  assert.match(
    casePage,
    /Não foi usada correspondência por nome, NIF ou fuzzy matching/,
  );
  assert.match(casePage, /BaseContractWithdrawalAction/);
  assert.match(casePage, /Campos exatos da projeção pública/);
  assert.match(casePage, /preview\.public_fields\.object/);
  assert.match(casePage, /preview\.source\.archive_attestation_sha256/);
  assert.match(casePage, /preview\.protected_identifier_count/);
  assert.match(actions, /publishBaseContract/);
  assert.match(actions, /withdrawBaseContract/);
  assert.match(actions, /revalidatePath\("\/investigador"\)/);
  assert.match(types, /type BaseContractPublicationPreview/);
  assert.match(types, /type BaseContractWithdrawalPreview/);
  assert.match(postgres, /publication\.target_type = 'BASE_PUBLIC_CONTRACT'/);
  assert.match(postgres, /contract\.publication_status = 'PUBLISHED'/);
  assert.match(postgres, /contract\.verification_status = 'VERIFIED'/);
  assert.match(postgres, /current_publication_snapshot_id IS NOT NULL/);
  assert.match(postgres, /ARRAY\[\]::jsonb\[\] AS parties/);
  assert.doesNotMatch(
    postgres,
    /LEFT JOIN public_contract_parties p ON p\.public_contract_id = c\.id/,
  );
  assert.match(
    packageJson,
    /tests\/v5-base-contract-publication-contract\.test\.mjs/,
  );
});
