import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("public frontend never replaces unavailable official data with demonstrations", async () => {
  const client = await readFile(new URL("../lib/public-data.ts", import.meta.url), "utf8");
  const banner = await readFile(new URL("../components/data-mode-banner.tsx", import.meta.url), "utf8");
  assert.match(client, /\/api\/v1\/public\/data-status/);
  assert.match(client, /mode:\s*"UNAVAILABLE"/);
  assert.doesNotMatch(client, /demo-data|v2-demo-data/);
  assert.doesNotMatch(client, /ENABLE_DEMO_DATA/);
  assert.match(banner, /Dados oficiais publicados/);
  assert.match(banner, /Dados oficiais temporariamente indisponíveis/);
  assert.doesNotMatch(banner, /fictícia|demonstrativos/i);
});

test("parliament V4 is snapshot-scoped, reviewed and explicit about partial availability", async () => {
  const repository = await readFile(
    new URL("../backend/app/repositories/public_parliament.py", import.meta.url),
    "utf8",
  );
  const ingestion = await readFile(
    new URL("../backend/app/repositories/parliament_activity.py", import.meta.url),
    "utf8",
  );
  const page = await readFile(
    new URL("../app/atividade-parlamentar/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(repository, /candidate\.entity_id = snapshot\.id/);
  assert.match(repository, /published\.id = session\.snapshot_id/);
  assert.match(repository, /published\.id = initiative\.snapshot_id/);
  assert.match(repository, /published\.id = event\.snapshot_id/);
  assert.doesNotMatch(ingestion, /UPDATE parliamentary_sessions/);
  assert.doesNotMatch(ingestion, /DELETE FROM parliamentary_sessions/);
  assert.match(page, /Consulta parcial/);
  assert.match(page, /não é uma agenda completa/i);
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

test("ingestion paths fail closed without auto-publication", async () => {
  const repository = await readFile(
    new URL("../backend/app/repositories/postgres.py", import.meta.url),
    "utf8",
  );
  const baseRepository = await readFile(
    new URL("../backend/app/repositories/base_staging.py", import.meta.url),
    "utf8",
  );
  const baseScript = await readFile(
    new URL("../backend/scripts/sync_base_contracts.py", import.meta.url),
    "utf8",
  );
  const baseMigration = await readFile(
    new URL(
      "../prisma/migrations/20260803080000_v4_base_staging/migration.sql",
      import.meta.url,
    ),
    "utf8",
  );
  assert.match(repository, /store_parliament_dataset/);
  assert.match(baseRepository, /store_base_collection/);
  assert.match(baseRepository, /archive_receipt: RawArchiveReceipt \| None/);
  assert.match(baseRepository, /copy_records_to_table\(\s*"base_contract_snapshots"/);
  assert.match(baseRepository, /copy_records_to_table\(\s*"base_contract_party_snapshots"/);
  assert.match(repository, /PARLIAMENT_VOTES_SNAPSHOT/);
  assert.match(baseScript, /--confirm-staging/);
  assert.match(baseScript, /ContentAddressedFileArchive\.from_settings/);
  assert.match(baseMigration, /BEFORE UPDATE OR DELETE ON "base_staging_batches"/);
  assert.match(baseMigration, /BEFORE UPDATE OR DELETE ON "base_contract_snapshots"/);
  assert.match(baseMigration, /BEFORE UPDATE OR DELETE ON "base_contract_party_snapshots"/);
  assert.doesNotMatch(repository, /INSERT INTO public_contracts/);
  assert.doesNotMatch(baseRepository, /INSERT INTO public_contracts/);
  assert.doesNotMatch(baseRepository, /INSERT INTO interest_entities/);
  assert.doesNotMatch(baseRepository, /INSERT INTO contract_match_reviews/);
});

test("profiles separate individual votes from collective party positions", async () => {
  const client = await readFile(new URL("../lib/public-data.ts", import.meta.url), "utf8");
  const types = await readFile(new URL("../types/domain.ts", import.meta.url), "utf8");
  const profile = await readFile(
    new URL("../components/politician-profile.tsx", import.meta.url),
    "utf8",
  );

  assert.match(client, /nominal_votes_available:\s*boolean/);
  assert.match(client, /nominal_vote_count:\s*number/);
  assert.match(client, /nominalVotesAvailable:\s*result\.data\.nominal_votes_available/);
  assert.match(client, /nominalVoteCount:\s*result\.data\.nominal_vote_count/);
  assert.match(client, /vote\.is_nominal\s*&&\s*allowedChoices\.has/);
  assert.match(types, /nominalVotesAvailable:\s*boolean/);
  assert.match(types, /nominalVoteCount:\s*number/);
  assert.match(types, /groupPositions:\s*VoteRecord\[\]/);
  assert.match(client, /actor_type !== "PERSON"/);
  assert.match(client, /actor_label\.replace/);
  assert.match(profile, /profile\.nominalVotesAvailable[\s\S]*profile\.nominalVoteCount/);
  assert.doesNotMatch(profile, /profile\.votes\.filter\([\s\S]*\.length/);
  assert.match(profile, /Sem votos individuais publicáveis nesta fonte/);
  assert.match(profile, /Não são votos individuais/);
  assert.match(profile, /Posições recentes do grupo/);
});
