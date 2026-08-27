import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.41 withdraws one whole attendance meeting with ADMIN MFA and no deletion", async () => {
  const [model, repository, dependencies, routes, action, page, integration] =
    await Promise.all([
      source("backend/app/models/editorial.py"),
      source("backend/app/repositories/politician_attendance_withdrawal.py"),
      source("backend/app/api/dependencies.py"),
      source("backend/app/api/routes/editorial.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/parlamento/deputados/presencas/page.tsx"),
      source("backend/tests/test_politician_attendance_publication_integration.py"),
    ]);

  assert.match(model, /class PoliticianAttendanceWithdrawalRequest/);
  for (const confirmation of [
    "confirm_source_and_publication_reviewed",
    "confirm_complete_meeting",
    "confirm_public_effect_reviewed",
    "confirm_session_records_and_history_preserved",
    "confirm_no_selective_person_or_mandate_change",
    "confirm_absence_is_not_noncompliance",
    "confirm_withdrawal",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }
  assert.match(dependencies, /PoliticianAttendanceWithdrawalRepository/);
  assert.match(routes, /attendance-cases\/\{case_id\}\/withdrawal/);
  assert.match(routes, /Depends\(require_editorial_admin\)/);

  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /EditorialAction\.WITHDRAW/);
  assert.match(repository, /EditorialState\.WITHDRAWN/);
  assert.match(repository, /PARLIAMENT_ATTENDANCE_MEETING_HIDDEN_HISTORY_PRESERVED/);
  assert.match(repository, /INSERT INTO data_publication_reviews/);
  assert.match(repository, /FALSE, \$3, \$4, \$5/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /'WITHDRAWN'/);
  assert.match(repository, /'WITHDRAW'::"EditorialPublicationAction"/);
  assert.match(repository, /selective_withdrawal_allowed": False/);
  assert.match(repository, /attendance_records_deleted": 0/);
  assert.doesNotMatch(
    repository,
    /DELETE FROM (?:attendance_records|parliamentary_sessions|people|mandates)/i,
  );
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(page, /Retirar toda a reunião da consulta ativa/);
  assert.match(page, /sem escolher deputados/i);
  assert.match(page, /uma falta não é apresentada como culpa ou incumprimento/i);
  assert.match(integration, /\["PUBLISH", "WITHDRAW"\]/);
  assert.match(integration, /records_preserved.*100/s);
  assert.match(integration, /latest_publishable.*False/s);
});

test("V5.41 closes the attendance gate without activating real data", async () => {
  const [documentation, checklist, plan, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_ATTENDANCE_WITHDRAWAL.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /URL oficial/i);
  assert.match(documentation, /data de recolha/i);
  assert.match(documentation, /SHA-256/);
  assert.match(documentation, /append-only/i);
  assert.match(documentation, /não executa uma retirada real/i);
  assert.match(documentation, /reunião inteira/i);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(checklist, /\[x\] V5\.41 — retirada transacional e imutável/);
  assert.match(plan, /V5_POLITICIAN_ATTENDANCE_WITHDRAWAL\.md/);
  assert.match(readme, /V5\.1 a V5\.41 preparadas/);
  assert.match(readme, /V5_POLITICIAN_ATTENDANCE_WITHDRAWAL\.md/);
});
