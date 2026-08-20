import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const source = (relativePath) => readFile(path.join(root, relativePath), "utf8");

test("a proposta de IA exige staff com MFA e confirmações privadas explícitas", async () => {
  const [route, dependency, model] = await Promise.all([
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/models/editorial.py"),
  ]);

  assert.match(route, /@router\.post\("\/ai\/dre-proposals"/);
  assert.match(route, /Depends\(require_editorial_staff\)/);
  assert.match(dependency, /assurance_level != "aal2"/);
  assert.match(model, /class AiDreProposalRequest/);
  assert.match(model, /confirm_private_only: Literal\[True\]/);
  assert.match(model, /confirm_archived_source_only: Literal\[True\]/);
  assert.match(model, /confirm_ai_not_source: Literal\[True\]/);
});

test("a geração lê apenas um snapshot DRE concluído e com arquivo atestado", async () => {
  const repository = await source("backend/app/repositories/ai_editorial.py");

  assert.match(repository, /FROM dre_document_snapshots snapshot/);
  assert.match(repository, /source\.publisher = 'DRE'/);
  assert.match(repository, /run\.status = 'SUCCEEDED'/);
  assert.match(repository, /source_archive_attestations candidate/);
  assert.match(repository, /archive_content_sha256.*source_hash/s);
  assert.match(repository, /pg_try_advisory_lock/);
  assert.doesNotMatch(repository, /fuzzy|similarity|levenshtein/i);
});

test("o resultado fica PENDING, auditável e sem caminho de publicação", async () => {
  const [service, editorial, publicRoute] = await Promise.all([
    source("backend/app/services/ai_editorial.py"),
    source("backend/app/repositories/editorial.py"),
    source("backend/app/api/routes/ai.py"),
  ]);

  assert.match(service, /requires_human_review["']?: True/);
  assert.match(service, /publication_eligible["']?: False/);
  assert.match(service, /publication_performed["']?: False/);
  assert.match(service, /prompt_sha256/);
  assert.match(service, /input_sha256/);
  assert.match(service, /output_sha256/);
  assert.match(service, /action="REQUESTED"/);
  assert.match(editorial, /origin=EditorialOrigin\.AI/);
  assert.match(editorial, /created_by_id=None/);
  assert.match(publicRoute, /status_code=410/);
  assert.doesNotMatch(service, /editorial_publication_events|INSERT INTO public_laws|\.publish\(/i);
});

test("a configuração recusa armazenamento do fornecedor e o comando direto está fechado", async () => {
  const [settings, summarizer, legacyScript, environment] = await Promise.all([
    source("backend/app/core/config.py"),
    source("backend/app/services/ai_summarizer.py"),
    source("backend/scripts/summarize_dre.py"),
    source(".env.example"),
  ]);

  assert.match(settings, /OPENAI_STORE tem de permanecer false/);
  assert.match(summarizer, /store=False/);
  assert.match(summarizer, /citizen-summary-ptpt-v2/);
  assert.match(legacyScript, /Geração direta desativada/);
  assert.doesNotMatch(legacyScript, /get_summarizer|DreCollector/);
  assert.match(environment, /AI_DAILY_GENERATION_LIMIT=20/);
  assert.match(environment, /AI_REQUEST_TIMEOUT_SECONDS=90/);
});
