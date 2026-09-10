import assert from "node:assert/strict";
import test from "node:test";
import pg from "pg";
import { resolveDisposableDatabaseTarget } from "../scripts/bootstrap-supabase-test-database.mjs";
import { tableFingerprintQuery } from "../scripts/database-fingerprint.mjs";

test("binary fingerprints detect changed bytes despite unchanged claimed digest", {
  skip: process.env.ENVIRONMENT !== "test" || process.env.CONFIRM_DISPOSABLE_DATABASE !== "true",
}, async () => {
  const target = resolveDisposableDatabaseTarget();
  const client = new pg.Client({ connectionString: target.connectionString, connectionTimeoutMillis: 5000 });
  await client.connect();
  try {
    await client.query("CREATE TEMP TABLE binary_proof (id integer, claimed_digest text, content bytea)");
    await client.query("INSERT INTO binary_proof VALUES (1, 'unchanged', decode(repeat('ab', 16*1024*1024), 'hex'))");
    const query = tableFingerprintQuery({ name: "binary_proof", columns: ["id", "claimed_digest", "content"], bytea_columns: ["content"] }, "pg_temp");
    const fingerprint = async () => (await client.query(query)).rows[0].fingerprint;
    const original = await fingerprint();
    assert.equal(await fingerprint(), original);
    await client.query("UPDATE binary_proof SET content=set_byte(content, 0, 0)");
    assert.notEqual(await fingerprint(), original);
    await client.query("UPDATE binary_proof SET content=NULL");
    const absent = await fingerprint();
    await client.query("UPDATE binary_proof SET content=decode('', 'hex')");
    assert.notEqual(await fingerprint(), absent);
  } finally { await client.end(); }
});
