import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("V5 stabilization never presents a progressive parliamentary total as exact", async () => {
  const page = await read("../app/atividade-parlamentar/page.tsx");

  assert.match(page, /const hasNextPage = explorer\.totalIsExact/);
  assert.match(
    page,
    /explorer\.availability\.explorer && explorer\.totalIsExact && page > pageCount/,
  );
  assert.match(
    page,
    /\? `Página \$\{Math\.min\(currentPage, pageCount\)\} de \$\{pageCount\}`/,
  );
  assert.match(page, /: `Página \$\{currentPage\}`/);
  assert.match(page, /hasNextPage \? <Link href=\{buildHref\(state, currentPage \+ 1\)\}/);
  assert.doesNotMatch(page, /<strong>Página \{Math\.min\(currentPage, pageCount\)\} de/);
});

test("the sitemap adds only published public records and keeps static routes on API failure", async () => {
  const sitemap = await read("../app/sitemap.ts");

  assert.match(sitemap, /export default async function sitemap/);
  assert.match(sitemap, /loadPublicPoliticians\(\)/);
  assert.match(sitemap, /new Set\(/);
  assert.match(sitemap, /\.map\(\(slug\) => `\/politicos\/\$\{slug\}`\)/);
  assert.match(sitemap, /loadPublicAiExplanations\(\{ pageSize: 100 \}\)/);
  assert.match(sitemap, /`\$\{SITE_URL\}\/explicacoes\/\$\{item\.id\}`/);
  assert.match(
    sitemap,
    /return \[\.\.\.staticEntries, \.\.\.profileEntries, \.\.\.explanationEntries\]/,
  );
  assert.match(sitemap, /politicians\.data/);
  assert.doesNotMatch(sitemap, /loadPublicPolitician\(/);
});

test("public pages declare stable canonical addresses", async () => {
  const pages = [
    ["../app/page.tsx", "/"],
    ["../app/politicos/page.tsx", "/politicos"],
    ["../app/atividade-parlamentar/page.tsx", "/atividade-parlamentar"],
    ["../app/promessas/page.tsx", "/promessas"],
    ["../app/explicacoes/page.tsx", "/explicacoes"],
    ["../app/pesquisa/page.tsx", "/pesquisa"],
    ["../app/guia-cidadao/page.tsx", "/guia-cidadao"],
    ["../app/metodologia/page.tsx", "/metodologia"],
    ["../app/direito-de-resposta/page.tsx", "/direito-de-resposta"],
    ["../app/privacidade/page.tsx", "/privacidade"],
    ["../app/cookies/page.tsx", "/cookies"],
    ["../app/termos/page.tsx", "/termos"],
    ["../app/acessibilidade/page.tsx", "/acessibilidade"],
    ["../app/contacto/page.tsx", "/contacto"],
  ];

  const sources = await Promise.all(pages.map(([path]) => read(path)));
  pages.forEach(([, canonical], index) => {
    assert.ok(
      sources[index].includes(`alternates: { canonical: "${canonical}" }`),
      `${canonical} deve declarar a sua URL canónica`,
    );
  });
});

test("politician metadata distinguishes a missing profile from an unavailable API", async () => {
  const [profile, client] = await Promise.all([
    read("../app/politicos/[slug]/page.tsx"),
    read("../lib/public-data.ts"),
  ]);

  assert.match(
    client,
    /if \(result\.status === 404\) \{\s*return \{ data: null, status, showingFallback: false \};\s*\}\s*return \{\s*data: null,\s*status: \{\s*\.\.\.status,\s*mode: "UNAVAILABLE"/,
  );
  assert.match(profile, /loaded\.status\.mode === "UNAVAILABLE"/);
  assert.match(profile, /title: "Perfil temporariamente indisponível"/);
  assert.match(profile, /title: "Página não encontrada"/);
  assert.match(profile, /robots: \{ index: false, follow: false \}/);
  assert.match(profile, /canonical: `\/politicos\/\$\{loaded\.data\.slug\}`/);
  assert.doesNotMatch(profile, /if \(!loaded\.data\) return \{ title: "Perfil político" \}/);
});

test("CI and deployment use one pinned Node major", async () => {
  const [packageSource, lockSource, ci, operations] = await Promise.all([
    read("../package.json"),
    read("../package-lock.json"),
    read("../.github/workflows/ci.yml"),
    read("../.github/workflows/production-operations.yml"),
  ]);
  const packageJson = JSON.parse(packageSource);
  const packageLock = JSON.parse(lockSource);

  assert.equal(packageJson.engines.node, "24.x");
  assert.equal(packageLock.packages[""].engines.node, "24.x");
  assert.match(ci, /node-version: 24/g);
  assert.doesNotMatch(ci, /node-version: 22/);
  assert.match(operations, /node-version: 24/);
});

test("the V5 release gate covers product, editorial, legal and recovery evidence", async () => {
  const [plan, checklist, readme] = await Promise.all([
    read("../docs/V5_RELEASE_PLAN.md"),
    read("../docs/V5_RELEASE_CHECKLIST.md"),
    read("../README.md"),
  ]);

  for (const requirement of [
    "Backend V5 e migrações de produção",
    "Parlamento completo dentro da cobertura declarada",
    "Promessómetro do Programa do XXV Governo",
    "Investigador Cívico",
    "Circuito responsável de IA",
    "Gate de release `v0.5.0`",
  ]) {
    assert.ok(plan.includes(requirement), `plano V5 deve incluir ${requirement}`);
  }
  assert.match(plan, /Não autoriza deploy, migração remota/);
  assert.match(plan, /nenhuma funcionalidade de recolha, revisão ou publicação é ativada implicitamente/i);
  assert.match(checklist, /Backup pós-migração cifrado/);
  assert.match(checklist, /Restauro pós-migração aprovado/);
  assert.match(checklist, /História Git integral pesquisada por segredos/);
  assert.match(readme, /V5\.1 a V5\.42 preparadas/);
  assert.match(readme, /V5\.17 aplica CSP com `nonce` por pedido/);
  assert.match(readme, /ativação remota de staging pendente/);
  assert.match(checklist, /\[x\] V5\.12 — workflow segregado de staging revisto e integrado/);
  assert.match(checklist, /\[x\] Workflow manual de staging integrado/);
  assert.match(readme, /V5_EDITORIAL_STAGING_EXECUTION_PLAN\.md/);
  assert.match(readme, /V5_STAGING_WORKFLOW_FOUNDATION\.md/);
  assert.match(readme, /V5_PUBLIC_QUALITY_GATE\.md/);
  assert.match(readme, /V5_GLOBAL_SEARCH_AND_PERFORMANCE\.md/);
  assert.match(readme, /V5_RELEASE_PRIVACY_AUDIT\.md/);
  assert.match(readme, /V5_PROMESSOMETRO_VOCABULARY\.md/);
  assert.match(readme, /V5_PARLIAMENT_COVERAGE_AND_BACKFILL\.md/);
  assert.match(readme, /V5_PARLIAMENT_SOURCE_CATALOGUE\.md/);
  assert.match(readme, /V5_PARLIAMENT_RESOURCE_MANIFEST\.md/);
  assert.match(readme, /V5_PARLIAMENT_RESOURCE_ARCHIVE\.md/);
  assert.match(readme, /V5_PARLIAMENT_RESOURCE_NORMALIZATION\.md/);
  assert.match(readme, /V5_PARLIAMENT_VOTE_NORMALIZATION\.md/);
  assert.match(readme, /V5_PARLIAMENT_DEPUTY_OBSERVATIONS\.md/);
  assert.match(readme, /V5_POLITICIAN_PROFILE_PUBLICATION_READINESS\.md/);
  assert.match(readme, /V5_POLITICIAN_PROFILE_SNAPSHOT_PUBLICATION\.md/);
  assert.match(readme, /V5_POLITICIAN_MANDATE_WITHDRAWAL\.md/);
  assert.match(plan, /V5_PARLIAMENT_SOURCE_CATALOGUE\.md/);
  assert.match(plan, /V5_PARLIAMENT_RESOURCE_MANIFEST\.md/);
  assert.match(plan, /V5_PARLIAMENT_RESOURCE_ARCHIVE\.md/);
  assert.match(plan, /V5_PARLIAMENT_RESOURCE_NORMALIZATION\.md/);
  assert.match(plan, /V5_PARLIAMENT_VOTE_NORMALIZATION\.md/);
  assert.match(plan, /V5_PARLIAMENT_DEPUTY_OBSERVATIONS\.md/);
  assert.match(checklist, /\[x\] V5\.22 — catálogo privado e versionado/);
  assert.match(checklist, /\[x\] V5\.23 — manifesto privado de XML\/JSON/);
  assert.match(checklist, /\[x\] V5\.24 — arquivo limitado de um recurso exato/);
  assert.match(checklist, /\[x\] V5\.25 — primeira normalização histórica privada/);
  assert.match(checklist, /\[x\] V5\.26 — normalização histórica privada de votações/);
  assert.match(checklist, /\[x\] V5\.27 — observações privadas e versionadas de deputados/);
  assert.match(plan, /V5_EDITORIAL_STAGING_EXECUTION_PLAN\.md/);
  assert.match(plan, /V5_STAGING_WORKFLOW_FOUNDATION\.md/);
  assert.match(readme, /docs\/V5_RELEASE_PLAN\.md/);
  assert.doesNotMatch(readme, /V5\.12 em preparação local/);
});
