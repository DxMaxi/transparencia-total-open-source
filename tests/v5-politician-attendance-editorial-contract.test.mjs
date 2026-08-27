import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.39 archives one complete meeting and creates only a private proposal", async () => {
  const [model, service, repository, editorial, routes, dependencies, action, page, migration] =
    await Promise.all([
      source("backend/app/models/editorial.py"),
      source("backend/app/services/parliament_attendance.py"),
      source("backend/app/repositories/parliament_attendance.py"),
      source("backend/app/repositories/politician_attendance_editorial.py"),
      source("backend/app/api/routes/editorial.py"),
      source("backend/app/api/dependencies.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/parlamento/deputados/presencas/page.tsx"),
      source("prisma/migrations/20260827010000_v5_parliament_attendance_observations/migration.sql"),
    ]);

  assert.match(model, /class PoliticianAttendanceEditorialProposalRequest/);
  for (const confirmation of [
    "confirm_private_only",
    "confirm_complete_meeting",
    "confirm_exact_official_ids_only",
    "confirm_no_name_matching",
    "confirm_absence_is_not_noncompliance",
    "confirm_no_selective_processing",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(action, new RegExp(`"${confirmation}"`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
  }

  assert.match(service, /_MEETING_PATH = "\/deputadogp\/paginas\/detalhereuniaoplenaria\.aspx"/);
  assert.match(service, /_BIOGRAPHY_PATH = "\/deputadogp\/paginas\/biografia\.aspx"/);
  assert.match(service, /MIN_ATTENDANCE_RECORDS = 100/);
  assert.match(service, /MAX_ATTENDANCE_RECORDS = 500/);
  assert.match(service, /ParliamentAttendanceStatus\.UNKNOWN/);
  assert.match(service, /settings\.environment not in \{"test", "staging"\}/);
  assert.match(repository, /archive_raw_document/);
  assert.match(repository, /PARLIAMENT_PLENARY_ATTENDANCE/);
  assert.match(service, /editorial_cases_created": 0/);
  assert.match(service, /publication_performed": False/);
  assert.doesNotMatch(repository, /INSERT INTO (people|mandates|parliamentary_sessions|attendance_records)/i);

  assert.match(routes, /@router\.get\("\/parliament\/attendance-candidates"\)/);
  assert.match(routes, /@router\.post\("\/parliament\/attendance-proposals"/);
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(dependencies, /PoliticianAttendanceEditorialRepository/);
  assert.match(editorial, /PARLIAMENT_ATTENDANCE_SNAPSHOT/);
  assert.match(editorial, /EXACT_AR_BID_ONLY/);
  assert.match(editorial, /WHOLE_MEETING_ONLY/);
  assert.match(editorial, /SOURCE_STATUS_IS_NOT_AUTOMATIC_NONCOMPLIANCE/);
  assert.match(editorial, /official_deputy_id_reference_sha256/);
  assert.doesNotMatch(editorial, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  assert.match(page, /Presença não mede mérito; falta não prova incumprimento/);
  assert.match(page, /cria zero presenças ou sessões públicas/i);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/g);
  assert.match(migration, /reject_parliament_snapshot_mutation/g);
  assert.match(migration, /REVOKE ALL PRIVILEGES/g);
  assert.doesNotMatch(migration, /CREATE POLICY/);
});

test("V5.39 proves idempotence and keeps approval separate from publication", async () => {
  const [integration, script, documentation, checklist, plan, readme, types] = await Promise.all([
    source("backend/tests/test_parliament_attendance_integration.py"),
    source("backend/scripts/sync_parliament_attendance.py"),
    source("docs/V5_POLITICIAN_ATTENDANCE_EDITORIAL.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
    source("lib/editorial-types.ts"),
  ]);

  assert.match(script, /--confirm-private-staging/);
  assert.match(script, /settings\.environment != "staging"/);
  assert.match(integration, /repeated\["snapshot_created"\] is False/);
  assert.match(integration, /after_sessions == before_sessions/);
  assert.match(integration, /after_public_attendance == before_public_attendance/);
  assert.match(integration, /publication_events == 0/);
  assert.match(integration, /current_state"\] == "PENDING"/);
  assert.match(documentation, /URL oficial, data[\s\S]*SHA-256/);
  assert.match(documentation, /não existe fuzzy[\s\S]*matching/i);
  assert.match(documentation, /dados indisponíveis/i);
  assert.match(documentation, /Uma presença prova apenas o estado publicado/);
  assert.match(documentation, /PostgreSQL descartável/);
  assert.match(checklist, /\[x\] V5\.39 — presenças oficiais por reunião/);
  assert.match(plan, /V5_POLITICIAN_ATTENDANCE_EDITORIAL\.md/);
  assert.match(readme, /V5\.1 a V5\.42 preparadas/);
  assert.match(types, /PoliticianAttendanceEditorialCandidate/);
  assert.match(types, /PoliticianAttendanceEditorialProposalResult/);
});
