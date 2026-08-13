import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { resolveDisposableDatabaseTarget } from "../scripts/bootstrap-supabase-test-database.mjs";

const root = process.cwd();
const source = (relativePath) => readFile(path.join(root, relativePath), "utf8");

test("the Supabase test bootstrap accepts only an explicitly confirmed local test database", () => {
  const accepted = resolveDisposableDatabaseTarget({
    ENVIRONMENT: "test",
    CONFIRM_DISPOSABLE_DATABASE: "true",
    DATABASE_URL:
      "postgresql://postgres:postgres@localhost:5432/transparencia_total_test?schema=public",
  });
  assert.equal(accepted.databaseName, "transparencia_total_test");
  assert.doesNotMatch(accepted.connectionString, /schema=public/);

  for (const environment of [
    {
      ENVIRONMENT: "production",
      CONFIRM_DISPOSABLE_DATABASE: "true",
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/transparencia_total_test",
    },
    {
      ENVIRONMENT: "test",
      CONFIRM_DISPOSABLE_DATABASE: "false",
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/transparencia_total_test",
    },
    {
      ENVIRONMENT: "test",
      CONFIRM_DISPOSABLE_DATABASE: "true",
      DATABASE_URL: "postgresql://postgres:postgres@db.example.org:5432/transparencia_total_test",
    },
    {
      ENVIRONMENT: "test",
      CONFIRM_DISPOSABLE_DATABASE: "true",
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/transparencia_total",
    },
  ]) {
    assert.throws(() => resolveDisposableDatabaseTarget(environment));
  }
});

test("CI creates the Supabase-shaped disposable database before Prisma migrations", async () => {
  const [workflow, bootstrap] = await Promise.all([
    source(".github/workflows/ci.yml"),
    source("scripts/bootstrap-supabase-test-database.mjs"),
  ]);

  const bootstrapStep = workflow.indexOf("npm run db:test:bootstrap-supabase");
  const migrationStep = workflow.indexOf("npm run db:deploy");
  assert.ok(bootstrapStep >= 0 && migrationStep > bootstrapStep);
  assert.match(workflow, /CONFIRM_DISPOSABLE_DATABASE: "true"/);
  assert.match(bootstrap, /CREATE ROLE anon NOLOGIN/);
  assert.match(bootstrap, /CREATE ROLE authenticated NOLOGIN/);
  assert.match(bootstrap, /CREATE TABLE IF NOT EXISTS auth\.users/);
  assert.match(bootstrap, /auth\.tt_disposable_test_marker/);
});

test("the staging inspector is read-only and keeps operational Auth gates explicit", async () => {
  const [service, command, documentation] = await Promise.all([
    source("backend/app/services/editorial_staging_readiness.py"),
    source("backend/scripts/inspect_editorial_staging_readiness.py"),
    source("docs/V5_EDITORIAL_STAGING_READINESS.md"),
  ]);

  assert.doesNotMatch(service, /\.execute\(/);
  assert.match(command, /--confirm-read-only/);
  assert.match(command, /settings\.environment != "staging"/);
  assert.match(command, /transaction\(readonly=True/);
  assert.match(documentation, /não configura o Supabase/i);
  assert.match(documentation, /não prova.*registo público.*desativado/is);
  assert.match(documentation, /PENDING.*IN_REVIEW.*APPROVED/s);
});
