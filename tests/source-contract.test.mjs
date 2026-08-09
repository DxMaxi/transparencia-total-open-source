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
  "portugal.gov.pt",
  "www.portugal.gov.pt",
  "www.base.gov.pt",
  "base.gov.pt",
  "www.sns.gov.pt",
  "sns.gov.pt",
  "transparencia.sns.gov.pt",
  "www.tcontas.pt",
  "tcontas.pt",
  "data.europarl.europa.eu",
]);

test("the government programme catalogue is pinned to an official document", async () => {
  const catalogue = JSON.parse(
    await readFile(new URL("../data/xxv-government-programme.json", import.meta.url), "utf8"),
  );
  const source = new URL(catalogue.sourceUrl);

  assert.equal(source.protocol, "https:");
  assert.ok(allowedHosts.has(source.hostname));
  assert.match(catalogue.sourceSha256, /^[0-9a-f]{64}$/);
  assert.ok(catalogue.sourceByteSize > 1_000_000);
  assert.ok(catalogue.commitments.length >= 10);
});
