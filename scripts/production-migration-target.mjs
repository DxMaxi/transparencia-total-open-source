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
      !(direct || pooler) || !url.password || url.pathname !== "/postgres" ||
      !["", "5432"].includes(url.port) ||
      !["require", "verify-full", "verify-ca"].includes(url.searchParams.get("sslmode"))) {
    throw new Error("A ligação não corresponde ao projeto de produção confirmado com TLS e porta de sessão.");
  }
  url.searchParams.delete("schema");
  return { connectionString: url.toString(), databaseName: "postgres" };
}
