import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.44 withdraws one exact authorship while preserving every historical object", async () => {
  const [
    model,
    repository,
    dependencies,
    routes,
    action,
    page,
    types,
    integration,
    publicRepository,
  ] = await Promise.all([
    source("backend/app/models/editorial.py"),
    source("backend/app/repositories/politician_initiative_authorship_withdrawal.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/api/routes/editorial.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/iniciativas/page.tsx"),
    source("lib/editorial-types.ts"),
    source("backend/tests/test_parliament_initiative_authorship_integration.py"),
    source("backend/app/repositories/postgres.py"),
  ]);

  assert.match(model, /class PoliticianInitiativeAuthorshipWithdrawalRequest/);
  for (const confirmation of [
    "confirm_source_and_publication_reviewed",
    "confirm_exact_authorship",
    "confirm_public_effect_reviewed",
    "confirm_authorship_and_history_preserved",
    "confirm_no_identity_initiative_or_party_change",
    "confirm_no_vote_or_collective_position_inference",
    "confirm_withdrawal",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(action, new RegExp(`"${confirmation}"`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
  }
  assert.match(model, /reason_category: ParliamentWithdrawalReason/);

  assert.match(dependencies, /PoliticianInitiativeAuthorshipWithdrawalRepository/);
  assert.match(
    dependencies,
    /get_politician_initiative_authorship_withdrawal_repository/,
  );
  assert.match(
    routes,
    /@router\.get\("\/parliament\/initiative-authorship-cases\/\{case_id\}\/withdrawal"\)/,
  );
  assert.match(
    routes,
    /@router\.post\([\s\S]*initiative-authorship-cases\/\{case_id\}\/withdrawal[\s\S]*Depends\(require_editorial_admin\)/,
  );

  assert.match(repository, /class PoliticianInitiativeAuthorshipWithdrawalRepository/);
  assert.match(repository, /async def inspect/);
  assert.match(repository, /async def withdraw/);
  assert.match(repository, /actor\.role is not StaffRole\.ADMIN/);
  assert.match(repository, /actor\.assurance_level != "aal2"/);
  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /INSERT INTO data_publication_reviews/);
  assert.match(repository, /POLITICIAN_INITIATIVE_AUTHORSHIP/);
  assert.match(repository, /publishable[\s\S]*FALSE/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /'WITHDRAWN'/);
  assert.match(repository, /EditorialAction\.WITHDRAW/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(repository, /'WITHDRAW'::"EditorialPublicationAction"/);
  assert.match(repository, /authorship_preserved/);
  assert.match(repository, /still_public/);
  assert.match(repository, /confirmed_effect != preview\["public_effect"\]/);
  assert.doesNotMatch(repository, /DELETE FROM politician_initiative_authorships/i);
  assert.doesNotMatch(repository, /UPDATE politician_initiative_authorships/i);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(action, /withdrawPoliticianInitiativeAuthorship/);
  assert.match(action, /expected_withdrawal_proof_sha256/);
  assert.match(action, /expected_public_effect_sha256/);
  assert.match(action, /sucesso: "autoria-retirada"/);
  assert.match(page, /V5\.44 · retirada append-only específica/);
  assert.match(page, /Retirar autoria e preservar histórico/);
  assert.match(page, /Autorias a apagar/);
  assert.match(page, /A retirada exige uma conta ADMIN com MFA/);
  assert.match(types, /PoliticianInitiativeAuthorshipPublicEffect/);
  assert.match(types, /PoliticianInitiativeAuthorshipWithdrawalPreview/);
  assert.match(types, /PoliticianInitiativeAuthorshipWithdrawalResult/);

  assert.match(integration, /invalid_withdrawal_payload/);
  assert.match(integration, /withdrawal_events_before/);
  assert.match(integration, /negative_reviews_before/);
  assert.match(integration, /public_profile_after_withdrawal/);
  assert.match(
    integration,
    /SELECT COUNT\(\*\) FROM politician_initiative_authorships WHERE id = \$1/,
  );
  assert.match(integration, /match="append-only"/);
  assert.match(publicRepository, /entity_type = 'POLITICIAN_INITIATIVE_AUTHORSHIP'/);
  assert.match(publicRepository, /AS review ON review\.publishable = TRUE/);
});

test("V5.44 documents a read-only preview and no real withdrawal", async () => {
  const [documentation, checklist, plan, handoff, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_INITIATIVE_AUTHORSHIP_WITHDRAWAL.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("docs/PROJECT_HANDOFF.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /GET \/api\/v1\/editorial[\s\S]*sem escrever/i);
  assert.match(documentation, /withdrawal_proof_sha256/);
  assert.match(documentation, /public_effect_sha256/);
  assert.match(documentation, /Transação append-only/i);
  assert.match(documentation, /não executa uma retirada real em staging ou produção/i);
  assert.match(documentation, /não associa pessoas por nome ou partido/i);
  assert.match(documentation, /não usa IA como fonte/i);
  assert.match(documentation, /não infere voto, apoio, mérito ou posição coletiva/i);
  assert.match(checklist, /\[x\] V5\.44 — retirada ADMIN\+MFA/);
  assert.match(checklist, /\[x\] Autoria de iniciativas usa relação oficial individual/);
  assert.match(plan, /V5_POLITICIAN_INITIATIVE_AUTHORSHIP_WITHDRAWAL\.md/);
  assert.match(handoff, /A V5\.44 acrescenta a retirada específica e append-only/);
  assert.match(readme, /V5\.1 a V5\.44 preparadas/);
});
