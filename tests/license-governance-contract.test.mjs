import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

function normalizedSha256(value) {
  const normalized = value.replace(/\r\n?/g, "\n").trim();
  return createHash("sha256").update(normalized, "utf8").digest("hex");
}

test("V5 uses a software-specific noncommercial license and preserves the V4 grant", async () => {
  const [license, historicalMit, contentLicense, licensing, packageJson, pyproject] =
    await Promise.all([
      source("LICENSE"),
      source("LICENSES/MIT-v0.4.0.txt"),
      source("LICENSES/CC-BY-NC-4.0.txt"),
      source("LICENSING.md"),
      source("package.json"),
      source("backend/pyproject.toml"),
    ]);

  const packageMetadata = JSON.parse(packageJson);

  assert.match(license, /^# PolyForm Noncommercial License 1\.0\.0/m);
  assert.match(license, /^Required Notice: Copyright \(c\) 2026 /m);
  assert.doesNotMatch(license, /^MIT License$/m);
  assert.match(historicalMit, /^MIT License$/m);
  assert.match(contentLicense, /^Attribution-NonCommercial 4\.0 International$/m);
  const polyFormTerms = license.replace(
    /^Required Notice: Copyright \(c\) 2026 Colaboradores da Transparência Total \/ Fator Cívico\.\r?\n(?:\r?\n)?/m,
    "",
  );
  assert.equal(
    normalizedSha256(polyFormTerms),
    "7779a554c40798f0f9c04960b82154d16dc0fa64349d401d24146e5c81f64093",
  );
  assert.equal(
    normalizedSha256(contentLicense),
    "db2e35513dbadcdc67f5819a3bfee2777786538dd3531620cd5fbd4b6ed6e538",
  );
  assert.equal(
    normalizedSha256(historicalMit),
    "fefd65c1805498fae21d8deddfa1554fb6f0120bd78f1a22fc7cdfcb29757bf9",
  );
  assert.match(licensing, /até à tag `v0\.4\.0`/);
  assert.match(licensing, /não é uma licença \*open-source\*/i);
  assert.match(licensing, /condições de origem/);
  assert.equal(packageMetadata.version, "0.5.0-alpha.0");
  assert.equal(packageMetadata.license, "PolyForm-Noncommercial-1.0.0");
  assert.match(pyproject, /^version = "0\.5\.0a0"$/m);
  assert.match(pyproject, /^license = "PolyForm-Noncommercial-1\.0\.0"$/m);
});

test("public and contributor copy describes the license scopes without relicensing sources", async () => {
  const [readme, contributing, terms, legalSite] = await Promise.all([
    source("README.md"),
    source("CONTRIBUTING.md"),
    source("app/termos/page.tsx"),
    source("lib/site.ts"),
  ]);

  assert.match(readme, /V5 em desenvolvimento/);
  assert.match(readme, /PolyForm Noncommercial 1\.0\.0/);
  assert.match(readme, /CC BY-NC 4\.0/);
  assert.match(readme, /licença MIT histórica/);
  assert.doesNotMatch(readme, /O código usa licença MIT/);
  assert.match(contributing, /Licença das contribuições/);
  assert.match(contributing, /material de terceiros conservem as respetivas condições/);
  assert.match(terms, /não uma licença\s+open-source/);
  assert.match(terms, /dados oficiais mantêm as condições e direitos/);
  assert.match(legalSite, /11 de agosto de 2026/);
});

test("governance blocks selective interference while retaining lawful correction paths", async () => {
  const governance = await source("docs/GOVERNANCE.md");

  assert.match(governance, /Inexistência de canais privilegiados/);
  assert.match(governance, /prazo legal/);
  assert.match(governance, /pressão económica/);
  assert.match(governance, /obrigação legal ou decisão de autoridade competente/);
  assert.match(governance, /A correção cria uma nova versão/);
  assert.match(governance, /não promete neutralidade absoluta/);
  assert.match(governance, /A IA:/);
  assert.match(governance, /não publica/);
  assert.match(governance, /deve abster-se quando não existam dados suficientes/);
  assert.doesNotMatch(governance, /provar matematicamente/i);
  assert.doesNotMatch(governance, /liminarmente rejeitados/i);
  assert.doesNotMatch(governance, /100% (?:de )?transparência/i);
});

test("published-data exports identify software terms and defer official-data rights to sources", async () => {
  const openDataRoute = await source("backend/app/api/routes/open_data.py");

  assert.match(openDataRoute, /"schema_version": "2\.1"/);
  assert.match(openDataRoute, /"software_license": "PolyForm-Noncommercial-1\.0\.0"/);
  assert.match(openDataRoute, /"project_content_license"/);
  assert.match(openDataRoute, /"reuse_notice"/);
  assert.match(openDataRoute, /condições da entidade de origem/);
  assert.match(openDataRoute, /"X-Data-Reuse": "source-terms-apply"/);
});
