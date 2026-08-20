import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

export const REQUIRED_PUBLIC_CAPABILITIES = [
  "global_search_v1",
  "parliament_explorer_v1",
  "parliament_publication_history_v1",
];
export const AI_PUBLIC_CAPABILITY = "ai_explanations_v1";

function normaliseApiBaseUrl(value) {
  if (!value?.trim()) {
    throw new Error("NEXT_PUBLIC_API_URL não está configurada.");
  }
  const url = new URL(value.trim());
  const localHttp = url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname);
  if ((url.protocol !== "https:" && !localHttp) || url.username || url.password || url.search || url.hash) {
    throw new Error("NEXT_PUBLIC_API_URL tem de ser HTTPS ou um endereço HTTP local, sem credenciais.");
  }
  return url.toString().replace(/\/$/, "");
}

async function getJson(baseUrl, path, { fetchImpl, timeoutMs }) {
  const response = await fetchImpl(`${baseUrl}${path}`, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new Error(`${path} respondeu HTTP ${response.status}`);
  }
  try {
    return await response.json();
  } catch {
    throw new Error(`${path} não devolveu JSON válido`);
  }
}

function assertExplorerShape(value) {
  if (
    !value
    || typeof value !== "object"
    || !["sessions", "initiatives", "votes"].includes(value.kind)
    || !Number.isInteger(value.total)
    || !Array.isArray(value.sessions)
    || !Array.isArray(value.initiatives)
    || !Array.isArray(value.votes)
    || !value.facets
    || typeof value.facets !== "object"
  ) {
    throw new Error("/api/v1/public/parliament/explore não cumpre o contrato V5.5");
  }
}

function assertLegacyStatusShape(value) {
  if (
    !value
    || typeof value !== "object"
    || !value.counts
    || typeof value.counts !== "object"
    || !Number.isInteger(value.counts.parliament_sessions)
    || !Number.isInteger(value.counts.parliament_initiatives)
    || !Number.isInteger(value.counts.parliament_votes)
  ) {
    throw new Error("/api/v1/public/data-status não cumpre o contrato de compatibilidade");
  }
}

function assertAiExplanationListShape(value) {
  if (
    !value
    || typeof value !== "object"
    || !Array.isArray(value.items)
    || !Number.isInteger(value.total)
    || value.total < 0
    || !Number.isInteger(value.limit)
    || !Number.isInteger(value.offset)
    || value.total_is_exact !== true
    || typeof value.publication_rule !== "string"
  ) {
    throw new Error("/api/v1/public/ai-explanations não cumpre o contrato V5.15");
  }
}

function assertGlobalSearchShape(value) {
  const expectedKinds = [
    "politicians",
    "parliament_sessions",
    "parliament_initiatives",
    "parliament_votes",
    "promises",
    "ai_explanations",
  ];
  if (
    !value
    || typeof value !== "object"
    || typeof value.query !== "string"
    || !Number.isInteger(value.total_results)
    || value.total_results < 0
    || !Number.isInteger(value.available_sections)
    || value.available_sections < 1
    || !Array.isArray(value.sections)
    || value.sections.length !== expectedKinds.length
    || new Set(value.sections.map((section) => section?.kind)).size !== expectedKinds.length
    || expectedKinds.some((kind) => !value.sections.some((section) => section?.kind === kind))
    || typeof value.publication_rule !== "string"
    || typeof value.search_rule !== "string"
  ) {
    throw new Error("/api/v1/public/search não cumpre o contrato V5.18");
  }
  const available = value.sections.filter((section) => section?.availability === "AVAILABLE");
  const unavailable = value.sections.filter((section) => section?.availability === "UNAVAILABLE");
  if (
    available.length !== value.available_sections
    || unavailable.length !== value.unavailable_sections
    || available.some(
      (section) =>
        !Number.isInteger(section.total)
        || section.total < 0
        || section.total_is_exact !== true
        || !Array.isArray(section.items),
    )
    || unavailable.some(
      (section) =>
        section.total !== null
        || section.total_is_exact !== false
        || !Array.isArray(section.items)
        || section.items.length,
    )
    || available.reduce((total, section) => total + section.total, 0) !== value.total_results
  ) {
    throw new Error("/api/v1/public/search devolveu cobertura ou contagens inconsistentes");
  }
}

