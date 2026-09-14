import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";

async function loadModule(file, env, dependencies = {}) {
  const source = await readFile(new URL(`../${file}`, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const context = { exports: {}, process: { env }, require(name) {
    assert.ok(Object.hasOwn(dependencies, name), `unexpected dependency: ${name}`);
    return dependencies[name];
  } };
  runInNewContext(compiled, context, { timeout: 1000 });
  return context.exports;
}

for (const [label, env, blocked] of [
  ["staging project deployed to its production slot", { DEPLOYMENT_ENVIRONMENT: "staging", VERCEL_ENV: "production" }, true],
  ["preview", { VERCEL_ENV: "preview" }, true],
  ["public production", { VERCEL_ENV: "production" }, false],
  ["existing installation without new setting", {}, false],
]) {
  test(`${label}: headers, robots and sitemap respect publication scope`, async () => {
    const environment = await loadModule("lib/deployment-environment.ts", env);
    const site = { SITE_URL: "https://site.example.test" };
    const config = await loadModule("next.config.ts", env, {
      "./lib/deployment-environment": environment,
      "./lib/content-security-policy": { buildContentSecurityPolicy: () => "default-src 'self'" },
    });
    const headers = await config.default.headers();
    const global = headers.find((rule) => rule.source === "/(.*)");
    assert.equal(global.headers.some((header) => header.key === "X-Robots-Tag" && header.value.includes("noindex")), blocked);
    for (const route of ["/admin/:path*", "/auth/:path*"]) {
      assert.ok(headers.find((rule) => rule.source === route).headers.some((header) => header.key === "X-Robots-Tag"));
    }
    const dependencies = { "@/lib/site": site, "@/lib/deployment-environment": environment };
    const robots = (await loadModule("app/robots.ts", env, dependencies)).default();
    assert.equal(robots.rules.disallow === "/", blocked);
    assert.equal(Boolean(robots.sitemap), !blocked);
    let calls = 0;
    const sitemap = await loadModule("app/sitemap.ts", env, {
      ...dependencies,
      "@/lib/public-data": {
        loadPublicPoliticians: async () => { calls++; return { data: [] }; },
        loadPublicAiExplanations: async () => { calls++; return { data: { items: [] } }; },
      },
    });
    const entries = await sitemap.default();
    assert.equal(entries.length === 0, blocked);
    assert.equal(calls, blocked ? 0 : 2);
  });
}
