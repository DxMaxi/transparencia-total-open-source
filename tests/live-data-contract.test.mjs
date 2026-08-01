import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("frontend distinguishes live, empty, unavailable and demonstration data", async () => {
  const client = await readFile(new URL("../lib/public-data.ts", import.meta.url), "utf8");
  const banner = await readFile(new URL("../components/data-mode-banner.tsx", import.meta.url), "utf8");
  assert.match(client, /\/api\/v1\/public\/data-status/);
  assert.match(client, /"UNAVAILABLE"\s*:\s*"DEMO"|"UNAVAILABLE"/);
  assert.match(banner, /Dados oficiais publicados/);
  assert.match(banner, /amostra abaixo é fictícia/);
});

test("parliamentary observations are not represented as inferred mandate starts", async () => {
  const schema = await readFile(new URL("../prisma/schema.prisma", import.meta.url), "utf8");
  const migration = await readFile(
    new URL("../prisma/migrations/20260801020000_v3_live_data/migration.sql", import.meta.url),
    "utf8",
  );
  assert.match(schema, /model ParliamentaryMembershipSnapshot/);
  assert.match(schema, /observedAt\s+DateTime/);
  assert.match(migration, /observed_at/);
  assert.doesNotMatch(migration, /started_at/);
});

test("collectors persist into staging without auto-publication", async () => {
  const repository = await readFile(
    new URL("../backend/app/repositories/postgres.py", import.meta.url),
    "utf8",
  );
  assert.match(repository, /store_parliament_dataset/);
  assert.match(repository, /store_base_collection/);
  assert.match(repository, /'INGESTED', 'UNDER_REVIEW'/);
  assert.doesNotMatch(repository, /'VERIFIED', 'PUBLISHED'.*INSERT INTO public_contracts/s);
});
