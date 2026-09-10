import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createHash } from "node:crypto";
import { matchesMigrationChecksum } from "../scripts/migration-checksum.mjs";
import { resolveProductionMigrationTarget } from "../scripts/production-migration-target.mjs";

const root = new URL("../", import.meta.url);

test("production migration refuses other projects, transaction pooling and missing authorization", () => {
  const base = {
    ENVIRONMENT: "production",
    CONFIRM_PRODUCTION_SCHEMA_MIGRATION: "MIGRAR-V5",
    EXPECTED_SUPABASE_PROJECT_REF: "kxvgungbqalofbqytwbn",
    DATABASE_URL: "postgresql://postgres:test-only@db.kxvgungbqalofbqytwbn.supabase.co:5432/postgres?sslmode=require",
  };
  assert.equal(resolveProductionMigrationTarget(base).databaseName, "postgres");
  const enforced = resolveProductionMigrationTarget({ ...base,
    DATABASE_URL: base.DATABASE_URL.replace("?sslmode=require", "?schema=public"),
  });
  assert.equal(new URL(enforced.connectionString).searchParams.get("sslmode"), "require");
  assert.equal(new URL(enforced.connectionString).searchParams.has("schema"), false);
  assert.throws(() => resolveProductionMigrationTarget({ ...base, CONFIRM_PRODUCTION_SCHEMA_MIGRATION: "" }));
  for (const url of [
    "postgresql://postgres:test-only@localhost:5432/postgres?sslmode=require",
    "postgresql://postgres:test-only@db.otherproject.supabase.co:5432/postgres?sslmode=require",
    "postgresql://postgres.otherproject:test-only@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require",
    base.DATABASE_URL.replace(":5432/", ":6543/"),
    base.DATABASE_URL.replace("sslmode=require", "sslmode=disable"),
    base.DATABASE_URL.replace("sslmode=require", "sslmode=prefer"),
    base.DATABASE_URL + "&sslmode=disable",
    base.DATABASE_URL + "&ssl=false",
  ]) assert.throws(() => resolveProductionMigrationTarget({ ...base, DATABASE_URL: url }));
  assert.equal(resolveProductionMigrationTarget({ ...base,
    DATABASE_URL: "postgresql://postgres.kxvgungbqalofbqytwbn:test-only@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require",
  }).databaseName, "postgres");
});

test("migration checksums allow historical line endings but reject changed SQL", () => {
  const sql = 'CREATE TABLE "example" (id INT);\n';
  const hash = (value) => createHash("sha256").update(value).digest("hex");
  assert.equal(matchesMigrationChecksum(Buffer.from(sql + "\n"), hash(sql)), true);
  assert.equal(matchesMigrationChecksum(Buffer.from(sql), hash(sql.replaceAll("\n", "\r\n"))), true);
  assert.equal(matchesMigrationChecksum(Buffer.from(sql), hash(sql.replace("INT", "TEXT"))), false);
  assert.equal(matchesMigrationChecksum(Buffer.from(sql), hash(sql + "DROP TABLE example;")), false);
});

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
  assert.match(workflow, /emit_postgres_backup_environment/);
  assert.match(workflow, /docker run --rm --env-file \/dev\/stdin postgres:17/);
  assert.ok(scopeCheckIndex >= 0 && scopeCheckIndex < inventoryIndex);
  assert.ok(scopeCheckIndex < dumpIndex);
  assert.doesNotMatch(workflow, /upload-artifact/);
  assert.doesNotMatch(workflow, /\.dump([^.]|$)(?!\.age)/);
  assert.doesNotMatch(workflow, /docker run[^\n]+-e PGDATABASE/);
  assert.doesNotMatch(workflow, /--dbname[= ]+.*PRODUCTION_DATABASE_URL/);
});

test("restore drill is manual, isolated and checks proof before decrypting", async () => {
  const workflow = await readFile(
    new URL(".github/workflows/database-restore-drill.yml", root),
    "utf8",
  );
  const verifyIndex = workflow.indexOf("verify_database_backup_ciphertext");
  const decryptIndex = workflow.indexOf("bash scripts/restore-public-backup-isolated.sh");
  const scopeCheckIndex = workflow.indexOf("verify_b2_application_key_scope");
  const downloadIndex = workflow.indexOf("aws s3api get-object");
  const ageInstallIndex = workflow.indexOf("sudo apt-get install --yes age");
  const identityCheckIndex = workflow.indexOf('age-keygen -y "$identity_file"');

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
  assert.match(
    workflow,
    /BACKUP_AGE_RECIPIENT: \$\{\{ vars\.BACKUP_AGE_RECIPIENT \}\}/,
  );
  assert.match(workflow, /age-keygen -y "\$identity_file"/);
  assert.match(
    workflow,
    /"\$derived_recipient" != "\$BACKUP_AGE_RECIPIENT"/,
  );
  assert.match(workflow, /não contém uma identidade privada age válida/);
  assert.match(workflow, /não corresponde ao destinatário usado no backup/);
  assert.match(workflow, /trap 'rm -f "\$identity_file"' EXIT/);
  assert.equal(workflow.match(/unset BACKUP_AGE_IDENTITY/g)?.length, 3);
  assert.doesNotMatch(workflow, /echo[^\n]*\$derived_recipient/);
  assert.ok(scopeCheckIndex >= 0 && scopeCheckIndex < downloadIndex);
  assert.ok(ageInstallIndex >= 0 && ageInstallIndex < identityCheckIndex);
  assert.ok(identityCheckIndex >= 0 && identityCheckIndex < downloadIndex);
  assert.ok(identityCheckIndex < decryptIndex);
  assert.ok(verifyIndex >= 0 && verifyIndex < decryptIndex);
  assert.match(workflow, /restore-public-backup-isolated.sh/);
  assert.doesNotMatch(workflow, /BACKUP_AGE_IDENTITY" == \*"AGE-SECRET-KEY-/);
  assert.doesNotMatch(workflow, /PRODUCTION_DATABASE_URL/);
  assert.doesNotMatch(workflow, /schedule:\s*\n/);
});

test("recovery documentation records the EU proof and tested restore", async () => {
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
  assert.match(documentation, /Estado do gate: PASS/i);
  assert.match(documentation, /31313078924/);
  assert.match(documentation, /31318699132/);
  assert.match(
    documentation,
    /ed19814bbc93b3fcd8fff918a2465b52a41b2904e5a23d0ee40bea54a7abd859/,
  );
  assert.doesNotMatch(documentation, /BLOCKED na operação/i);
  assert.match(gitignore, /\*\.agekey/);
  assert.match(gitignore, /\*-backup-age\.key/);
});
