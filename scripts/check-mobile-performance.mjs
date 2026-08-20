import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { launch } from "chrome-launcher";
import lighthouse from "lighthouse";
import { chromium } from "@playwright/test";

const host = "127.0.0.1";
const port = Number.parseInt(process.env.PERFORMANCE_PORT ?? "3100", 10);
const baseUrl = (process.env.PERFORMANCE_BASE_URL ?? `http://${host}:${port}`).replace(/\/$/, "");
const outputDirectory = fileURLToPath(new URL("../.sites-runtime/lighthouse/", import.meta.url));
const nextBinary = fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url));
const numberOfRuns = 3;
const routes = ["/", "/atividade-parlamentar", "/pesquisa"];
const budgets = {
  performanceScore: { minimum: 0.9, label: "desempenho" },
  firstContentfulPaint: { maximum: 2_500, label: "FCP" },
  largestContentfulPaint: { maximum: 3_500, label: "LCP" },
  totalBlockingTime: { maximum: 350, label: "TBT" },
  cumulativeLayoutShift: { maximum: 0.1, label: "CLS" },
  interactive: { maximum: 4_500, label: "TTI" },
  totalBytes: { maximum: 400_000, label: "peso transferido" },
};

function median(values) {
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.floor(ordered.length / 2)];
}

function auditNumber(result, id) {
  const value = result.lhr.audits[id]?.numericValue;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`O Lighthouse não devolveu a métrica ${id}.`);
  }
  return value;
}

function metrics(result) {
  const score = result.lhr.categories.performance?.score;
  if (typeof score !== "number" || !Number.isFinite(score)) {
    throw new Error("O Lighthouse não devolveu a pontuação de desempenho.");
  }
  return {
    performanceScore: score,
    firstContentfulPaint: auditNumber(result, "first-contentful-paint"),
    largestContentfulPaint: auditNumber(result, "largest-contentful-paint"),
    totalBlockingTime: auditNumber(result, "total-blocking-time"),
    cumulativeLayoutShift: auditNumber(result, "cumulative-layout-shift"),
    interactive: auditNumber(result, "interactive"),
    totalBytes: auditNumber(result, "total-byte-weight"),
  };
}

async function waitForServer(url, server) {
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`O servidor Next terminou antes da medição (código ${server.exitCode}).`);
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_500) });
      if (response.ok) return;
    } catch {
      // O servidor ainda está a iniciar.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("O servidor Next não ficou pronto dentro de 45 segundos.");
}

function startServer() {
  if (process.env.PERFORMANCE_START_SERVER === "0") return null;
  return spawn(
    process.execPath,
    [nextBinary, "start", "--hostname", host, "--port", String(port)],
    {
      cwd: fileURLToPath(new URL("../", import.meta.url)),
      env: { ...process.env, NODE_ENV: "production" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
}

async function stopServer(server) {
  if (!server) return;
  if (server.exitCode === null) {
    const exited = new Promise((resolve) => server.once("exit", resolve));
    server.kill();
    await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 5_000))]);
  }
  server.stdout?.destroy();
  server.stderr?.destroy();
}

async function run() {
  await mkdir(outputDirectory, { recursive: true });
  const server = startServer();
  let chrome;
  try {
    if (server) await waitForServer(baseUrl, server);
    chrome = await launch({
      chromePath: process.env.CHROME_PATH || chromium.executablePath(),
      chromeFlags: ["--headless", "--no-sandbox", "--disable-gpu"],
    });

    const routeSummaries = [];
    for (const route of routes) {
      const results = [];
      for (let runIndex = 1; runIndex <= numberOfRuns; runIndex += 1) {
        const result = await lighthouse(`${baseUrl}${route}`, {
          port: chrome.port,
          output: "json",
          logLevel: "error",
          onlyCategories: ["performance"],
        });
        if (!result) throw new Error(`O Lighthouse não produziu relatório para ${route}.`);
        results.push(metrics(result));
        await writeFile(
          `${outputDirectory}/${encodeURIComponent(route || "home")}-${runIndex}.json`,
          JSON.stringify(result.lhr),
          "utf8",
        );
      }
      const summary = Object.fromEntries(
        Object.keys(results[0]).map((metric) => [
          metric,
          median(results.map((result) => result[metric])),
        ]),
      );
      routeSummaries.push({ route, runs: numberOfRuns, median: summary });
    }

    const failures = [];
    for (const route of routeSummaries) {
      for (const [metric, budget] of Object.entries(budgets)) {
        const value = route.median[metric];
        if (budget.minimum !== undefined && value < budget.minimum) {
          failures.push(`${route.route}: ${budget.label} ${value} < ${budget.minimum}`);
        }
        if (budget.maximum !== undefined && value > budget.maximum) {
          failures.push(`${route.route}: ${budget.label} ${value} > ${budget.maximum}`);
        }
      }
    }
    const report = {
      generatedAt: new Date().toISOString(),
      methodology: "Lighthouse mobile, simulação predefinida, mediana de três execuções",
      budgets,
      routes: routeSummaries,
      failures,
    };
    await writeFile(
      `${outputDirectory}/summary.json`,
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );
    for (const route of routeSummaries) {
      const result = route.median;
      console.log(
        `${route.route}: score ${result.performanceScore.toFixed(2)}, `
        + `LCP ${Math.round(result.largestContentfulPaint)} ms, `
        + `TBT ${Math.round(result.totalBlockingTime)} ms, `
        + `CLS ${result.cumulativeLayoutShift.toFixed(3)}, `
        + `${Math.round(result.totalBytes)} bytes`,
      );
    }
    if (failures.length) {
      throw new Error(`Orçamento móvel excedido:\n${failures.join("\n")}`);
    }
  } finally {
    await stopServer(server);
    try {
      await chrome?.kill();
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error ? error.code : null;
      if (code !== "EPERM") throw error;
      console.warn("O Chrome terminou, mas o Windows reteve temporariamente a pasta de perfil.");
    }
  }
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
