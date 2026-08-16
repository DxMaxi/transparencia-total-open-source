import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("public smoke covers every public route and deployment guard", async () => {
  const script = await readFile(
    new URL("scripts/check-public-site.mjs", root),
    "utf8",
  );

  for (const pathname of [
    "/politicos",
    "/atividade-parlamentar",
    "/promessas",
    "/guia-cidadao",
    "/metodologia",
    "/contacto",
    "/direito-de-resposta",
    "/privacidade",
    "/cookies",
    "/termos",
    "/acessibilidade",
  ]) {
    assert.match(script, new RegExp(`"${pathname}"`));
  }
  assert.match(script, /Dados oficiais publicados/);
  assert.match(script, /Ativar modo offline/);
  assert.match(script, /strict-transport-security/);
  assert.match(script, /content-security-policy/);
  assert.match(script, /PRIVATE_PATH_PREFIXES/);
  assert.match(script, /AbortSignal\.timeout/);
  assert.match(script, /__public-smoke-unknown-route__/);
});

test("public smoke runs after a successful Production deployment and on a daily schedule", async () => {
  const workflow = await readFile(
    new URL(".github/workflows/public-smoke.yml", root),
    "utf8",
  );

  assert.match(workflow, /deployment_status:/);
  assert.match(workflow, /github\.event\.deployment_status\.state == 'success'/);
  assert.match(workflow, /github\.event\.deployment\.environment == 'Production'/);
  assert.doesNotMatch(workflow, /push:\r?\n\s+branches:\r?\n\s+- main/);
  assert.match(workflow, /schedule:/);
  assert.match(workflow, /npm run smoke:public/);
  assert.match(workflow, /SMOKE_ATTEMPTS: "12"/);
});

test("official indexes refresh before the freshness monitor without publishing", async () => {
  const refresh = await readFile(
    new URL(".github/workflows/official-index-sync.yml", root),
    "utf8",
  );
  const monitor = await readFile(
    new URL(".github/workflows/operational-status.yml", root),
    "utf8",
  );

  assert.match(refresh, /cron: "17 2 \* \* \*"/);
  assert.match(monitor, /cron: "23 6 \* \* \*"/);
  assert.match(refresh, /environment: production/);
  assert.match(refresh, /python -m scripts\.refresh_v4_indexes/);
  assert.doesNotMatch(refresh, /scripts\.(publish|promote)|db:(deploy|migrate)|prisma migrate/i);
});
