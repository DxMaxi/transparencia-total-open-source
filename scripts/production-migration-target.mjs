import { fileURLToPath } from "node:url";

export const productionCaPath = fileURLToPath(new URL(
  "../config/certificates/supabase-prod-ca-2021.crt", import.meta.url,
));

export function resolveProductionMigrationTarget(environment = process.env) {
  const expectedRef = "kxvgungbqalofbqytwbn";
  if (environment.ENVIRONMENT !== "production" ||
      environment.CONFIRM_PRODUCTION_SCHEMA_MIGRATION !== "MIGRAR-V5" ||
      environment.EXPECTED_SUPABASE_PROJECT_REF !== expectedRef) {
    throw new Error("Falta a confirmação exata do destino de produção.");
  }
  let url;
  try { url = new URL(environment.DATABASE_URL); } catch {
    throw new Error("Ligação de produção inválida.");
  }
  const username = decodeURIComponent(url.username);
  const direct = url.hostname === `db.${expectedRef}.supabase.co` && username === "postgres";
  const pooler = url.hostname.endsWith(".pooler.supabase.com") && username === `postgres.${expectedRef}`;
  if (!["postgres:", "postgresql:"].includes(url.protocol) ||
      !(direct || pooler) || !url.password || url.pathname !== "/postgres") {
    throw new Error("Destino ou utilizador não corresponde ao projeto de produção confirmado.");
  }
  if (!["", "5432"].includes(url.port)) {
    throw new Error("A migração exige a porta de sessão 5432.");
  }
  if (url.searchParams.getAll("sslmode").length > 1 || url.searchParams.has("ssl")) {
    throw new Error("Opções TLS ambíguas: configurar apenas sslmode.");
  }
  // Dashboard connection strings can omit TLS. Enforce it for every consumer;
  // never downgrade an explicitly configured mode or silently accept plaintext.
  if (!url.searchParams.has("sslmode")) url.searchParams.set("sslmode", "require");
  if (!["require", "verify-full", "verify-ca"].includes(url.searchParams.get("sslmode"))) {
    throw new Error("A migração exige TLS obrigatório.");
  }
  const allowedOptions = new Set(["schema", "sslmode", "connection_limit", "pool_timeout", "connect_timeout"]);
  if ([...url.searchParams.keys()].some((key) => !allowedOptions.has(key))) {
    throw new Error("Opção de ligação não autorizada na migração de produção.");
  }
  url.searchParams.set("sslmode", "verify-full");
  url.searchParams.set("sslrootcert", productionCaPath);
  url.searchParams.delete("schema");
  return { connectionString: url.toString(), databaseName: "postgres" };
}
