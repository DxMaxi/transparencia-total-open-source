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

test("the sitemap adds only published politician slugs and keeps static routes on API failure", async () => {
  const sitemap = await read("../app/sitemap.ts");

  assert.match(sitemap, /export default async function sitemap/);
  assert.match(sitemap, /loadPublicPoliticians\(\)/);
  assert.match(sitemap, /new Set\(/);
  assert.match(sitemap, /\.map\(\(slug\) => `\/politicos\/\$\{slug\}`\)/);
  assert.match(sitemap, /return \[\.\.\.staticEntries, \.\.\.profileEntries\]/);
  assert.match(sitemap, /politicians\.data/);
  assert.doesNotMatch(sitemap, /loadPublicPolitician\(/);
});

test("public pages declare stable canonical addresses", async () => {
  const pages = [
    ["../app/page.tsx", "/"],
    ["../app/politicos/page.tsx", "/politicos"],
    ["../app/atividade-parlamentar/page.tsx", "/atividade-parlamentar"],
    ["../app/promessas/page.tsx", "/promessas"],
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
  const profile = await read("../app/politicos/[slug]/page.tsx");

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
  assert.match(readme, /V5\.1 a V5\.11 integradas/);
  assert.match(readme, /fundação operacional V5\.12 em preparação local/);
  assert.match(readme, /V5_EDITORIAL_STAGING_EXECUTION_PLAN\.md/);
  assert.match(readme, /V5_STAGING_WORKFLOW_FOUNDATION\.md/);
  assert.match(plan, /V5_EDITORIAL_STAGING_EXECUTION_PLAN\.md/);
  assert.match(plan, /V5_STAGING_WORKFLOW_FOUNDATION\.md/);
  assert.match(readme, /docs\/V5_RELEASE_PLAN\.md/);
  assert.doesNotMatch(readme, /V5\.11 em preparação local/);
});
