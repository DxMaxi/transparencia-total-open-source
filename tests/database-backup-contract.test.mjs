import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("daily backup encrypts before B2 and never persists a plaintext dump", async () => {
  const workflow = await readFile(
    new URL(".github/workflows/database-backup.yml", root),
    "utf8",
  );
  const scopeCheckIndex = workflow.indexOf("verify_b2_application_key_scope");
  const inventoryIndex = workflow.indexOf("capture_database_inventory");
  const dumpIndex = workflow.indexOf("pg_dump --format=custom");

  assert.match(workflow, /cron: "17 5 \* \* \*"/);
  assert.match(workflow, /environment: production/);
  assert.match(workflow, /--schema=public/);
  assert.match(workflow, /pg_dump[\s\S]+\| age --recipient/);
  assert.match(workflow, /--object-lock-mode COMPLIANCE/g);
  assert.match(workflow, /get-object-retention/g);
  assert.match(workflow, /eu-central-/);
  assert.match(workflow, /capture_database_inventory/g);
  assert.match(workflow, /build_database_backup_manifest/);
  assert.match(workflow, /--role backup/);
  assert.ok(scopeCheckIndex >= 0 && scopeCheckIndex < inventoryIndex);
  assert.ok(scopeCheckIndex < dumpIndex);
  assert.doesNotMatch(workflow, /upload-artifact/);
  assert.doesNotMatch(workflow, /\.dump([^.]|$)(?!\.age)/);
  assert.doesNotMatch(workflow, /--dbname[= ]+.*PRODUCTION_DATABASE_URL/);
});

test("restore drill is manual, isolated and checks proof before decrypting", async () => {
  const workflow = await readFile(
    new URL(".github/workflows/database-restore-drill.yml", root),
    "utf8",
  );
  const verifyIndex = workflow.indexOf("verify_database_backup_ciphertext");
  const decryptIndex = workflow.indexOf("age --decrypt");
  const scopeCheckIndex = workflow.indexOf("verify_b2_application_key_scope");
  const downloadIndex = workflow.indexOf("aws s3api get-object");

  assert.match(workflow, /workflow_dispatch:/);
  assert.doesNotMatch(workflow, /schedule:/);
  assert.match(workflow, /expected_ciphertext_sha256:/);
  assert.match(workflow, /expected_manifest_sha256:/);
  assert.match(workflow, /inputs\.confirmation == 'RESTAURO'/);
  assert.match(workflow, /environment: recovery/);
  assert.match(workflow, /image: postgres:17/);
  assert.match(workflow, /localhost:5432\/transparencia_restore/);
  assert.match(workflow, /Produção usada como destino: não/);
  assert.match(workflow, /verify_v4_archive/);
  assert.match(workflow, /check_v4_operational_status/);
  assert.match(workflow, /build_database_restore_attestation/);
  assert.match(workflow, /--role restore/);
  assert.ok(scopeCheckIndex >= 0 && scopeCheckIndex < downloadIndex);
  assert.ok(verifyIndex >= 0 && verifyIndex < decryptIndex);
  assert.doesNotMatch(workflow, /PRODUCTION_DATABASE_URL/);
  assert.doesNotMatch(workflow, /schedule:\s*\n/);
});

test("recovery documentation names the EU region, key separation and real gate", async () => {
  const documentation = await readFile(
    new URL("docs/BACKUP_BACKBLAZE_B2.md", root),
    "utf8",
  );
  const gitignore = await readFile(new URL(".gitignore", root), "utf8");

  assert.match(documentation, /EU Central/i);
  assert.match(documentation, /Amesterdão/i);
  assert.match(documentation, /B2_BACKUP_APPLICATION_KEY/);
  assert.match(documentation, /B2_RESTORE_APPLICATION_KEY/);
  assert.match(documentation, /b2 key create/);
  assert.match(
    documentation,
    /readFiles,writeFiles,readFileRetentions,writeFileRetentions/,
  );
  assert.match(documentation, /transparencia-total-restore readFiles/);
  assert.match(documentation, /Read and Write/);
  assert.match(documentation, /deleteFiles/);
  assert.match(documentation, /bypassGovernance/);
  assert.match(documentation, /BACKUP_AGE_IDENTITY/);
  assert.match(documentation, /não.*repositório/i);
  assert.match(documentation, /BLOCKED/);
  assert.match(gitignore, /\*\.agekey/);
  assert.match(gitignore, /\*-backup-age\.key/);
});
