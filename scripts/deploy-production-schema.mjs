import { spawnSync } from "node:child_process";
import { resolveProductionMigrationTarget } from "./production-migration-target.mjs";

const { connectionString } = resolveProductionMigrationTarget();
// Pass the validated URI only in the child environment, never in argv or logs.
const result = spawnSync("npm", ["run", "db:deploy"], {
  env: { ...process.env, DATABASE_URL: connectionString },
  stdio: "inherit",
});
if (result.error) throw new Error("Não foi possível iniciar a migração de produção.");
process.exit(result.status ?? 1);
