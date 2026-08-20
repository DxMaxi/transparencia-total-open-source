import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  classifyPublicApiError,
  publicApiEndpointLabel,
  PUBLIC_API_REVALIDATE_SECONDS,
  PUBLIC_API_TIMEOUT_MS,
} from "../lib/public-api-policy.ts";

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

test("public API failures are classified and logged without query data", async () => {
  const client = await readFile(new URL("../lib/public-data.ts", import.meta.url), "utf8");

  const timeout = new Error("the raw message must not be logged");
  timeout.name = "TimeoutError";
  const abort = new Error("the raw message must not be logged");
  abort.name = "AbortError";

  assert.equal(classifyPublicApiError(timeout), "timeout");
  assert.equal(classifyPublicApiError(abort), "abort");
  assert.equal(classifyPublicApiError(new TypeError("connection details")), "network");
  assert.equal(classifyPublicApiError(new SyntaxError("response body")), "invalid_json");
  assert.equal(
    publicApiEndpointLabel("/api/v1/public/parliament/explore?q=private-search&cursor=secret"),
    "/api/v1/public/parliament/explore",
  );
  assert.equal(publicApiEndpointLabel("not-an-api-path?token=secret"), "/invalid");
  assert.equal(PUBLIC_API_TIMEOUT_MS, 10_000);
  assert.equal(PUBLIC_API_REVALIDATE_SECONDS, 60);
  assert.match(client, /public_api_fetch_failed/);
  assert.match(client, /retry_policy: "none"/);
  assert.doesNotMatch(client, /error\.message/);
});