export async function verifyPublicApiCompatibility(
  rawBaseUrl,
  { fetchImpl = fetch, timeoutMs = 8_000, requireGlobalSearch = true } = {},
) {
  const baseUrl = normaliseApiBaseUrl(rawBaseUrl);
  const health = await getJson(baseUrl, "/api/v1/health", { fetchImpl, timeoutMs });
  const capabilities = Array.isArray(health.public_capabilities)
    ? health.public_capabilities
    : [];
  const requiredCapabilities = requireGlobalSearch
    ? REQUIRED_PUBLIC_CAPABILITIES
    : REQUIRED_PUBLIC_CAPABILITIES.filter((capability) => capability !== "global_search_v1");
  const missing = requiredCapabilities.filter(
    (capability) => !capabilities.includes(capability),
  );
  if (missing.length) {
    const hasVersionedPublicCapabilities = capabilities.some(
      (capability) => requiredCapabilities.includes(capability),
    );
    if (hasVersionedPublicCapabilities) {
      throw new Error(`A API pública ainda não anuncia: ${missing.join(", ")}`);
    }
    const [status, sessions, initiatives, votes] = await Promise.all([
      getJson(baseUrl, "/api/v1/public/data-status", { fetchImpl, timeoutMs }),
      getJson(
        baseUrl,
        "/api/v1/public/parliament/sessions?legislature=XVII&limit=1&offset=0",
        { fetchImpl, timeoutMs },
      ),
      getJson(
        baseUrl,
        "/api/v1/public/parliament/initiatives?legislature=XVII&limit=1&offset=0",
        { fetchImpl, timeoutMs },
      ),
      getJson(
        baseUrl,
        "/api/v1/public/parliament/votes?legislature=XVII&limit=1&offset=0",
        { fetchImpl, timeoutMs },
      ),
    ]);
    assertLegacyStatusShape(status);
    if (![sessions, initiatives, votes].every(Array.isArray)) {
      throw new Error("A API antiga não fornece todas as listas parlamentares revistas");
    }
    return {
      apiVersion: String(health.version ?? "não indicada"),
      capabilities: [],
      mode: "LIMITED_READ_ONLY",
    };
  }

  const aiAvailable = capabilities.includes(AI_PUBLIC_CAPABILITY);
  const [globalSearch, explorer, history, aiListing, aiHistory] = await Promise.all([
    requireGlobalSearch
      ? getJson(
          baseUrl,
          "/api/v1/public/search?q=lei&section_limit=1",
          { fetchImpl, timeoutMs },
        )
      : Promise.resolve(null),
    getJson(
      baseUrl,
      "/api/v1/public/parliament/explore?kind=votes&legislature=XVII&limit=1&offset=0",
      { fetchImpl, timeoutMs },
    ),
    getJson(
      baseUrl,
      "/api/v1/public/parliament/publication-history?legislature=XVII&limit=1",
      { fetchImpl, timeoutMs },
    ),
    aiAvailable
      ? getJson(
          baseUrl,
          "/api/v1/public/ai-explanations?limit=1&offset=0",
          { fetchImpl, timeoutMs },
        )
      : Promise.resolve(null),
    aiAvailable
      ? getJson(
          baseUrl,
          "/api/v1/public/ai-explanations/publication-history?limit=1",
          { fetchImpl, timeoutMs },
        )
      : Promise.resolve(null),
  ]);
  if (requireGlobalSearch) assertGlobalSearchShape(globalSearch);
  assertExplorerShape(explorer);
  if (!Array.isArray(history)) {
    throw new Error("/api/v1/public/parliament/publication-history não devolveu uma lista");
  }
  if (aiAvailable) {
    assertAiExplanationListShape(aiListing);
    if (!Array.isArray(aiHistory)) {
      throw new Error("/api/v1/public/ai-explanations/publication-history não devolveu uma lista");
    }
  }

  return {
    apiVersion: String(health.version ?? "não indicada"),
    capabilities: aiAvailable
      ? [...requiredCapabilities, AI_PUBLIC_CAPABILITY]
      : requiredCapabilities,
    mode: aiAvailable ? "CURRENT" : "CURRENT_AI_FAIL_CLOSED",
  };
}

export async function waitForPublicApiCompatibility(
  rawBaseUrl,
  {
    attempts = 30,
    intervalMs = 10_000,
    fetchImpl = fetch,
    timeoutMs = 8_000,
    requireGlobalSearch = true,
    onRetry = (message) => console.warn(message),
  } = {},
) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await verifyPublicApiCompatibility(rawBaseUrl, {
        fetchImpl,
        timeoutMs,
        requireGlobalSearch,
      });
    } catch (error) {
      lastError = error;
      if (attempt === attempts) break;
      onRetry(
        `API pública ainda não compatível (tentativa ${attempt}/${attempts}): ${error.message}`,
      );
      await new Promise((resolveDelay) => setTimeout(resolveDelay, intervalMs));
    }
  }
  throw new Error(
    `Deployment do frontend bloqueado: a API não suporta o contrato V5.18 nem a leitura revista de compatibilidade. ${lastError?.message ?? "Falha desconhecida."}`,
  );
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const attempts = Number.parseInt(process.env.PUBLIC_API_COMPATIBILITY_ATTEMPTS ?? "30", 10);
  const intervalMs = Number.parseInt(
    process.env.PUBLIC_API_COMPATIBILITY_INTERVAL_MS ?? "10000",
    10,
  );
  waitForPublicApiCompatibility(process.env.NEXT_PUBLIC_API_URL, {
    attempts: Number.isInteger(attempts) && attempts > 0 ? attempts : 30,
    intervalMs: Number.isInteger(intervalMs) && intervalMs >= 0 ? intervalMs : 10_000,
    requireGlobalSearch: process.env.VERCEL_ENV !== "preview",
  })
    .then((result) => {
      console.log(`API pública compatível: ${result.apiVersion} (${result.mode}).`);
    })
    .catch((error) => {
      console.error(error.message);
      process.exitCode = 1;
    });
}
