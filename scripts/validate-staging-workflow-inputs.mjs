import { pathToFileURL } from "node:url";

export const STAGING_OPERATION_CONFIRMATIONS = Object.freeze({
  "inventory-read-only": "STAGING-INVENTORY-READ-ONLY",
  "migrate-schema": "STAGING-MIGRATE-SCHEMA",
  "inspect-readiness-read-only": "STAGING-INSPECT-READ-ONLY",
  "stage-government-programme-catalogue": "STAGING-STAGE-GOVERNMENT-PROGRAMME",
});

const PROJECT_REF_PATTERN = /^[a-z0-9]{20}$/;
const OFFICIAL_REPOSITORY = "DxMaxi/transparencia-total-open-source";
const PRODUCTION_FRONTEND_HOSTS = new Set([
  "transparenciatotal.pt",
  "www.transparenciatotal.pt",
]);

function required(environment, name) {
  const value = environment[name]?.trim();
  if (!value) throw new Error(`${name} não configurada.`);
  return value;
}

function projectRef(value, label) {
  if (!PROJECT_REF_PATTERN.test(value)) {
    throw new Error(`${label} não tem a forma de um project ref Supabase.`);
  }
  return value;
}

function forbiddenProjectRefs(value) {
  const refs = value
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => projectRef(item, "STAGING_FORBIDDEN_PROJECT_REFS"));
  if (refs.length === 0) {
    throw new Error("STAGING_FORBIDDEN_PROJECT_REFS tem de identificar pelo menos produção.");
  }
  return new Set(refs);
}

function exactHttpsOrigin(value, label) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${label} inválida.`);
  }
  if (
    url.protocol !== "https:" ||
    !url.hostname ||
    url.username ||
    url.password ||
    !["", "/"].includes(url.pathname) ||
    url.search ||
    url.hash
  ) {
    throw new Error(`${label} deve ser uma origem HTTPS exata.`);
  }
  return url;
}

export function resolveStagingWorkflowRequest(
  environment = process.env,
  { dispatchOnly = false } = {},
) {
  if (environment.GITHUB_EVENT_NAME !== "workflow_dispatch") {
    throw new Error("O workflow de staging aceita apenas workflow_dispatch.");
  }
  if (environment.GITHUB_REF !== "refs/heads/main") {
    throw new Error("O workflow de staging só pode executar a partir de main.");
  }
  if (environment.GITHUB_REPOSITORY !== OFFICIAL_REPOSITORY) {
    throw new Error("O workflow de staging recusa outro repositório.");
  }
  if (environment.ENVIRONMENT !== "staging") {
    throw new Error("ENVIRONMENT tem de ser staging.");
  }

  const operation = required(environment, "REQUESTED_OPERATION");
  const expectedConfirmation = STAGING_OPERATION_CONFIRMATIONS[operation];
  if (!expectedConfirmation) throw new Error("Operação de staging desconhecida.");
  if (required(environment, "REQUESTED_CONFIRMATION") !== expectedConfirmation) {
    throw new Error(`A operação ${operation} exige a confirmação exata ${expectedConfirmation}.`);
  }

  const requestedProjectRef = projectRef(
    required(environment, "REQUESTED_PROJECT_REF"),
    "REQUESTED_PROJECT_REF",
  );
  if (dispatchOnly) {
    return { operation, projectRef: requestedProjectRef, dispatchOnly: true };
  }

  const configuredProjectRef = projectRef(
    required(environment, "STAGING_SUPABASE_PROJECT_REF"),
    "STAGING_SUPABASE_PROJECT_REF",
  );
  if (requestedProjectRef !== configuredProjectRef) {
    throw new Error("O project ref pedido não coincide com o environment staging.");
  }

  const forbidden = forbiddenProjectRefs(required(environment, "STAGING_FORBIDDEN_PROJECT_REFS"));
  if (forbidden.has(configuredProjectRef)) {
    throw new Error("O project ref de staging coincide com um destino proibido.");
  }

  const supabaseUrl = exactHttpsOrigin(required(environment, "SUPABASE_URL"), "SUPABASE_URL");
  if (supabaseUrl.hostname !== `${configuredProjectRef}.supabase.co`) {
    throw new Error("SUPABASE_URL não corresponde ao project ref de staging.");
  }

  const corsOrigin = exactHttpsOrigin(
    required(environment, "STAGING_CORS_ORIGIN"),
    "STAGING_CORS_ORIGIN",
  );
  if (PRODUCTION_FRONTEND_HOSTS.has(corsOrigin.hostname)) {
    throw new Error("A origem frontend de staging não pode ser o domínio de produção.");
  }
  if (required(environment, "CORS_ORIGINS") !== corsOrigin.origin) {
    throw new Error("CORS_ORIGINS tem de coincidir exatamente com STAGING_CORS_ORIGIN.");
  }

  required(environment, "DATABASE_URL");
  return { operation, projectRef: configuredProjectRef, dispatchOnly: false };
}

const invokedPath = process.argv[1] ? pathToFileURL(process.argv[1]).href : null;
if (invokedPath === import.meta.url) {
  try {
    const request = resolveStagingWorkflowRequest(process.env, {
      dispatchOnly: process.argv.includes("--dispatch-only"),
    });
    console.log(
      JSON.stringify({
        authorized: true,
        operation: request.operation,
        project_ref: request.projectRef,
        scope: request.dispatchOnly ? "dispatch-only" : "staging-environment",
      }),
    );
  } catch (error) {
    console.error(error instanceof Error ? error.message : "Validação de staging falhou.");
    process.exitCode = 1;
  }
}
