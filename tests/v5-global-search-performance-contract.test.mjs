import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("global search is a public projection and never a matching or publication channel", async () => {
  const [route, repository, model, health] = await Promise.all([
    read("../backend/app/api/routes/public_data.py"),
    read("../backend/app/repositories/public_search.py"),
    read("../backend/app/models/public_search.py"),
    read("../backend/app/api/routes/health.py"),
  ]);

  assert.match(route, /@router\.get\("\/search", response_model=PublishedGlobalSearch\)/);
  assert.match(route, /PublicGlobalSearchRepository\(repository\.pool\)\.search/);
  assert.match(route, /available_sections.*== 0/s);
  assert.match(repository, /PublicPoliticianRepository/);
  assert.match(repository, /PublicParliamentRepository/);
  assert.match(repository, /PublicAiExplanationRepository/);
  assert.match(repository, /latest_review\.decision = 'ACCEPT'/);
  assert.match(repository, /source_archive_attestations/);
  assert.doesNotMatch(repository, /similarity\s*\(/i);
  assert.doesNotMatch(repository, /fuzzy/i);
  assert.match(model, /Pesquisar não cria associações, correspondências de identidade/);
  assert.match(health, /"global_search_v1"/);
});

test("the public search interface exposes source, dates, hash and unavailable coverage", async () => {
  const [page, client, types, header] = await Promise.all([
    read("../app/pesquisa/page.tsx"),
    read("../lib/public-data.ts"),
    read("../types/public-data.ts"),
    read("../components/site-header.tsx"),
  ]);

  assert.match(page, /alternates: \{ canonical: "\/pesquisa" \}/);
  assert.match(page, /loadPublicGlobalSearch\(query\)/);
  assert.match(page, /Fonte oficial/);
  assert.match(page, /Recolhida/);
  assert.match(page, /Revista/);
  assert.match(page, /SHA-256 da fonte/);
  assert.match(page, /Não apresentamos listas antigas, exemplos locais ou dados por rever/);
  assert.match(client, /\/api\/v1\/public\/search\?/);
  assert.match(client, /available: false/);
  assert.match(types, /availability: "AVAILABLE" \| "UNAVAILABLE"/);
  assert.match(header, /href="\/pesquisa" aria-label="Pesquisa global"/);
});

test("search is discoverable but query pages are never stored by the offline cache", async () => {
  const [sitemap, worker] = await Promise.all([
    read("../app/sitemap.ts"),
    read("../public/sw.js"),
  ]);

  assert.match(sitemap, /"\/pesquisa"/);
  assert.match(worker, /"\/pesquisa"/);
  assert.match(worker, /if \(url\.search\) return false/);
});

test("mobile performance uses three Lighthouse runs and fact-based budgets", async () => {
  const [script, workflow, packageSource] = await Promise.all([
    read("../scripts/check-mobile-performance.mjs"),
    read("../.github/workflows/ci.yml"),
    read("../package.json"),
  ]);
  const packageJson = JSON.parse(packageSource);

  assert.equal(packageJson.devDependencies.lighthouse, "13.4.1");
  assert.equal(packageJson.devDependencies["chrome-launcher"], "1.2.1");
  assert.equal(packageJson.scripts["performance:mobile"], "node scripts/check-mobile-performance.mjs");
  assert.match(script, /const numberOfRuns = 3/);
  assert.match(script, /"\/atividade-parlamentar", "\/pesquisa"/);
  assert.match(script, /performanceScore: \{ minimum: 0\.9/);
  assert.match(script, /largestContentfulPaint: \{ maximum: 3_500/);
  assert.match(script, /totalBlockingTime: \{ maximum: 350/);
  assert.match(script, /cumulativeLayoutShift: \{ maximum: 0\.1/);
  assert.match(script, /totalBytes: \{ maximum: 400_000/);
  assert.match(script, /median\(results\.map/);
  assert.match(workflow, /npm run performance:mobile/);
  assert.match(workflow, /lighthouse-diagnostics/);
});

test("Promessómetro receives global query links and exposes stable record anchors", async () => {
  const [page, component] = await Promise.all([
    read("../app/promessas/page.tsx"),
    read("../components/promessometro.tsx"),
  ]);

  assert.match(page, /searchParams: Promise<SearchParams>/);
  assert.match(page, /initialQuery=\{query\}/);
  assert.match(page, /Catálogo publicado/);
  assert.match(component, /Pesquisar no catálogo publicado/);
  assert.match(component, /id=\{`promessa-\$\{promise\.id\}`\}/);
});
