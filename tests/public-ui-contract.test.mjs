import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("mobile navigation exposes its controlled region and a reliable hidden state", async () => {
  const header = await readFile(new URL("components/site-header.tsx", root), "utf8");
  const css = await readFile(new URL("app/globals.css", root), "utf8");

  assert.match(header, /aria-controls="mobile-primary-navigation"/);
  assert.match(header, /id="mobile-primary-navigation"/);
  assert.match(header, /hidden={!open}/);
  assert.match(css, /\[hidden\]\s*{\s*display:\s*none\s*!important;/);
});

test("Promessómetro filters expose state and announce a compact result count", async () => {
  const component = await readFile(
    new URL("components/promessometro.tsx", root),
    "utf8",
  );

  assert.match(component, /aria-pressed={activeFilter === filter\.value}/);
  assert.match(component, /className="filter-result-count" role="status"/);
  assert.doesNotMatch(component, /className="promise-list" aria-live=/);
});

test("right-of-reply form sends explicit legitimacy and omits empty optional fields", async () => {
  const component = await readFile(
    new URL("components/right-of-reply-form.tsx", root),
    "utf8",
  );

  assert.match(component, /name="legitimacy_confirmed" value="true" required/);
  assert.match(component, /filter\(\(\[, value\]\) => value !== ""\)/);
  assert.match(component, /aria-describedby="reply-data-minimization-hint"/);
});
