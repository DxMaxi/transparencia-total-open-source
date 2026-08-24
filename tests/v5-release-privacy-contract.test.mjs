import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relativePath) => readFile(path.join(repositoryRoot, relativePath), "utf8");

const protectedKey = /^(?:nif|nipc|tax_?id|fiscal_?number)$/i;
const personalDataKey = /^(?:email|phone|telefone|telemovel|morada|address)$/i;
const secretPatterns = [
  ["identidade age", /AGE-SECRET-KEY-[A-Z0-9-]{20,}/],
  ["chave privada", /BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY/],
  ["secret key Supabase", /sb_secret_[a-z0-9_-]{12,}/i],
  ["chave OpenAI", /sk-(?:proj-)?[a-z0-9_-]{20,}/i],
  ["JWT completo", /eyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}/],
  ["ligação PostgreSQL com password", /postgres(?:ql)?:\/\/[^\s:@/]+:[^\s@/]+@/i],
];

function inspectJson(value, location, findings) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => inspectJson(item, `${location}[${index}]`, findings));
    return;
  }

  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      const childLocation = `${location}.${key}`;
      if (protectedKey.test(key)) findings.push(`${childLocation}: identificador fiscal`);
      if (
        personalDataKey.test(key)
        && child !== null
        && String(child).trim() !== ""
      ) {
        findings.push(`${childLocation}: dado pessoal preenchido`);
      }
      inspectJson(child, childLocation, findings);
    }
    return;
  }

  if (typeof value !== "string") return;
  for (const [label, pattern] of secretPatterns) {
    if (pattern.test(value)) findings.push(`${location}: ${label}`);
  }
}

test("tracked civic JSON files contain no clear protected identifiers or secrets", async () => {
  const trackedDataFiles = execFileSync("git", ["ls-files", "data"], {
    cwd: repositoryRoot,
    encoding: "utf8",
  })
    .split(/\r?\n/)
    .filter((file) => file.endsWith(".json"));

  assert.ok(trackedDataFiles.length > 0, "o gate deve inspecionar os JSON versionados em data/");
  const findings = [];
  for (const file of trackedDataFiles) {
    const parsed = JSON.parse(await read(file));
    inspectJson(parsed, file, findings);
  }

  assert.deepEqual(findings, []);
});

test("the release records the sanitized history audit and keeps public visibility blocked", async () => {
  const [audit, checklist, technicalAudit] = await Promise.all([
    read("docs/V5_RELEASE_PRIVACY_AUDIT.md"),
    read("docs/V5_RELEASE_CHECKLIST.md"),
    read("docs/AUDIT_2026-08-15.md"),
  ]);

  assert.match(audit, /Gitleaks `8\.30\.0`/);
  assert.match(audit, /cinco alertas `generic-api-key`/i);
  assert.match(audit, /um endereço Gmail\s+pessoal permanece em diffs históricos/i);
  assert.match(audit, /a visibilidade pública do repositório continua bloqueada/i);
  assert.match(audit, /não autoriza reescrever commits, tags ou branches/i);
  assert.doesNotMatch(audit, /[a-z0-9._%+-]+@gmail\.com/i);
  assert.match(checklist, /\[x\] História Git integral pesquisada por segredos/);
  assert.match(checklist, /V5_RELEASE_PRIVACY_AUDIT\.md/);
  assert.match(technicalAudit, /V5_RELEASE_PRIVACY_AUDIT\.md/);
});
