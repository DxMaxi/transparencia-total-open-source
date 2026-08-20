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
  assert.match(worker, /PUBLIC_PAGE_PATHS/);
  assert.match(worker, /PUBLIC_ASSET_PREFIXES/);
  assert.match(worker, /PUBLIC_RECORD_PREFIXES/);
  assert.match(worker, /isExplicitlyCacheablePath/);
  assert.match(worker, /if \(url\.search\) return false/);
  assert.match(worker, /OFFLINE_PREFERENCE_CACHE/);
  assert.match(worker, /ENABLE_OFFLINE/);
  assert.match(worker, /if \(!offlineModeEnabled\) return/);
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
  assert.match(layout, /id="conteudo" tabIndex=\{-1\}/);
  assert.doesNotMatch(layout, /BrowserStorageCleanup|PwaRegister/);
  assert.match(footer, /<PwaControls \/>/);
  assert.match(controls, /onClick={enableOfflineMode}/);
  assert.match(controls, /navigator\.serviceWorker\.register\("\/sw\.js"/);
  assert.match(controls, /sendOfflineCommand\(registration, "ENABLE_OFFLINE"\)/);
  assert.match(controls, /OFFLINE_PREFERENCE_CACHE/);
  assert.match(controls, /registration\.unregister\(\)/);
  assert.match(controls, /key\.startsWith\(PROJECT_CACHE_PREFIX\)/);
  assert.doesNotMatch(controls, /localStorage|sessionStorage|indexedDB/);
});

test("push alerts require informed consent and can be updated or erased", async () => {
  const [home, component, route, repository, apiMain, proxy, gitignore] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("components/push-subscribe.tsx", root), "utf8"),
    readFile(new URL("backend/app/api/routes/push.py", root), "utf8"),
    readFile(new URL("backend/app/repositories/postgres.py", root), "utf8"),
    readFile(new URL("backend/app/main.py", root), "utf8"),
    readFile(new URL("proxy.ts", root), "utf8"),
    readFile(new URL(".gitignore", root), "utf8"),
  ]);

  assert.match(home, /<PushSubscribe \/>/);
  assert.match(component, /type="checkbox"/);
  assert.match(component, /Notification\.requestPermission\(\)/);
  assert.ok(
    component.indexOf("if (!consent)")
      < component.indexOf("Notification.requestPermission()"),
  );
  assert.match(component, /navigator\.serviceWorker\.register\("\/sw\.js"/);
  assert.match(component, /method: "DELETE"/);
  assert.match(component, /subscription\.unsubscribe\(\)/);
  assert.match(component, /subscriptionRegistration\.unregister\(\)/);
  assert.match(component, /keepForOffline/);
  assert.match(component, /removal-pending/);
  assert.match(component, /backendRemoved \? "idle" : "removal-pending"/);
  assert.match(component, /Desativar e apagar alertas/);
  assert.match(component, /Só conteúdo aprovado pode originar um alerta/);
  assert.match(route, /@router\.delete\("\/subscriptions"/);
  assert.match(route, /PUSH_SUBSCRIPTION_POLICY/);
  assert.match(route, /get_publishable_push_alert\(payload\.alert_id\)/);
  assert.doesNotMatch(route, /payload\.title/);
  assert.doesNotMatch(route, /payload\.body/);
  assert.match(repository, /DELETE FROM push_subscriptions/);
  assert.match(repository, /alert\.publication_status = 'PUBLISHED'/);
  assert.match(repository, /data_publication_reviews/);
  assert.match(repository, /publication_review\.publishable = true/);
  assert.match(repository, /review\.entity_type = 'CITIZEN_ALERT'/);
  assert.match(repository, /source_archive_attestations/);
  assert.match(apiMain, /allow_methods=\["GET", "POST", "DELETE", "OPTIONS"\]/);
  assert.ok(proxy.includes("manifest\\\\.json"));
  for (const directory of ["test-results", "playwright-report", "blob-report"]) {
    assert.match(gitignore, new RegExp(`/${directory}/`));
  }
});

test("obsolete automatic registration and cleanup components are removed", async () => {
  await assert.rejects(access(new URL("components/pwa-register.tsx", root)));
  await assert.rejects(access(new URL("components/browser-storage-cleanup.tsx", root)));
});
