import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
const approvedStatuses = [
  "UNVERIFIED",
  "NOT_STARTED",
  "IN_PROGRESS",
  "PARTIAL",
  "FULFILLED",
];

test("Promessómetro publishes only the approved V5 vocabulary", async () => {
  const [component, styles, client, domain, apiModel, repository, search] = await Promise.all([
    read("../components/promessometro.tsx"),
    read("../app/globals.css"),
    read("../lib/public-data.ts"),
    read("../types/domain.ts"),
    read("../backend/app/models/api.py"),
    read("../backend/app/repositories/postgres.py"),
    read("../backend/app/repositories/public_search.py"),
  ]);

  for (const status of approvedStatuses) {
    assert.match(component, new RegExp(status));
    assert.match(client, new RegExp(status));
    assert.match(domain, new RegExp(status));
    assert.match(apiModel, new RegExp(status));
    assert.match(repository, new RegExp("'" + status + "'"));
    assert.match(search, new RegExp("'" + status + "'"));
  }

  for (const legacy of ["BROKEN", "ABANDONED"]) {
    assert.doesNotMatch(component, new RegExp(legacy));
    assert.doesNotMatch(client, new RegExp(legacy));
    assert.doesNotMatch(domain, new RegExp(legacy));
    assert.doesNotMatch(apiModel, new RegExp(legacy));
    assert.doesNotMatch(repository, new RegExp("'" + legacy + "'"));
    assert.doesNotMatch(search, new RegExp("'" + legacy + "'"));
  }
  assert.match(repository, /p\.status::text IN/);
  assert.match(search, /promise\.status::text IN/);
  assert.match(styles, /summary-status--not_started/);
  assert.match(styles, /summary-status--partial/);
  assert.doesNotMatch(styles, /summary-status--(?:broken|abandoned)/);
  assert.match(client, /recebeu um estado editorial incompatível/);
  assert.match(client, /mode: "UNAVAILABLE"/);
});

test("the enum migration is additive and never reclassifies historical decisions", async () => {
  const [schema, migration, documentation, checklist] = await Promise.all([
    read("../prisma/schema.prisma"),
    read("../prisma/migrations/20260824023000_v5_promessometro_status_vocabulary/migration.sql"),
    read("../docs/V5_PROMESSOMETRO_VOCABULARY.md"),
    read("../docs/V5_RELEASE_CHECKLIST.md"),
  ]);

  assert.match(schema, /NOT_STARTED/);
  assert.match(schema, /PARTIAL/);
  assert.match(schema, /Valor legado conservado apenas para compatibilidade de migração/);
  assert.match(migration, /ALTER TYPE "PromiseStatus" ADD VALUE IF NOT EXISTS 'NOT_STARTED'/);
  assert.match(migration, /ALTER TYPE "PromiseStatus" ADD VALUE IF NOT EXISTS 'PARTIAL'/);
  assert.doesNotMatch(migration, /(?:UPDATE|DELETE|INSERT)/i);
  assert.match(documentation, /Nunca nasce apenas da ausência de dados/);
  assert.match(documentation, /não reescrever decisões antigas/);
  assert.match(checklist, /Estados públicos limitados ao vocabulário editorial aprovado/);
});

test("the public explanation rejects automatic forecasts and one-document conclusions", async () => {
  const [component, page] = await Promise.all([
    read("../components/promessometro.tsx"),
    read("../app/promessas/page.tsx"),
  ]);

  assert.match(component, /Não são previsões, pontuações automáticas nem opiniões da IA/);
  assert.match(component, /“Não iniciada” nunca resulta apenas da ausência de dados/);
  assert.match(component, /uma\s+lei ou anúncio, por si só, também não prova execução material/);
  assert.match(page, /Cada estado aponta para a prova oficial e para a revisão/);
});
