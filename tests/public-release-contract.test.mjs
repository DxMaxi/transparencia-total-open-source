import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function sourceFiles(directory) {
  const absolute = new URL(`${directory}/`, root);
  const entries = await readdir(absolute, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const relative = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await sourceFiles(relative));
    else if ([".ts", ".tsx"].includes(extname(entry.name))) files.push(relative);
  }
  return files;
}

test("public interface contains no prototype or demonstration copy", async () => {
  const files = [
    ...await sourceFiles("app"),
    ...await sourceFiles("components"),
    ...await sourceFiles("lib"),
  ];
  const contents = await Promise.all(
    files.map(async (file) => `${file}\n${await readFile(new URL(file, root), "utf8")}`),
  );
  const publicSource = contents.join("\n");

  assert.doesNotMatch(publicSource, /prot[oó]tipo com dados|dados demonstrativos|IA não executada/i);
  assert.doesNotMatch(publicSource, /demo-data|v2-demo-data|ENABLE_DEMO_DATA/);
});

test("legal information is reachable and supports real controller identification", async () => {
  const footer = await readFile(new URL("components/site-footer.tsx", root), "utf8");
  const site = await readFile(new URL("lib/site.ts", root), "utf8");
  for (const route of ["privacidade", "cookies", "termos", "acessibilidade", "contacto"]) {
    assert.match(footer, new RegExp(`href=[\\"']/${route}[\\"']`));
    await readFile(new URL(`app/${route}/page.tsx`, root), "utf8");
  }
  assert.match(site, /NEXT_PUBLIC_LEGAL_RESPONSIBLE_NAME/);
  assert.match(site, /Maximiano Moreira/);
  assert.match(site, /NEXT_PUBLIC_LEGAL_ADDRESS/);
  assert.match(site, /NEXT_PUBLIC_LEGAL_TAX_ID/);
});

test("the public release exposes security headers and opt-in PWA controls", async () => {
  const config = await readFile(new URL("next.config.ts", root), "utf8");
  const csp = await readFile(new URL("lib/content-security-policy.ts", root), "utf8");
  const proxy = await readFile(new URL("proxy.ts", root), "utf8");
  const supabaseProxy = await readFile(new URL("lib/supabase/proxy.ts", root), "utf8");
  const layout = await readFile(new URL("app/layout.tsx", root), "utf8");
  const footer = await readFile(new URL("components/site-footer.tsx", root), "utf8");
  const controls = await readFile(new URL("components/pwa-controls.tsx", root), "utf8");
  assert.match(config, /Content-Security-Policy/);
  assert.match(config, /X-Content-Type-Options/);
  assert.match(config, /X-Frame-Options/);
  assert.match(config, /Strict-Transport-Security/);
  assert.match(csp, /connect-src/);
  assert.match(csp, /worker-src 'self'/);
  assert.match(csp, /'strict-dynamic'/);
  assert.match(csp, /'nonce-\$\{nonce\}'/);
  assert.match(proxy, /pathname\.startsWith\("\/admin\/"\)/);
  assert.match(proxy, /pathname\.startsWith\("\/auth\/"\)/);
  assert.match(proxy, /crypto\.randomUUID\(\)/);
  assert.match(proxy, /requestHeaders\.set\("x-nonce", nonce\)/);
  assert.match(proxy, /response\.headers\.set\("Content-Security-Policy"/);
  assert.match(supabaseProxy, /request:\s*\{\s*headers:\s*forwardedHeaders\s*\}/);
  assert.match(layout, /manifest:\s*["']\/manifest\.json/);
  assert.doesNotMatch(layout, /BrowserStorageCleanup|PwaRegister/);
  assert.match(footer, /<PwaControls \/>/);
  assert.match(controls, /onClick={enableOfflineMode}/);
  assert.match(controls, /onClick={disableOfflineMode}/);
});

test("the right-of-reply form never falls back to a query-string submission", async () => {
  const form = await readFile(new URL("components/right-of-reply-form.tsx", root), "utf8");
  assert.match(form, /<form[^>]+method=["']post["']/);
});

test("the public contact channel never falls back to the maintainer personal email", async () => {
  const files = [
    "lib/site.ts",
    "app/contacto/page.tsx",
    "components/site-footer.tsx",
    "components/right-of-reply-form.tsx",
    "backend/app/core/config.py",
    ".env.example",
  ];
  const contents = (await Promise.all(
    files.map((file) => readFile(new URL(file, root), "utf8")),
  )).join("\n");
  assert.doesNotMatch(contents, /maximiano\.jp\.moreira@gmail\.com/i);
  assert.match(contents, /NEXT_PUBLIC_CONTACT_EMAIL/);
  assert.match(contents, /Email institucional em configuração/);
  assert.match(contents, /Um endereço pessoal não é\s+apresentado como substituição/);
});

test("the Prisma toolchain overrides the vulnerable recursive merge release", async () => {
  const packageJson = JSON.parse(await readFile(new URL("package.json", root), "utf8"));
  const packageLock = JSON.parse(await readFile(new URL("package-lock.json", root), "utf8"));

  assert.equal(packageJson.overrides?.["deepmerge-ts"], "8.0.1");
  assert.equal(packageLock.packages?.["node_modules/deepmerge-ts"]?.version, "8.0.1");
});
