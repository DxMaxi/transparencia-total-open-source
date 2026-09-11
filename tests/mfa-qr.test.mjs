import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import { AuthClient } from "@supabase/supabase-js";

test("MFA preserves the installed SDK image URL instead of encoding a second prefix", async () => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="black"/></svg>';
  const auth = new AuthClient({
    url: "https://auth.example.test",
    persistSession: false,
    autoRefreshToken: false,
    detectSessionInUrl: false,
    fetch: async () => new Response(JSON.stringify({
      id: "synthetic-factor", type: "totp",
      totp: { qr_code: svg, secret: "SYNTHETIC-TEST-ONLY", uri: "otpauth://totp/test" },
    }), { headers: { "Content-Type": "application/json" } }),
  });
  const enrolled = await auth.mfa.enroll({ factorType: "totp" });
  assert.equal(enrolled.error, null);
  assert.equal(enrolled.data.totp.qr_code, `data:image/svg+xml;utf-8,${svg}`);

  const preparedState = Promise.withResolvers();
  const oldApiUrl = process.env.NEXT_PUBLIC_API_URL;
  const oldFetch = globalThis.fetch;
  const client = { auth: {
    getClaims: async () => ({ data: { claims: {} } }),
    getSession: async () => ({ data: { session: { access_token: "synthetic-test-only" } } }),
    mfa: {
      getAuthenticatorAssuranceLevel: async () => ({ data: { currentLevel: "aal1" } }),
      listFactors: async () => ({ data: { totp: [], all: [] } }),
      enroll: async () => enrolled,
    },
  } };
  const realRequire = createRequire(import.meta.url);
  const mockedRequire = (name) => {
    if (name === "react") return {
      useEffect: (effect) => effect(), useRef: () => ({ current: false }),
      useState: (initial) => [initial, (value) => {
        if (value?.factorId) preparedState.resolve(value);
        if (typeof value === "string" && value.startsWith("Não foi possível")) {
          preparedState.reject(new Error("MFA preparation failed"));
        }
      }],
    };
    if (name === "next/navigation") return { useRouter: () => ({ replace: assert.fail, refresh() {} }) };
    if (name === "@/lib/supabase/client") return { createBrowserSupabaseClient: () => client };
    return realRequire(name);
  };
  const source = await readFile(new URL("../components/admin-mfa-setup.tsx", import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  try {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.test";
    globalThis.fetch = async () => new Response("{}", { status: 200 });
    const module = { exports: {} };
    new Function("require", "module", "exports", output)(mockedRequire, module, module.exports);
    module.exports.AdminMfaSetup({ configured: true, next: "/admin/revisao" });
    const state = await preparedState.promise;
    assert.equal(state.qrCode, enrolled.data.totp.qr_code);
    assert.ok(state.qrCode.slice(state.qrCode.indexOf(",") + 1).startsWith("<svg"));
    assert.equal(state.secret, "SYNTHETIC-TEST-ONLY");
  } finally {
    globalThis.fetch = oldFetch;
    if (oldApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = oldApiUrl;
  }
});
