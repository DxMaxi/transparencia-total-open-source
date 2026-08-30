import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("V5.50 creates only a private BASE contract editorial case", async () => {
  const [model, repository, routes, dependencies, integration] =
    await Promise.all([
      read("backend/app/models/editorial.py"),
      read("backend/app/repositories/base_contract_editorial.py"),
      read("backend/app/api/routes/editorial.py"),
      read("backend/app/api/dependencies.py"),
      read("backend/tests/test_base_contract_editorial_integration.py"),
    ]);

  assert.match(model, /class BaseContractEditorialProposalRequest/);
  for (const confirmation of [
    "confirm_private_only",
    "confirm_normalized_batch_consistency",
    "confirm_exact_official_contract_id",
    "confirm_no_party_identity_or_name_matching",
    "confirm_organisations_require_independent_sources",
    "confirm_no_contract_or_relationship_publication",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
  }
  assert.match(repository, /EditorialCaseKind\.PUBLIC_CONTRACT/);
  assert.match(repository, /BASE_CONTRACT_SNAPSHOT/);
  assert.match(repository, /create_ingestion_case/);
  assert.match(repository, /HISTORICAL_CLOSED_YEAR/);
  assert.match(repository, /source_archive_attestations/);
  assert.match(repository, /base_contract_catalogue_resources/);
  assert.match(repository, /actual_contract_count/);
  assert.match(repository, /actual_party_count/);
  assert.match(repository, /_json_object_list/);
  assert.match(repository, /json\.loads\(value\)/);
  assert.match(repository, /archive_byte_size/);
  assert.match(repository, /resource_byte_size/);
  assert.match(repository, /source_retrieved_at[^]*source_modified_at/);
  assert.match(repository, /SPECIFIC_SOURCE_RECORD_ONLY/);
  assert.match(repository, /annual_source_completeness_claimed[^]*False/);
  assert.match(repository, /next_cursor/);
  assert.doesNotMatch(repository, /\bOFFSET\b/);
  assert.match(repository, /protected_identifier_exposed[^]*False/);
  assert.match(repository, /name_or_fuzzy_matching_allowed[^]*False/);
  assert.doesNotMatch(
    repository,
    /INSERT INTO (public_contracts|organisations|interest_entities|contract_match_reviews|interest_relationships)/i,
  );
  assert.doesNotMatch(
    repository,
    /similarity\s*\(|levenshtein\s*\(|rapidfuzz|fuzzywuzzy/i,
  );
  assert.match(routes, /@router\.get\("\/base\/contract-candidates"\)/);
  assert.match(routes, /@router\.post\("\/base\/contract-proposals"/);
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(routes, /cursor: Annotated\[str \| None/);
  assert.match(dependencies, /BaseContractEditorialRepository/);
  assert.match(integration, /dict\(after\) == dict\(before\)/);
  assert.match(integration, /publication_events == 0/);
  assert.match(integration, /current_state"\] == "PENDING"/);
  assert.match(integration, /protected_digest not in json\.dumps/);
  assert.match(integration, /_require_disposable_database/);
  assert.match(integration, /current_database\(\)/);
  assert.match(integration, /45000000-7/);
  assert.match(integration, /123456789\.00/);
  assert.match(integration, /"cases": 1, "versions": 1, "decisions": 1/);
});

test("V5.50 closes generic promotion and requires specific publication events", async () => {
  const [
    legacy,
    postgres,
    reviewScript,
    actions,
    page,
    types,
    docs,
    checklist,
  ] = await Promise.all([
    read("backend/app/repositories/base_promotion.py"),
    read("backend/app/repositories/postgres.py"),
    read("backend/scripts/review_publication.py"),
    read("app/admin/revisao/actions.ts"),
    read("app/admin/revisao/contratos/page.tsx"),
    read("lib/editorial-types.ts"),
    read("docs/V5_BASE_CONTRACT_EDITORIAL.md"),
    read("docs/V5_RELEASE_CHECKLIST.md"),
  ]);

  assert.match(legacy, /promoção BASE genérica foi desativada/);
  assert.doesNotMatch(legacy, /INSERT INTO/);
  assert.match(postgres, /exigem a porta editorial BASE específica/);
  assert.match(reviewScript, /use a porta editorial BASE específica/);
  for (const target of [
    "BASE_PUBLIC_CONTRACT",
    "BASE_INTEREST_ENTITY",
    "BASE_INTEREST_RELATIONSHIP",
  ]) {
    assert.match(postgres, new RegExp(target));
  }
  assert.match(
    postgres,
    /ORDER BY publication\.created_at DESC, publication\.id DESC/,
  );
  for (const confirmation of [
    "confirm_private_only",
    "confirm_normalized_batch_consistency",
    "confirm_exact_official_contract_id",
    "confirm_no_party_identity_or_name_matching",
    "confirm_organisations_require_independent_sources",
    "confirm_no_contract_or_relationship_publication",
  ]) {
    assert.match(actions, new RegExp(`"${confirmation}"`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
  }
  assert.match(types, /type BaseContractEditorialCandidate/);
  assert.match(types, /next_cursor: string \| null/);
  assert.match(types, /filter_required: boolean/);
  assert.match(types, /warnings: string\[\]/);
  assert.match(page, /Uma[^]*organização só pode/);
  assert.match(page, /Entidade adjudicante/);
  assert.match(page, /Adjudicatário/);
  assert.match(page, /Voltar ao início/);
  assert.match(page, /candidate\.catalogue\.byte_size/);
  assert.match(page, /Limitações declaradas pela recolha/);
  assert.match(page, /não\s+assumo\s+cobertura[\s\S]*integral/i);
  assert.match(page, /const exactAmount/);
  assert.doesNotMatch(page, /Number\(value\)/);
  assert.doesNotMatch(page, /next_offset|boundedOffset/);
  assert.match(page, /dados indisponíveis/i);
  assert.match(docs, /zero linhas/);
  assert.match(docs, /não existe similaridade/i);
  assert.match(docs, /não afirma cobertura integral/i);
  assert.match(
    checklist,
    /\[x\] V5\.50 — proposta editorial privada por contrato BASE/,
  );
});
