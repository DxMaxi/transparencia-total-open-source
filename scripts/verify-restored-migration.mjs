import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import pg from "pg";
import { resolveDisposableDatabaseTarget } from "./bootstrap-supabase-test-database.mjs";

// Fingerprints stay on the ephemeral runner. Only aggregate outcomes are published.
const quote = (value) => `"${value.replaceAll('"', '""')}"`;
const [operation, snapshotPath, reportPath] = process.argv.slice(2);
assert.ok(["capture", "verify"].includes(operation));
assert.ok(snapshotPath);
const target = resolveDisposableDatabaseTarget();
const client = new pg.Client({ connectionString: target.connectionString });
await client.connect();
try {
  await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY");
  const tables = operation === "capture"
    ? (await client.query(`SELECT table_name AS name, array_agg(column_name::text ORDER BY ordinal_position) AS columns
        FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name <> '_prisma_migrations'
        AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public')
        GROUP BY table_name ORDER BY table_name`)).rows
    : JSON.parse(await readFile(snapshotPath, "utf8"));
  for (const table of tables) {
    // V5 deliberately retires this legacy column, but only when every value is NULL.
    // No other dropped column is exempt from the original-content comparison.
    if (operation === "capture" && table.name === "organisations" && table.columns.includes("public_nipc")) {
      const { rows: [legacy] } = await client.query('SELECT count(*)::text AS count FROM public.organisations WHERE public_nipc IS NOT NULL');
      assert.equal(legacy.count, "0", "Identificadores legados exigem investigação antes da migração");
      table.retired_empty_columns = ["public_nipc"];
      table.columns = table.columns.filter((column) => column !== "public_nipc");
    }
    const { rows: [result] } = await client.query(`SELECT count(*)::text AS count,
      md5(coalesce(string_agg(fingerprint, '' ORDER BY fingerprint COLLATE "C"), '')) AS fingerprint
      FROM (SELECT md5(row_to_json(original)::text) AS fingerprint
        FROM (SELECT ${table.columns.map(quote).join(",")} FROM public.${quote(table.name)}) original) fingerprints`);
    if (operation === "capture") Object.assign(table, result);
    else {
      assert.equal(result.count, table.count, `Contagem alterada: ${table.name}`);
      assert.equal(result.fingerprint, table.fingerprint, `Conteúdo original alterado: ${table.name}`);
    }
  }
  if (operation === "capture") {
    await writeFile(snapshotPath, JSON.stringify(tables), { mode: 0o600 });
  } else {
    assert.ok(reportPath);
    const { rows: [browserRoles] } = await client.query("SELECT count(*)::text AS count FROM pg_roles WHERE rolname IN ('anon','authenticated')");
    assert.equal(browserRoles.count, "2", "Faltam os dois papéis browser para provar isolamento");
    const migrationRoot = new URL("../prisma/migrations/", import.meta.url);
    const expected = (await readdir(migrationRoot, { withFileTypes: true }))
      .filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort();
    const { rows: migrations } = await client.query(`SELECT migration_name, checksum FROM public._prisma_migrations
      WHERE finished_at IS NOT NULL AND rolled_back_at IS NULL ORDER BY migration_name`);
    assert.deepEqual(migrations.map((row) => row.migration_name), expected);
    for (const migration of migrations) {
      const bytes = await readFile(new URL(`${migration.migration_name}/migration.sql`, migrationRoot));
      assert.equal(migration.checksum, createHash("sha256").update(bytes).digest("hex"),
        `Checksum de migração divergente: ${migration.migration_name}`);
    }
    const { rows: unsafeTables } = await client.query(`SELECT c.relname FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p')
      AND c.relname <> '_prisma_migrations' AND (NOT c.relrowsecurity OR EXISTS (
        SELECT 1 FROM pg_roles r WHERE r.rolname IN ('anon','authenticated')
        AND has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))) `);
    assert.equal(unsafeTables.length, 0, "Tabelas sem RLS ou com privilégios browser");
    const { rows: unsafeFunctions } = await client.query(`SELECT p.proname FROM pg_proc p
      JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
        AND d.objid=p.oid AND d.deptype='e')
      AND EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname IN ('anon','authenticated')
        AND has_function_privilege(r.oid,p.oid,'EXECUTE'))`);
    assert.equal(unsafeFunctions.length, 0, "Funções privadas executáveis pelo browser");
    await writeFile(reportPath, JSON.stringify({
      outcome: "PASS", checked_at: new Date().toISOString(),
      commit: process.env.GITHUB_SHA ?? null, workflow_run_id: process.env.GITHUB_RUN_ID ?? null,
      production_target_used: false, original_tables_verified: tables.length,
      original_rows_verified: tables.reduce((sum, table) => sum + Number(table.count), 0),
      original_content_preserved: true, migration_checksums_verified: migrations.length,
      retired_empty_columns_verified: tables.flatMap((table) =>
        (table.retired_empty_columns ?? []).map((column) => `${table.name}.${column}`)),
      browser_privileges_safe: true, row_level_security_verified: true,
      authentication_proven: false,
    }, null, 2) + "\n", { mode: 0o600 });
  }
  await client.query("COMMIT");
  console.log(operation === "capture" ? "Fotografia original preservada no runner efémero." : "Migrações e preservação dos dados: PASS.");
} finally {
  await client.end();
}