test("public status exposes every operational V4 source and its freshness", async () => {
  const [repository, client, card, styles, monitor] = await Promise.all([
    readFile(new URL("../backend/app/repositories/postgres.py", import.meta.url), "utf8"),
    readFile(new URL("../lib/public-data.ts", import.meta.url), "utf8"),
    readFile(new URL("../components/data-status-card.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../.github/workflows/operational-status.yml", import.meta.url), "utf8"),
  ]);

  for (const source of [
    "PARLIAMENT_DEPUTIES",
    "PARLIAMENT_ACTIVITY",
    "PARLIAMENT_VOTES",
    "BASE_CONTRACTS",
    "DRE",
    "TRANSPARENCY_ENTITY",
    "COURT_OF_AUDIT",
    "EUROPEAN_PARLIAMENT",
    "LOCAL_SNS",
  ]) {
    assert.ok(repository.includes(source));
    assert.ok(client.includes(source));
  }
  assert.match(card, /COURT_OF_AUDIT/);
  assert.match(card, /EUROPEAN_PARLIAMENT/);
  assert.doesNotMatch(card, /sources\.slice\(0,\s*7/);

  const cardMaxAge = card.match(/MAX_SOURCE_AGE_HOURS = (\d+);/)?.[1];
  const monitorMaxAge = monitor.match(/V4_SOURCE_MAX_AGE_HOURS:\s*"(\d+)"/)?.[1];
  assert.equal(cardMaxAge, monitorMaxAge);
  assert.match(card, /source\.finishedAt/);
  assert.match(card, /Desatualizado/);
  assert.match(card, /Parcial antigo/);
  assert.match(styles, /\.sync-state--stale/);
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
  assert.match(page, /não é\s+uma agenda completa/i);
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

test("V5.6 profiles expose independent, fail-closed coverage areas", async () => {
  const [client, types, profile, repository, models, reviewScript, documentation] =
    await Promise.all([
      readFile(new URL("../lib/public-data.ts", import.meta.url), "utf8"),
      readFile(new URL("../types/domain.ts", import.meta.url), "utf8"),
      readFile(new URL("../components/politician-profile.tsx", import.meta.url), "utf8"),
      readFile(new URL("../backend/app/repositories/postgres.py", import.meta.url), "utf8"),
      readFile(new URL("../backend/app/models/api.py", import.meta.url), "utf8"),
      readFile(new URL("../backend/scripts/review_publication.py", import.meta.url), "utf8"),
      readFile(new URL("../docs/V5_POLITICIAN_PROFILES.md", import.meta.url), "utf8"),
    ]);

  assert.match(client, /nominal_votes_available:\s*boolean/);
  assert.match(client, /nominal_vote_count:\s*number/);
  assert.match(client, /nominalVotesAvailable:\s*result\.data\.nominal_votes_available/);
  assert.match(client, /nominalVoteCount:\s*result\.data\.nominal_vote_count/);
  assert.match(client, /vote\.is_nominal\s*&&\s*allowedChoices\.has/);
  assert.match(client, /contract_version\?:\s*"v5\.6"/);
  assert.match(client, /membership_observations\?/);
  assert.match(client, /declaration_lookup_source\?/);
  assert.match(client, /legacyProfileCoverage/);
  assert.doesNotMatch(client, /toOfficialSource\(result\.data\.declaration_source\)/);
  assert.doesNotMatch(client, /groupPositions/);
  assert.match(types, /nominalVotesAvailable:\s*boolean/);
  assert.match(types, /nominalVoteCount:\s*number/);
  assert.match(types, /PoliticianProfileCoverage/);
  assert.match(types, /membershipObservations:\s*MembershipObservation\[\]/);
  assert.match(types, /declarations:\s*AssetDeclarationRecord\[\]/);
  assert.match(types, /declarationLookupSource:\s*OfficialLookup/);
  assert.doesNotMatch(types, /groupPositions/);
  assert.doesNotMatch(client, /actor_label\.replace/);
  assert.doesNotMatch(client, /partyKey/);
  assert.match(profile, /profile\.nominalVotesAvailable[\s\S]*profile\.nominalVoteCount/);
  assert.doesNotMatch(profile, /profile\.votes\.filter\([\s\S]*\.length/);
  assert.match(profile, /Cobertura desta ficha/);
  assert.match(profile, /Sem votos individuais publicáveis nesta fotografia/);
  assert.match(profile, /Grupo indicado na fonte/);
  assert.match(profile, /Uma sigla ou um nome semelhante não é suficiente/);
  assert.doesNotMatch(profile, /Posições recentes do grupo/);
  assert.match(profile, /identificador oficial\s+inequívoco/);
  assert.match(repository, /_EXACT_PERSON_VOTE_PARSER_VERSION = "parliament-activity-v5"/);
  assert.match(repository, /candidate\.entity_type = 'MANDATE'/);
  assert.match(repository, /candidate\.entity_type = 'ASSET_DECLARATION'/);
  assert.match(repository, /sd\.publisher = 'TRANSPARENCY_ENTITY'/);
  assert.match(models, /contract_version: Literal\["v5\.6"\]/);
  assert.match(models, /membership_observations: list\[PublishedMembershipObservation\]/);
  assert.match(models, /declarations: list\[PublishedAssetDeclaration\]/);
  assert.match(models, /declaration_lookup_source: PublishedOfficialLookup/);
  assert.match(reviewScript, /"MANDATE"/);
  assert.match(reviewScript, /"ASSET_DECLARATION"/);
  assert.match(reviewScript, /--confirm-legal-basis-reviewed/);
  assert.match(documentation, /não publica nem retira dados reais/i);
  assert.match(documentation, /não existe correspondência aproximada/i);
});
test("Promessómetro marks the editorial catalogue as fallback when the API is unavailable", async () => {
  const client = await readFile(new URL("../lib/public-data.ts", import.meta.url), "utf8");

  assert.match(
    client,
    /if \(result\.ok\) \{\s*return \{ data: initialGovernmentCommitments, status, showingFallback: true \};\s*\}/,
  );
  assert.match(
    client,
    /data: initialGovernmentCommitments,[\s\S]*mode: "UNAVAILABLE"[\s\S]*showingFallback: true/,
  );
});
