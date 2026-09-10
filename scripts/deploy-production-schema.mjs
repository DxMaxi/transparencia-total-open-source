import { spawnSync } from "node:child_process";
import { productionCaPath, resolveProductionMigrationTarget } from "./production-migration-target.mjs";

const { connectionString } = resolveProductionMigrationTarget();
// Prisma's schema engine names the CA option sslcert and uses sslaccept=strict
// for certificate/hostname verification; node-postgres uses sslrootcert.
const prismaUrl = new URL(connectionString);
prismaUrl.searchParams.delete("sslrootcert");
prismaUrl.searchParams.set("sslmode", "require");
prismaUrl.searchParams.set("sslcert", productionCaPath);
prismaUrl.searchParams.set("sslaccept", "strict");
// Pass the validated URI only in the child environment, never in argv or logs.
const result = spawnSync("npm", ["run", "db:deploy"], {
  env: { ...process.env, DATABASE_URL: prismaUrl.toString() },
  stdio: "inherit",
});
if (result.error) throw new Error("Não foi possível iniciar a migração de produção.");
process.exit(result.status ?? 1);
