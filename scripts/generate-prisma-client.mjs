import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// Client generation reads the schema only. Do not give the frontend build a live database.
// prisma.config.ts still requires a URL; a loopback destination satisfies that validation.
const cli = fileURLToPath(new URL("../node_modules/prisma/build/index.js", import.meta.url));
const result = spawnSync(process.execPath, [cli, "generate"], {
  cwd: new URL("../", import.meta.url),
  env: { ...process.env, DATABASE_URL: "postgresql://127.0.0.1:1/prisma_generate_only" },
  stdio: "inherit",
});

if (result.error) {
  console.error("Não foi possível iniciar a geração do cliente Prisma.");
}
process.exitCode = result.status ?? 1;
