import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const source = (path) => readFile(new URL(path, root), "utf8");

test("V5.4 withdraws only a published parliamentary scope and preserves history", async () => {
  const [route, repository, model, migration, schema] = await Promise.all([
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/repositories/parliament_editorial_publication.py"),
    source("backend/app/models/editorial.py"),
    source("prisma/migrations/20260811133000_v5_editorial_withdrawal_cycle/migration.sql"),
    source("prisma/schema.prisma"),
  ]);

  assert.match(route, /@router\.get\("\/parliament\/cases\/\{case_id\}\/withdrawal"\)/);
  assert.match(route, /@router\.post\("\/parliament\/cases\/\{case_id\}\/withdrawal"\)/);
  assert.match(route, /Depends\(require_editorial_admin\)/);
  assert.doesNotMatch(route, /@router\.post\("\/cases\/\{case_id\}\/withdraw"\)/);
  assert.match(repository, /publishable=False/);
  assert.match(repository, /EditorialAction\.WITHDRAW/);
  assert.match(repository, /EditorialState\.WITHDRAWN/);
  assert.match(repository, /FALLBACK_TO_PREVIOUS_SNAPSHOT/);
  assert.match(repository, /DATA_UNAVAILABLE/);
  assert.match(repository, /public_effect_sha256/);
  assert.match(repository, /publication_event_sha256/);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);
  assert.match(model, /class ParliamentWithdrawalReason\(StrEnum\)/);
  assert.match(model, /confirm_no_selective_removal: Literal\[True\]/);
  assert.match(migration, /'WITHDRAWN'::"EditorialState"/);
  assert.match(migration, /editorial_publication_events_case_version_action_target_key/);
  assert.match(schema, /@@unique\(\[caseId, versionId, action, targetType, targetId\]\)/);
});

test("V5.4 separates private rationale from the redacted public record", async () => {
  const [actions, page, publicRoute, publicRepository, types, documentation] = await Promise.all([
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/[case_id]/page.tsx"),
    source("backend/app/api/routes/public_data.py"),
    source("backend/app/repositories/public_parliament.py"),
    source("lib/editorial-types.ts"),
    source("docs/V5_PARLIAMENT_WITHDRAWAL.md"),
  ]);

  for (const confirmation of [
    "confirm_no_selective_removal",
    "confirm_public_effect_reviewed",
    "confirm_withdrawal",
  ]) {
    assert.match(actions, new RegExp(confirmation));
    assert.match(page, new RegExp(confirmation));
  }
  for (const proof of [
    "expected_public_review_id",
    "expected_publication_audit_event_id",
    "expected_publication_event_sha256",
    "expected_public_effect_sha256",
  ]) {
    assert.match(actions, new RegExp(proof));
    assert.match(page, new RegExp(proof));
  }
  assert.match(page, /Fundamentação interna completa/);
  assert.match(page, /Resumo público redigido/);
  assert.match(types, /PARLIAMENT_WITHDRAWAL_REASON_LABELS/);
  assert.match(publicRoute, /\/parliament\/publication-history/);
  assert.match(publicRepository, /public_rationale/);
  assert.match(publicRepository, /withdrawal_reason_category/);
  assert.doesNotMatch(publicRepository, /"case_id":/);
  assert.match(documentation, /não executa qualquer retirada real/i);
  assert.match(documentation, /PUBLISHED.*WITHDRAWN.*PENDING/s);
});
