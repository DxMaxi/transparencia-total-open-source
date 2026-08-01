import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const allowedHosts = new Set([
  "www.parlamento.pt",
  "parlamento.pt",
  "diariodarepublica.pt",
  "www.diariodarepublica.pt",
  "data.dre.pt",
  "www.tribunalconstitucional.pt",
  "tribunalconstitucional.pt",
  "dados.gov.pt",
  "www.base.gov.pt",
  "base.gov.pt",
  "www.sns.gov.pt",
  "sns.gov.pt",
  "www.tcontas.pt",
  "tcontas.pt",
  "data.europarl.europa.eu",
]);

test("all URLs embedded in demonstration data point to official sources", async () => {
  const source = [
    await readFile(new URL("../lib/demo-data.ts", import.meta.url), "utf8"),
    await readFile(new URL("../lib/v2-demo-data.ts", import.meta.url), "utf8"),
  ].join("\n");
  const urls = [...source.matchAll(/url:\s*"(https:[^"]+)"/g)].map((match) => match[1]);
  assert.ok(urls.length >= 3);
  for (const value of urls) {
    const url = new URL(value);
    assert.equal(url.protocol, "https:");
    assert.ok(allowedHosts.has(url.hostname), `host oficial esperado: ${url.hostname}`);
  }
});

test("the UI labels all sample political data as demonstration", async () => {
  const data = [
    await readFile(new URL("../lib/demo-data.ts", import.meta.url), "utf8"),
    await readFile(new URL("../lib/v2-demo-data.ts", import.meta.url), "utf8"),
  ].join("\n");
  const banner = await readFile(new URL("../components/demo-banner.tsx", import.meta.url), "utf8");
  assert.match(data, /isDemonstration:\s*true/g);
  assert.match(banner, /dados demonstrativos/i);
});
