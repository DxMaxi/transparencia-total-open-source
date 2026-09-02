import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

function loadFunctions(source, names, globals = {}) {
  const file = ts.createSourceFile("contract.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const functions = file.statements.filter((node) =>
    ts.isFunctionDeclaration(node) && node.name && names.includes(node.name.text),
  );
  assert.equal(functions.length, names.length);
  const code = functions.map((node) => node.getText(file).replace(/^export /, "")).join("\n");
  const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
  const context = vm.createContext(globals);
  vm.runInContext(compiled.outputText, context);
  return context;
}

test("V5.52 private identity query rejects protected identifiers before reflection", async () => {
  const page = await read("app/admin/revisao/organizacoes/page.tsx");
  const { safeSearchQuery, boundedOffset } = loadFunctions(page, ["safeSearchQuery", "boundedOffset"]);
  for (const unsafe of [
    "123456789", "123 456 789", "123-456-789", "１２３４５６７８９", "١٢٣٤٥٦٧٨٩",
    "Empresa 1 A 2 B 3 C 4 D 5 E 6 F 7 G 8 H 9", "f".repeat(64), `prova ${"a1".repeat(32)}`,
    "abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd-abcd",
    "a".repeat(101), "e", "entidade\u200b", ["empresa", "outra"],
  ]) assert.equal(safeSearchQuery(unsafe), null);
  assert.equal(safeSearchQuery(undefined), "");
  assert.equal(safeSearchQuery("  Município de Teste  "), "Município de Teste");
  assert.equal(safeSearchQuery("AP-1-2026"), "AP-1-2026");
  assert.equal(boundedOffset("20"), 20);
  for (const unsafe of ["-1", "1.5", "20abc", "10001", ["20"], undefined]) assert.equal(boundedOffset(unsafe), 0);
  assert.match(page, /defaultValue=\{query\}/);
  assert.match(page, /if \(safeQuery !== null\)/);
  assert.match(page, /Object\.hasOwn\(errorMessages, input\.erro\)/);
  assert.doesNotMatch(page, /\{input\.(?:q|erro)\}/);
  assert.doesNotMatch(page, /name="(?:nipc|nif|protected_identifier_digest|observation_sha256|hmac)"/i);
  assert.doesNotMatch(page, /candidate\.(?:protected_identifier_digest|observation_sha256|hmac)/i);
});

test("V5.52 server action authenticates independently and allowlists private proposal fields", async () => {
  const actions = await read("app/admin/revisao/actions.ts");
  const requests = [];
  const redirects = [];
  const revalidations = [];
  let authenticated = false;
  let apiFailure = null;
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  const context = loadFunctions(actions,
    ["requiredText", "evidenceId", "sha256", "createBaseOrganisationIdentityProposal"], {
      EditorialApiError: ApiError,
      getEditorialContext: async () => { authenticated = true; },
      editorialFetch: async (path, init) => {
        assert.equal(authenticated, true);
        requests.push({ path, body: JSON.parse(init.body) });
        if (apiFailure) throw apiFailure;
        return { created: true, case: { id: "editorial-identity-1" } };
      },
      revalidatePath: (path) => revalidations.push(path),
      redirect: (path) => { redirects.push(path); throw new Error("NEXT_REDIRECT"); },
    });
  const values = {
    observation_id: "org-observation-1", source_record_sha256: "a".repeat(64),
    proposal_confirmation_sha256: "b".repeat(64),
    confirm_independent_official_source: "on", confirm_private_identity_only: "on", confirm_no_publication: "on",
    protected_identifier_digest: "c".repeat(64), nipc: "123456789", legal_name: "Forged name",
  };
  const form = { get: (key) => values[key] ?? null };
  await assert.rejects(context.createBaseOrganisationIdentityProposal(form), /NEXT_REDIRECT/);
  assert.deepEqual(requests[0], {
    path: "/base/organisation-identity-proposals",
    body: {
      observation_id: values.observation_id, source_record_sha256: values.source_record_sha256,
      proposal_confirmation_sha256: values.proposal_confirmation_sha256,
      confirm_independent_official_source: true, confirm_private_identity_only: true, confirm_no_publication: true,
    },
  });
  assert.deepEqual(revalidations, ["/admin/revisao", "/admin/revisao/organizacoes"]);
  assert.equal(redirects.at(-1), "/admin/revisao/editorial-identity-1?sucesso=identidade-privada");
  for (const status of [409, 422, 500]) {
    apiFailure = new ApiError(`Private database detail ${values.nipc} ${values.protected_identifier_digest}`, status);
    await assert.rejects(context.createBaseOrganisationIdentityProposal(form), /NEXT_REDIRECT/);
    assert.equal(redirects.at(-1), `/admin/revisao/organizacoes?erro=${status === 500 ? "proposta-nao-criada" : "prova-invalidada"}`);
  }
  assert.equal(revalidations.length, 2);
  delete values.confirm_no_publication;
  const requestCount = requests.length;
  await assert.rejects(context.createBaseOrganisationIdentityProposal(form), /NEXT_REDIRECT/);
  assert.equal(requests.length, requestCount);
  assert.equal(redirects.at(-1), "/admin/revisao/organizacoes?erro=confirmacao-em-falta");
});

test("V5.52 exposes neither generic identity creation nor JSON correction or publication", async () => {
  const [types, manual, detail, page, actions, queue, scripts] = await Promise.all([
    read("lib/editorial-types.ts"), read("app/admin/revisao/novo/page.tsx"),
    read("app/admin/revisao/[case_id]/page.tsx"), read("app/admin/revisao/organizacoes/page.tsx"),
    read("app/admin/revisao/actions.ts"), read("app/admin/revisao/page.tsx"), read("package.json"),
  ]);
  assert.match(types, /ORGANISATION_IDENTITY: "Identidade de organização \(privada\)"/);
  assert.match(types, /MANUAL_EDITORIAL_KINDS = EDITORIAL_KINDS\.filter\([^]*kind !== "ORGANISATION_IDENTITY"/);
  assert.match(manual, /MANUAL_EDITORIAL_KINDS\.map/);
  assert.match(actions, /formData\.get\("kind"\) === "ORGANISATION_IDENTITY"/);
  assert.match(detail, /const canCorrect = !isOrganisationIdentity &&/);
  assert.match(detail, /A identidade permanece privada, mesmo depois de aprovada/);
  assert.match(detail, /Uma correção exige nova observação/);
  assert.match(queue, /href="\/admin\/revisao\/organizacoes"/);
  for (const flag of ["confirm_independent_official_source", "confirm_private_identity_only", "confirm_no_publication"]) {
    assert.match(page, new RegExp(`name="${flag}"`));
  }
  const identityTypes = types.slice(types.indexOf("export type BaseOrganisationIdentityCandidate"), types.indexOf("export type StaffSession"));
  assert.doesNotMatch(identityTypes, /protected_identifier_digest|observation_sha256|nipc|hmac/i);
  assert.match(identityTypes, /protected_identifier_exposed: false/);
  assert.match(page, /não estabelece correspondências/);
  assert.match(page, /const nextOffset/);
  assert.match(page, /Consulta privada temporariamente indisponível/);
  assert.match(JSON.parse(scripts).scripts["test:frontend"], /v5-base-organisation-identity-contract\.test\.mjs/);
});
