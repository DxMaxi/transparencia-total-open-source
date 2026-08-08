import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("manifest contains installable PWA essentials", async () => {
  const manifest = JSON.parse(await readFile(new URL("public/manifest.json", root), "utf8"));
  assert.equal(manifest.name, "Transparência Total");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.scope, "/");
  assert.ok(manifest.start_url.startsWith("/"));
  assert.deepEqual(
    manifest.icons.map((icon) => icon.sizes),
    ["192x192", "512x512"],
  );
  assert.ok(manifest.icons.every((icon) => icon.purpose.includes("maskable")));
});

test("generated PNG icons have the dimensions declared in the manifest", async () => {
  for (const size of [192, 512]) {
    const png = await readFile(new URL(`public/icons/icon-${size}.png`, root));
    assert.equal(png.toString("ascii", 1, 4), "PNG");
    assert.equal(png.readUInt32BE(16), size);
    assert.equal(png.readUInt32BE(20), size);
  }
});

test("service worker implements offline and push paths", async () => {
  const worker = await readFile(new URL("public/sw.js", root), "utf8");
  assert.match(worker, /offline\.html/);
  assert.match(worker, /addEventListener\("push"/);
  assert.match(worker, /addEventListener\("notificationclick"/);
  assert.match(worker, /url\.origin !== self\.location\.origin/);
});

test("the public layout does not register device storage without an explicit choice", async () => {
  const layout = await readFile(new URL("app/layout.tsx", root), "utf8");
  assert.doesNotMatch(layout, /PwaRegister/);
  assert.match(layout, /BrowserStorageCleanup/);
  assert.doesNotMatch(layout, /manifest:\s*["']\/manifest\.json/);
});

test("legacy browser storage cleanup is restricted to this project's PWA assets", async () => {
  const cleanup = await readFile(
    new URL("components/browser-storage-cleanup.tsx", root),
    "utf8",
  );
  assert.match(cleanup, /pathname === ["']\/sw\.js["']/);
  assert.match(cleanup, /startsWith\(LEGACY_CACHE_PREFIX\)/);
  assert.doesNotMatch(cleanup, /localStorage|sessionStorage|indexedDB/);
});
