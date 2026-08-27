import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.40 publishes one complete attendance meeting in one ADMIN MFA transaction", async () => {
  const [
    schema,
    migration,
    model,
    repository,
    dependencies,
    routes,
    action,
    page,
    integration,
  ] = await Promise.all([
    source("prisma/schema.prisma"),
    source("prisma/migrations/20260827020000_v5_parliament_attendance_publication/migration.sql"),
    source("backend/app/models/editorial.py"),
    source("backend/app/repositories/politician_attendance_publication.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/api/routes/editorial.py"),
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/parlamento/deputados/presencas/page.tsx"),
    source("backend/tests/test_politician_attendance_publication_integration.py"),
  ]);

  for (const field of [
    "attendanceSnapshotId",
    "sourceObservationId",
    "sourceRecordSha256",
  ]) {
    assert.match(schema, new RegExp(field));
  }
  assert.match(schema, /@@unique\(\[attendanceSnapshotId\]\)/);
  assert.match(schema, /@@unique\(\[sourceObservationId\]\)/);
  assert.match(migration, /parliamentary_sessions_snapshot_scope_check/);
  assert.match(migration, /attendance_records_source_bundle_check/);
  assert.match(migration, /attendance_records_source_observation_id_fkey/);
  assert.match(migration, /attendance_records_append_only/);
  assert.match(migration, /ON DELETE RESTRICT/);

  assert.match(model, /class PoliticianAttendancePublicationRequest/);
  for (const confirmation of [
    "confirm_source_reviewed",
    "confirm_complete_meeting",
    "confirm_exact_official_ids_and_mandates_only",
    "confirm_all_statuses_reviewed",
    "confirm_absence_is_not_noncompliance",
    "confirm_append_only_publication",
    "confirm_publication",
  ]) {
    assert.match(model, new RegExp(`${confirmation}: Literal\\[True\\]`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
    assert.match(action, new RegExp(`"${confirmation}"`));
  }
  assert.match(dependencies, /PoliticianAttendancePublicationRepository/);
  assert.match(routes, /attendance-cases\/\{case_id\}\/publication/);
  assert.match(routes, /Depends\(require_editorial_admin\)/);

  assert.match(repository, /pg_advisory_xact_lock/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /WHOLE_MEETING_ONLY/);
  assert.match(repository, /EXACT_AR_BID_ONLY/);
  assert.match(repository, /SOURCE_STATUS_IS_NOT_AUTOMATIC_NONCOMPLIANCE/);
  assert.match(repository, /INSERT INTO parliamentary_sessions/);
  assert.match(repository, /INSERT INTO attendance_records/);
  assert.match(repository, /PARLIAMENT_ATTENDANCE_SNAPSHOT/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /EditorialAction\.PUBLISH/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.match(repository, /attendance_records_to_create/);
  assert.match(repository, /people_to_create": 0/);
  assert.match(repository, /mandates_to_create": 0/);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);
  assert.doesNotMatch(repository, /DELETE FROM (?:attendance_records|parliamentary_sessions)/i);

  assert.match(page, /Publicar reunião completa com prova/);
  assert.match(page, /uma falta não será apresentada como culpa ou incumprimento/i);
  assert.match(integration, /expected_mapping_sha256": "0" \* 64/);
  assert.match(integration, /SELECT COUNT\(\*\) FROM parliamentary_sessions/);
  assert.match(integration, /pytest\.raises\(asyncpg\.PostgresError, match="append-only"\)/);
});

test("V5.40 exposes every published meeting with its own official proof", async () => {
  const [apiModel, publicRepository, publicTypes, publicAdapter, publicProfile] =
    await Promise.all([
      source("backend/app/models/api.py"),
      source("backend/app/repositories/postgres.py"),
      source("types/domain.ts"),
      source("lib/public-data.ts"),
      source("components/politician-profile.tsx"),
    ]);

  assert.match(apiModel, /class PublishedAttendanceRecord/);
  assert.match(apiModel, /source_record_sha256/);
  assert.match(apiModel, /records: list\[PublishedAttendanceRecord\]/);
  assert.match(publicRepository, /published_meetings AS/);
  assert.match(publicRepository, /PARLIAMENT_ATTENDANCE_SNAPSHOT/);
  assert.match(publicRepository, /observation\.official_deputy_id/);
  assert.match(publicRepository, /mandate_review\.publishable = TRUE/);
  assert.match(publicRepository, /Cada linha identifica|respetiva fonte oficial/);
  assert.match(publicTypes, /interface AttendanceMeetingRecord/);
  assert.match(publicAdapter, /recordsComplete/);
  assert.match(publicProfile, /reunião\(ões\) com[\s\S]*prova individual/);
  assert.match(publicProfile, /Registo SHA-256/);
  assert.match(publicProfile, /SourceLink source=\{record\.source\}/);
});

test("V5.40 publication proof remains intact after V5.41 closes withdrawal", async () => {
  const [documentation, checklist, plan, readme] = await Promise.all([
    source("docs/V5_POLITICIAN_ATTENDANCE_PUBLICATION.md"),
    source("docs/V5_RELEASE_CHECKLIST.md"),
    source("docs/V5_RELEASE_PLAN.md"),
    source("README.md"),
  ]);

  assert.match(documentation, /URL oficial/i);
  assert.match(documentation, /data de recolha/i);
  assert.match(documentation, /SHA-256/);
  assert.match(documentation, /append-only/i);
  assert.match(documentation, /não publica dados reais/i);
  assert.match(documentation, /retirada imutável[\s\S]*V5\.41/i);
  assert.match(checklist, /\[x\] V5\.40 — publicação transacional/);
  assert.match(checklist, /\[x\] V5\.41 — retirada transacional e imutável/);
  assert.match(plan, /V5_POLITICIAN_ATTENDANCE_PUBLICATION\.md/);
  assert.match(readme, /V5\.1 a V5\.\d+ preparadas/);
});
