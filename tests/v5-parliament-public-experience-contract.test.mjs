import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("V5.5 explores only a reviewed parliamentary snapshot with bounded filters", async () => {
  const [route, repository, models] = await Promise.all([
    read("../backend/app/api/routes/public_data.py"),
    read("../backend/app/repositories/public_parliament.py"),
    read("../backend/app/models/public_parliament.py"),
  ]);

  assert.match(route, /@router\.get\("\/parliament\/explore"/);
  assert.match(route, /Literal\["sessions", "initiatives", "votes"\]/);
  assert.match(route, /date_from > date_to/);
  assert.match(route, /offset: int = Query\(default=0, ge=0, le=10_000\)/);
  assert.match(repository, /WITH published_snapshot AS/);
  assert.match(repository, /review\.publishable = TRUE/);
  assert.match(repository, /attestation\.content_sha256 = source\.content_sha256/);
  assert.match(repository, /ESCAPE '!'/);
  assert.match(repository, /record\.vote_event_id = ANY\(\$1::text\[\]\)/);
  assert.match(models, /topics_available: Literal\[False\] = False/);
  assert.match(models, /não o deduz por palavras-chave nem por inteligência artificial/);
});

test("V5.5 never links a party or politician by a similar label", async () => {
  const [repository, ingestion, bulkIngestion, sync, client, profile] = await Promise.all([
    read("../backend/app/repositories/public_parliament.py"),
    read("../backend/app/repositories/parliament_activity.py"),
    read("../backend/app/repositories/parliament_activity_bulk.py"),
    read("../backend/scripts/sync_parliament_activity.py"),
    read("../lib/public-data.ts"),
    read("../components/politician-profile.tsx"),
  ]);

  assert.match(repository, /party\.source_id = \$\{len\(arguments\)\}/);
  assert.match(repository, /party\.source_id IS NOT NULL/);
  assert.match(repository, /published\.parser_version = 'parliament-activity-v5'/);
  assert.doesNotMatch(repository, /record\.actor_label\s*=/);
  assert.match(ingestion, /record\.actor_source_id/);
  assert.doesNotMatch(ingestion, /WHERE short_name = \$1 OR source_id = \$1/);
  assert.match(bulkIngestion, /party_source_ids/);
  assert.doesNotMatch(bulkIngestion, /short_name = ANY/);
  assert.match(sync, /CODE_VERSION = "parliament-activity-v5"/);
  assert.doesNotMatch(client, /actor_label\.replace/);
  assert.doesNotMatch(client, /partyKey/);
  assert.doesNotMatch(client, /groupPositions/);
  assert.match(profile, /identificador oficial\s+inequívoco/);
  assert.match(profile, /Uma sigla ou um nome semelhante não é suficiente/);
});

test("V5.5 public UI provides shareable search, filters, pagination and restrained explainers", async () => {
  const [page, client, styles] = await Promise.all([
    read("../app/atividade-parlamentar/page.tsx"),
    read("../lib/public-data.ts"),
    read("../app/globals.css"),
  ]);

  for (const field of [
    "q",
    "tipo",
    "legislatura",
    "de",
    "ate",
    "tipo_iniciativa",
    "estado_iniciativa",
    "resultado",
    "nominal",
    "grupo",
    "posicao",
  ]) {
    assert.match(page, new RegExp(`name=["']${field}["']`));
  }
  assert.match(page, /searchParams: Promise<PageSearchParams>/);
  assert.match(page, /URLSearchParams/);
  assert.match(page, /Paginação dos resultados/);
  assert.match(page, /Temas: dados indisponíveis/);
  assert.match(page, /não é possível determinar entrada em vigor, execução ou impacto material/);
  assert.match(page, /A ausência de resultados não significa incumprimento/);
  assert.match(page, /O que estes números cobrem/);
  assert.match(page, /Não é uma\s+contagem de toda a história parlamentar portuguesa/);
  assert.match(page, /A indisponibilidade da API não é apresentada como zero registos/);
  assert.match(page, /LIMITED_READ_ONLY/);
  assert.match(page, /mesma fotografia oficial revista/);
  assert.doesNotMatch(page, /resultTone/);
  assert.doesNotMatch(page, /parliament-vote-result--positive/);
  assert.match(client, /Promise\.all\(\[/);
  assert.match(client, /\/api\/v1\/public\/parliament\/explore/);
  assert.match(client, /explorer\.status === 404/);
  assert.match(client, /legacyParliamentPath/);
  assert.match(client, /hasAdvancedParliamentFilters/);
  assert.match(client, /showingFallback: false/);
  assert.match(styles, /\.parliament-search-form/);
  assert.match(styles, /\.parliament-page--v551/);
  assert.match(styles, /\.parliament-search-form__primary/);
  assert.match(styles, /@media \(max-width: 720px\)[\s\S]*\.parliament-search-form/);
});
