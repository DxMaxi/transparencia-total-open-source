import { defineConfig } from "@playwright/test";

const baseURL = (
  process.env.PLAYWRIGHT_BASE_URL || "https://www.transparenciatotal.pt"
).replace(/\/$/, "");
const startLocalServer = process.env.PLAYWRIGHT_START_SERVER === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "test-results",
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : "list",
  use: {
    baseURL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: startLocalServer
    ? {
        command: "npm run start:next -- --hostname 127.0.0.1 --port 3000",
        url: baseURL,
        reuseExistingServer: false,
        timeout: 120_000,
      }
    : undefined,
});
