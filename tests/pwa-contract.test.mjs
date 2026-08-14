import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
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

test("service worker caches only public, explicitly cacheable resources", async () => {
  const worker = await readFile(new URL("public/sw.js", root), "utf8");
  assert.match(worker, /CACHE_PREFIX = "transparencia-total-"/);
  assert.match(worker, /PRIVATE_PATH_PREFIXES = \["\/admin", "\/auth", "\/api"\]/);
  assert.match(worker, /request\.headers\.has\("authorization"\)/);
  assert.match(worker, /private\|no-store/);
  assert.match(worker, /key\.startsWith\(CACHE_PREFIX\)/);
  assert.match(worker, /safeNotificationTarget/);
  assert.match(worker, /target\.origin !== self\.location\.origin/);
  assert.match(worker, /addEventListener\("push"/);
  assert.match(worker, /addEventListener\("notificationclick"/);
});

test("offline mode is an explicit reversible choice", async () => {
  const layout = await readFile(new URL("app/layout.tsx", root), "utf8");
  const footer = await readFile(new URL("components/site-footer.tsx", root), "utf8");
  const controls = await readFile(new URL("components/pwa-controls.tsx", root), "utf8");

  assert.match(layout, /manifest:\s*["']\/manifest\.json/);
  assert.doesNotMatch(layout, /BrowserStorageCleanup|PwaRegister/);
  assert.match(footer, /<PwaControls \/>/);
  assert.match(controls, /onClick={enableOfflineMode}/);
  assert.match(controls, /navigator\.serviceWorker\.register\("\/sw\.js"/);
  assert.match(controls, /registration\.unregister\(\)/);
  assert.match(controls, /key\.startsWith\(PROJECT_CACHE_PREFIX\)/);
  assert.doesNotMatch(controls, /localStorage|sessionStorage|indexedDB/);
});

test("obsolete automatic registration and cleanup components are removed", async () => {
  await assert.rejects(access(new URL("components/pwa-register.tsx", root)));
  await assert.rejects(access(new URL("components/browser-storage-cleanup.tsx", root)));
});
