import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  STAGING_OPERATION_CONFIRMATIONS,
  resolveStagingWorkflowRequest,
} from "../scripts/validate-staging-workflow-inputs.mjs";

const PROJECT_REF = "abcdefghijklmnopqrst";
const PRODUCTION_REF = "0123456789abcdefghij";

const environment = (overrides = {}) => ({
  GITHUB_EVENT_NAME: "workflow_dispatch",
  GITHUB_REF: "refs/heads/main",
  GITHUB_REPOSITORY: "DxMaxi/transparencia-total-open-source",
  ENVIRONMENT: "staging",
  REQUESTED_OPERATION: "inventory-read-only",
  REQUESTED_PROJECT_REF: PROJECT_REF,
  REQUESTED_CONFIRMATION: "STAGING-INVENTORY-READ-ONLY",
  STAGING_SUPABASE_PROJECT_REF: PROJECT_REF,
  STAGING_FORBIDDEN_PROJECT_REFS: PRODUCTION_REF,
  SUPABASE_URL: `https://${PROJECT_REF}.supabase.co`,
  STAGING_CORS_ORIGIN: "https://staging.transparenciatotal.pt",
  CORS_ORIGINS: "https://staging.transparenciatotal.pt",
  DATABASE_URL: `postgresql://postgres:private@db.${PROJECT_REF}.supabase.co:5432/postgres?sslmode=require`,
  ...overrides,
});

test("the staging workflow accepts only operation-specific confirmations", () => {
  for (const [operation, confirmation] of Object.entries(STAGING_OPERATION_CONFIRMATIONS)) {
    const request = resolveStagingWorkflowRequest(
      environment({ REQUESTED_OPERATION: operation, REQUESTED_CONFIRMATION: confirmation }),
    );
    assert.equal(request.operation, operation);
    assert.equal(request.projectRef, PROJECT_REF);
    assert.equal(request.dispatchOnly, false);
  }

  assert.throws(
    () => resolveStagingWorkflowRequest(environment({ REQUESTED_CONFIRMATION: "STAGING" })),
    /confirmação exata/,
  );
});

test("dispatch validation fails before requesting staging on another ref or repository", () => {
  const dispatch = resolveStagingWorkflowRequest(environment(), { dispatchOnly: true });
  assert.equal(dispatch.dispatchOnly, true);

  for (const invalid of [
    { GITHUB_EVENT_NAME: "push" },
    { GITHUB_REF: "refs/heads/codex/example" },
    { GITHUB_REPOSITORY: "DxMaxi/fork" },
    { ENVIRONMENT: "production" },
  ]) {
    assert.throws(() =>
      resolveStagingWorkflowRequest(environment(invalid), { dispatchOnly: true }),
    );
  }
});

test("staging environment validation rejects ambiguous or production-like targets", () => {
  for (const invalid of [
    { REQUESTED_PROJECT_REF: PRODUCTION_REF },
    { STAGING_FORBIDDEN_PROJECT_REFS: PROJECT_REF },
    { SUPABASE_URL: `https://${PRODUCTION_REF}.supabase.co` },
    { STAGING_CORS_ORIGIN: "https://www.transparenciatotal.pt" },
    { CORS_ORIGINS: "https://another-staging.example.org" },
    { DATABASE_URL: "" },
  ]) {
    assert.throws(() => resolveStagingWorkflowRequest(environment(invalid)));
  }
});

test("the staging workflow is manual, segregated and inventories before any migration", async () => {
  const [workflow, service, command] = await Promise.all([
    readFile(
      new URL("../.github/workflows/staging-editorial-operations.yml", import.meta.url),
      "utf8",
    ),
    readFile(new URL("../backend/app/services/staging_target.py", import.meta.url), "utf8"),
    readFile(new URL("../backend/scripts/inspect_staging_target.py", import.meta.url), "utf8"),
  ]);
  const inventory = workflow.indexOf("Inventariar o destino antes de qualquer escrita");
  const migration = workflow.indexOf("Aplicar apenas as migrações de esquema");
  const protectedJobGuards = workflow.match(
    /if: \$\{\{ github\.ref == 'refs\/heads\/main' && github\.repository == 'DxMaxi\/transparencia-total-open-source' \}\}/g,
  );

  assert.match(workflow, /workflow_dispatch:/);
  assert.doesNotMatch(workflow, /\n\s+push:|\n\s+schedule:|\n\s+pull_request:/);
  assert.match(workflow, /permissions:\s+contents: read/);
  assert.match(workflow, /environment: staging/);
  assert.equal(protectedJobGuards?.length, 2);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /validate-staging-workflow-inputs\.mjs --dispatch-only/);
  assert.match(workflow, /secrets\.STAGING_DATABASE_URL/);
  assert.match(workflow, /vars\.STAGING_SUPABASE_PROJECT_REF/);
  assert.match(workflow, /STAGING_FORBIDDEN_PROJECT_REFS/);
  assert.doesNotMatch(workflow, /PRODUCTION_|service_role|SUPABASE_SECRET|ADMIN_API_KEY/);
  assert.doesNotMatch(workflow, /vercel\s|deploy --prod|publish|withdraw|sync-/i);
  assert.match(workflow, /npm run db:deploy/);
  assert.doesNotMatch(workflow, /db:migrate|db:seed|prisma migrate dev/);
  assert.ok(inventory >= 0 && migration > inventory);
  assert.doesNotMatch(service, /\.execute\(/);
  assert.match(service, /SHOW transaction_read_only/);
  assert.match(command, /transaction\(readonly=True, isolation="repeatable_read"\)/);
});
