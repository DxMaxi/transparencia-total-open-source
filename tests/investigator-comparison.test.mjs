import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
function loadComponent(name) {
  const source = readFileSync(new URL(`../components/${name}.tsx`, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const componentModule = { exports: {} };
  new Function("require", "module", "exports", output)((dependency) => {
    if (dependency === "@/components/interest-graph") return { InterestGraph: () => null };
    if (dependency.startsWith("@/components/")) return loadComponent(dependency.split("/").at(-1));
    return require(dependency);
  }, componentModule, componentModule.exports);
  return componentModule.exports;
}

test("every reviewed pair is rendered with unique headings and no legacy aggregate claims", () => {
  const { InvestigatorWorkbench } = loadComponent("investigator-workbench");
  const source = { url: "https://www.parlamento.pt/test", publisher: "Parlamento", label: "Prova sintética" };
  const comparisons = ["Primeira matéria sintética", "Segunda matéria sintética"].map((subject, index) => ({
    id: `synthetic-${index}`, subject,
    statement: { quote: "Declaração sintética", speaker: "Pessoa sintética", date: "12/09/2026", source },
    vote: { choice: "A favor", initiative: subject, date: "12/09/2026", source },
    // Even an old cached response must not turn a single pair into a person-wide score.
    comparison: { outcome: "CONSISTENT", score: 98, comparablePairs: 999, totalStatements: 1000,
      methodologyVersion: "synthetic-v1", rationale: "Fundamentação sintética" },
  }));
  const html = renderToStaticMarkup(React.createElement(InvestigatorWorkbench, {
    dataset: { nodes: [], edges: [], comparisons },
  }));
  for (const pair of comparisons) assert.ok(html.includes(pair.subject));
  const headingIds = [...html.matchAll(/<h2 id="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(headingIds.length, 2);
  assert.equal(new Set(headingIds).size, 2);
  for (const id of headingIds) assert.ok(html.includes(`aria-labelledby="${id}"`));
  assert.equal((html.match(/Resultado deste par/g) ?? []).length, 2);
  assert.equal((html.match(/Não representa uma avaliação global da pessoa/g) ?? []).length, 2);
  assert.doesNotMatch(html, /98%|999|1000|excluídas por insuficiência|Índice de coerência/);
});
