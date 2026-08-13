import pg from "pg";
import { pathToFileURL } from "node:url";

const { Client } = pg;

const DISPOSABLE_BOOTSTRAP_SQL = String.raw`
DO $bootstrap$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END
$bootstrap$;

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
  id UUID PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS auth.tt_disposable_test_marker (
  singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton)
);

INSERT INTO auth.tt_disposable_test_marker (singleton)
VALUES (TRUE)
ON CONFLICT (singleton) DO NOTHING;
`;

export function resolveDisposableDatabaseTarget(environment = process.env) {
  if (environment.ENVIRONMENT !== "test") {
    throw new Error("O bootstrap Supabase só pode executar com ENVIRONMENT=test.");
  }
  if (environment.CONFIRM_DISPOSABLE_DATABASE !== "true") {
    throw new Error("Falta CONFIRM_DISPOSABLE_DATABASE=true.");
  }

  const configured = environment.DATABASE_URL?.trim();
  if (!configured) throw new Error("DATABASE_URL não configurada.");

  let url;
  try {
    url = new URL(configured);
  } catch {
    throw new Error("DATABASE_URL inválida.");
  }

  if (!['postgres:', 'postgresql:'].includes(url.protocol)) {
    throw new Error("O bootstrap exige PostgreSQL.");
  }
  if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
    throw new Error("O bootstrap recusa bases fora do computador local.");
  }

  const databaseName = decodeURIComponent(url.pathname.replace(/^\//, ""));
  if (!databaseName.endsWith("_test")) {
    throw new Error("O nome da base descartável tem de terminar em _test.");
  }

  // `schema=public` é uma opção Prisma, não um parâmetro PostgreSQL.
  url.searchParams.delete("schema");
  return { connectionString: url.toString(), databaseName };
}

export async function bootstrapSupabaseTestDatabase(environment = process.env) {
  const target = resolveDisposableDatabaseTarget(environment);
  const client = new Client({ connectionString: target.connectionString });
  await client.connect();
  try {
    await client.query("BEGIN");
    await client.query(DISPOSABLE_BOOTSTRAP_SQL);
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
  return { databaseName: target.databaseName };
}

const invokedPath = process.argv[1] ? pathToFileURL(process.argv[1]).href : null;
if (invokedPath === import.meta.url) {
  bootstrapSupabaseTestDatabase()
    .then(() => {
      console.log("Papéis e auth stub preparados apenas na base PostgreSQL descartável.");
    })
    .catch((error) => {
      console.error(error instanceof Error ? error.message : "Bootstrap descartável falhou.");
      process.exitCode = 1;
    });
}
