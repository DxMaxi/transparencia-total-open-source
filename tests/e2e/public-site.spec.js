import { test, expect } from "@playwright/test";

const baseURL = (
  process.env.PLAYWRIGHT_BASE_URL || "https://www.transparenciatotal.pt"
).replace(/\/$/, "");

test.describe("Transparência Total — auditoria pública", () => {
  test("páginas principais abrem sem erro", async ({ page }) => {
    const routes = [
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

    for (const route of routes) {
      const response = await page.goto(`${baseURL}${route}`, {
        waitUntil: "domcontentloaded",
      });

      expect(response, `Sem resposta em ${route}`).not.toBeNull();
      expect(response.status(), `${route} devolveu erro`).toBe(200);

      await expect(page.locator("h1")).toBeVisible();
    }
  });

  test("links internos principais não estão partidos", async ({ page }) => {
    await page.goto(baseURL);

    const hrefs = await page.locator('a[href^="/"]').evaluateAll((links) =>
      [...new Set(links.map((link) => link.getAttribute("href")).filter(Boolean))]
    );

    for (const href of hrefs) {
      if (
        href.startsWith("/admin") ||
        href.startsWith("/auth") ||
        href.startsWith("/api")
      ) {
        continue;
      }

      const response = await page.request.get(`${baseURL}${href}`);
      expect(
        response.status(),
        `Link interno partido: ${href}`
      ).toBeLessThan(400);
    }
  });

  test("404 pública funciona corretamente", async ({ page }) => {
    const response = await page.goto(
      `${baseURL}/pagina-que-nao-deve-existir-e2e`
    );

    expect(response).not.toBeNull();
    expect(response.status()).toBe(404);

    await expect(
      page.getByText(/Página não encontrada/i)
    ).toBeVisible();
  });

  test("site funciona em viewport móvel", async ({ page }) => {
    await page.setViewportSize({
      width: 390,
      height: 844,
    });

    await page.goto(baseURL);

    await expect(page.locator("h1")).toBeVisible();

    const bodyWidth = await page.evaluate(
      () => document.documentElement.scrollWidth
    );

    expect(bodyWidth).toBeLessThanOrEqual(390);
  });

  test("modo offline só cria cache depois da escolha e pode ser apagado", async ({ page }) => {
    await page.goto(baseURL);
    await page.evaluate(async () => {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.unregister()));
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith("transparencia-total-"))
          .map((key) => caches.delete(key)),
      );
    });
    await page.reload();

    const initialCaches = await page.evaluate(() => caches.keys());
    expect(initialCaches.filter((key) => key.startsWith("transparencia-total-"))).toEqual([]);

    await page.getByRole("button", { name: "Ativar modo offline" }).click();
    await expect(page.getByText(/Ativo\. Páginas públicas/)).toBeVisible();
    const enabledCaches = await page.evaluate(() => caches.keys());
    expect(enabledCaches).toContain("transparencia-total-offline-preference");

    await page.getByRole("button", { name: "Desativar e apagar cache" }).click();
    await expect(page.getByText(/Desativado\. Nenhum cache offline/)).toBeVisible();
    const finalCaches = await page.evaluate(() => caches.keys());
    expect(finalCaches.filter((key) => key.startsWith("transparencia-total-"))).toEqual([]);
  });

  test("página de políticos carrega interface pública", async ({ page }) => {
    await page.goto(`${baseURL}/politicos`);

    await expect(page.locator("h1")).toBeVisible();

    await expect(
      page.locator("body")
    ).not.toContainText(/Application error|Internal Server Error/i);
  });

  test("atividade parlamentar carrega sem erro", async ({ page }) => {
    await page.goto(`${baseURL}/atividade-parlamentar`);

    await expect(page.locator("h1")).toBeVisible();

    await expect(
      page.locator("body")
    ).not.toContainText(/Application error|Internal Server Error/i);
  });
});
