import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("V5.54 creates only exact private candidates from two active publications", async () => {
  const [model, repository, routes, dependencies, schema, migration] = await Promise.all([
    read("backend/app/models/base_contract_organisation_match.py"),
    read("backend/app/repositories/base_contract_organisation_match.py"),
    read("backend/app/api/routes/editorial.py"),
    read("backend/app/api/dependencies.py"),
    read("prisma/schema.prisma"),
    read("prisma/migrations/20260908090000_v5_exact_contract_party_candidates/migration.sql"),
  ]);

  assert.match(model, /ConfigDict\(extra="forbid", hide_input_in_errors=True\)/);
  assert.equal((model.match(/Literal\[True\]/g) ?? []).length, 6);
  assert.match(model, /confirm_exact_protected_identifier/);
  assert.match(model, /confirm_no_name_or_fuzzy_matching/);
  assert.match(model, /confirm_no_public_party_match_or_relationship/);

  assert.match(repository, /EXACT_PROTECTED_IDENTIFIER/);
  assert.match(repository, /PENDING_REVIEW/);
  assert.match(repository, /protected_identifier_digest = party\.protected_identifier_digest/);
  assert.match(repository, /hmac\.compare_digest/);
  assert.match(repository, /ON CONFLICT \(contract_publication_snapshot_id,/);
  assert.match(repository, /source\.publisher::text = 'BASE_GOV'/);
  assert.match(repository, /organisation_source\.publisher::text = 'JUSTICE_REGISTRY'/);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein|rapidfuzz/i);
  assert.doesNotMatch(repository, /INSERT INTO (?:public_contract_parties|contract_match_reviews|interest_entities|interest_relationships|editorial_publication_events)/i);

  assert.match(schema, /model BaseContractOrganisationMatchCandidate/);
  assert.doesNotMatch(
    schema.match(/model BaseContractOrganisationMatchCandidate[\s\S]*?@@map\("base_contract_organisation_match_candidates"\)/)?.[0] ?? "",
    /protectedIdentifierDigest|fiscalIdentifier|nipc|nif/i,
  );
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration, /base_contract_org_candidates_append_only_truncate/);
  assert.match(migration, /contract_match_reviews_block_v554_materialisation/);
  assert.match(migration, /interest_relationships_block_v554_materialisation/);
  assert.match(migration, /source_archive_attestations_no_truncate/);
  assert.match(migration, /COUNT\(DISTINCT organisation\."id"\)/);
  assert.match(migration, /identity\."protected_identifier_digest" = party\."protected_identifier_digest"/);
  assert.match(migration, /REVOKE ALL ON TABLE public\.base_contract_organisation_match_candidates/);

  assert.match(routes, /@router\.get\("\/base\/contract-organisation-match-candidates"\)/);
  assert.match(routes, /\/base\/contract-organisation-match-candidates[\s\S]*require_editorial_staff/);
  assert.match(dependencies, /BaseContractOrganisationMatchRepository/);
});

test("V5.54 keeps protected identifiers beyond the browser boundary", async () => {
  const [types, actions, page] = await Promise.all([
    read("lib/editorial-types.ts"),
    read("app/admin/revisao/actions.ts"),
    read("app/admin/revisao/contratos/correspondencias/page.tsx"),
  ]);

  assert.match(actions, /createBaseContractOrganisationMatchCandidate/);
  assert.match(actions, /base\/contract-organisation-match-candidates/);
  assert.match(actions, /\^base_contract_\[0-9a-f\]\{64\}\$/);
  assert.match(actions, /confirm_exact_protected_identifier: true/);
  assert.match(actions, /confirm_no_name_or_fuzzy_matching: true/);
  assert.match(actions, /confirm_no_public_party_match_or_relationship: true/);
  assert.doesNotMatch(actions, /formData\.get\(["'](?:nipc|nif|hmac|protected_identifier_digest|score)["']\)/i);

  assert.match(page, /searchParams: Promise/);
  assert.match(page, /Correspondência não é conclusão|correspondência não é uma conclusão/i);
  assert.match(page, /PENDING_REVIEW/);
  assert.match(page, /O identificador fiscal e o respetivo HMAC nunca são enviados ao navegador/i);
  assert.match(page, /Nomes apenas para leitura/i);
  assert.match(page, /candidate_proof_sha256/);
  assert.equal((page.match(/<Confirmation name=/g) ?? []).length, 6);
  assert.match(page, /type="checkbox" required/);
  assert.doesNotMatch(page, /name=["'](?:nipc|nif|hmac|protected_identifier_digest|score)["']/i);

  assert.match(types, /BaseContractOrganisationMatchCandidateList/);
  assert.match(types, /BaseContractOrganisationMatchCandidateResult/);
  const matchTypes = types.match(
    /export type BaseContractOrganisationMatchSourceProof[\s\S]*?export type BaseContractOrganisationMatchCandidateResult[\s\S]*?};/,
  )?.[0] ?? "";
  assert.doesNotMatch(matchTypes, /protected_identifier_digest|identity_observation_id|nipc|nif|hmac|score/i);
});

test("V5.54 is documented as code-only and has zero public effect", async () => {
  const [methodology, readiness, checklist, plan, handoff, readme, packageJson] =
    await Promise.all([
      read("docs/V5_BASE_CONTRACT_ORGANISATION_MATCHING.md"),
      read("docs/V5_OPERATIONAL_READINESS.md"),
      read("docs/V5_RELEASE_CHECKLIST.md"),
      read("docs/V5_RELEASE_PLAN.md"),
      read("docs/PROJECT_HANDOFF.md"),
      read("README.md"),
      read("package.json"),
    ]);

  assert.match(methodology, /Uma igualdade criptográfica exata cria apenas um candidato/);
  assert.match(methodology, /PENDING_REVIEW/);
  assert.match(methodology, /zero efeito público|efeito público igual a zero/i);
  assert.match(methodology, /não ativa staging|não ativam staging/i);
  assert.match(readiness, /V5\.54/);
  assert.match(readiness, /V5\.55/);
  assert.match(checklist, /\[x\] V5\.54/);
  assert.match(plan, /V5\.54/);
  assert.match(handoff, /V5\.55/);
  assert.match(readme, /V5\.1 a V5\.54/);
  assert.match(
    JSON.parse(packageJson).scripts["test:frontend"],
    /v5-base-contract-organisation-match-contract\.test\.mjs/,
  );
});
