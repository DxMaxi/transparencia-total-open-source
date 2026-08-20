import assert from "node:assert/strict";

const siteUrl = new URL(
  process.env.PUBLIC_SITE_URL?.trim() || "https://www.transparenciatotal.pt",
);
const attempts = Math.max(1, Number.parseInt(process.env.SMOKE_ATTEMPTS || "12", 10));
const delayMs = Math.max(0, Number.parseInt(process.env.SMOKE_DELAY_MS || "20000", 10));
const timeoutMs = Math.max(1000, Number.parseInt(process.env.SMOKE_TIMEOUT_MS || "15000", 10));

const htmlRoutes = [
  "/",
  "/politicos",
  "/atividade-parlamentar",
  "/promessas",
  "/explicacoes",
  "/guia-cidadao",
  "/metodologia",
  "/contacto",
  "/direito-de-resposta",
  "/privacidade",
  "/cookies",
  "/termos",
  "/acessibilidade",
];

function target(pathname) {
  return new URL(pathname, siteUrl).href;
}

async function get(pathname) {
  const response = await fetch(target(pathname), {
    headers: {
      Accept: "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
      "User-Agent": "TransparenciaTotal-PublicSmoke/1.0 (+https://www.transparenciatotal.pt)",
    },
    redirect: "follow",
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await response.text();
  return { response, body };
}

async function auditPublicSite() {
  const pages = await Promise.all(
    htmlRoutes.map(async (pathname) => {
      const result = await get(pathname);
      assert.equal(
        result.response.status,
        200,
        `${pathname} returned ${result.response.status}`,
      );
      assert.match(
        result.response.headers.get("content-type") || "",
        /text\/html/i,
        `${pathname} did not return HTML`,
      );
      assert.match(result.body, /<html[^>]+lang="pt-PT"/i, `${pathname} has no pt-PT root`);
      assert.match(result.body, /<h1[\s>]/i, `${pathname} has no H1`);
      assert.doesNotMatch(result.body, /Internal Server Error|Application error/i);
      return { pathname, ...result };
    }),
  );

  const home = pages.find((page) => page.pathname === "/");
  assert.ok(home);
  assert.match(home.body, /Dados oficiais publicados\./);
  assert.match(home.body, /Ativar modo offline/);

  const requiredHeaders = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
  };
  for (const [name, expected] of Object.entries(requiredHeaders)) {
    assert.equal(home.response.headers.get(name), expected, `invalid ${name}`);
  }
  assert.match(
    home.response.headers.get("strict-transport-security") || "",
    /max-age=31536000/i,
  );
  const csp = home.response.headers.get("content-security-policy") || "";
  assert.match(csp, /frame-ancestors 'none'/);
  assert.match(csp, /worker-src 'self'/);
  assert.match(csp, /upgrade-insecure-requests/);

  const [robots, sitemap, manifest, worker, missing] = await Promise.all([
    get("/robots.txt"),
    get("/sitemap.xml"),
    get("/manifest.json"),
    get("/sw.js"),
    get("/__public-smoke-unknown-route__"),
  ]);
  for (const [name, result] of Object.entries({ robots, sitemap, manifest, worker })) {
    assert.equal(result.response.status, 200, `${name} returned ${result.response.status}`);
  }
  assert.match(robots.body, /User-Agent:/i);
  assert.match(robots.body, /Sitemap:/i);
  assert.match(sitemap.body, /<urlset/i);
  assert.equal(JSON.parse(manifest.body).name, "Transparência Total");
  assert.match(worker.body, /CACHE_PREFIX = "transparencia-total-"/);
  assert.match(worker.body, /PRIVATE_PATH_PREFIXES/);
  assert.equal(missing.response.status, 404);
  assert.match(missing.body, /Página não encontrada/);

  return {
    origin: siteUrl.origin,
    pages: pages.length,
    checked_at: new Date().toISOString(),
  };
}

let latestError;
let succeeded = false;
for (let attempt = 1; attempt <= attempts; attempt += 1) {
  try {
    const report = await auditPublicSite();
    console.log(JSON.stringify({ status: "ok", attempt, ...report }));
    succeeded = true;
    break;
  } catch (error) {
    latestError = error;
    console.error(
      JSON.stringify({
        status: "retry",
        attempt,
        message: error instanceof Error ? error.message : String(error),
      }),
    );
    if (attempt < attempts) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
}

if (!succeeded) {
  throw latestError;
}
