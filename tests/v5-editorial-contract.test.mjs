import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const source = (relativePath) => readFile(path.join(root, relativePath), "utf8");

test("o acesso editorial é por convite, valida claims e exige MFA", async () => {
  const [login, proxy, mfa, serverApi] = await Promise.all([
    source("components/admin-login-form.tsx"),
    source("lib/supabase/proxy.ts"),
    source("components/admin-mfa-setup.tsx"),
    source("lib/editorial-api.ts"),
  ]);

  assert.match(login, /shouldCreateUser:\s*false/);
  assert.match(proxy, /supabase\.auth\.getClaims\(\)/);
  assert.match(mfa, /mfa\.getAuthenticatorAssuranceLevel\(\)/);
  assert.match(mfa, /factorType:\s*"totp"/);
  assert.match(serverApi, /claims\.aal !== "aal2"/);
  assert.match(serverApi, /Authorization: `Bearer \$\{accessToken\}`/);
});

test("o painel compara fonte e versão mas não oferece publicação genérica", async () => {
  const [detail, actions, apiRoute] = await Promise.all([
    source("app/admin/revisao/[case_id]/page.tsx"),
    source("app/admin/revisao/actions.ts"),
    source("backend/app/api/routes/editorial.py"),
  ]);

  assert.match(detail, /Fonte original/);
  assert.match(detail, /Versão normalizada atual/);
  assert.match(detail, /Sem publicação automática/);
  assert.match(actions, /start-review/);
  assert.match(actions, /approve/);
  assert.match(actions, /reject/);
  assert.match(actions, /correct/);
  assert.doesNotMatch(actions, /\/publish/);
  assert.doesNotMatch(apiRoute, /@router\.post\("\/cases\/\{case_id\}\/publish"/);
});

test("rotas privadas não são descobertas pelo site público", async () => {
  const [robots, sitemap, nextConfig] = await Promise.all([
    source("app/robots.ts"),
    source("app/sitemap.ts"),
    source("next.config.ts"),
  ]);
  assert.match(robots, /disallow:\s*\["\/admin\/", "\/auth\/"\]/);
  assert.doesNotMatch(sitemap, /\/admin/);
  assert.doesNotMatch(sitemap, /\/auth/);
  assert.match(nextConfig, /source: "\/admin\/:path\*"/);
  assert.match(nextConfig, /private, no-store, max-age=0/);
  assert.match(nextConfig, /noindex, nofollow, noarchive/);
});
