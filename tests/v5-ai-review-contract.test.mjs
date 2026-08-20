import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const source = (relativePath) => readFile(path.join(root, relativePath), "utf8");

test("o catálogo e a fonte DRE são privados, MFA e novamente atestados", async () => {
  const [route, repository, service, main] = await Promise.all([
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/repositories/ai_editorial.py"),
    source("backend/app/services/ai_editorial.py"),
    source("backend/app/main.py"),
  ]);

  assert.match(route, /@router\.get\("\/ai\/dre-snapshots"\)/);
  assert.match(route, /@router\.get\("\/ai\/cases\/\{case_id\}\/source"\)/);
  assert.match(route, /ai_dre_snapshots[\s\S]*Depends\(require_editorial_staff\)/);
  assert.match(route, /ai_dre_case_source[\s\S]*Depends\(require_editorial_staff\)/);
  assert.match(route, /limit: Annotated\[int, Query\(ge=1, le=50_000\)\]/);
  assert.match(repository, /def load_ai_case_snapshot/);
  assert.match(repository, /snapshot_reference_sha256/);
  assert.match(repository, /len\(matching_ids\) != 1/);
  assert.match(repository, /expected_attestation_sha256 ==/);
  assert.match(service, /visible_text = snapshot\.extracted_text\[effective_offset:text_end\]/);
  assert.match(main, /startswith\(f"\{settings\.api_prefix\}\/editorial"\)/);
  assert.match(main, /response\.headers\["Cache-Control"\] = "no-store"/);

  const listMethod = service.split("async def list_dre_snapshots", 2)[1].split("async def case_source", 1)[0];
  assert.doesNotMatch(listMethod, /"extracted_text"/);
  assert.match(service, /"publication_performed": False/);
});

test("regenerar acrescenta uma versão AI e uma decisão humana sem publicação", async () => {
  const [model, service, editorial] = await Promise.all([
    source("backend/app/models/editorial.py"),
    source("backend/app/services/ai_editorial.py"),
    source("backend/app/repositories/editorial.py"),
  ]);

  assert.match(model, /class AiDreRegenerationRequest/);
  assert.match(model, /expected_current_version_sha256/);
  assert.match(model, /confirm_new_immutable_version: Literal\[True\]/);
  assert.match(service, /async def regenerate_dre_proposal/);
  assert.match(service, /expected_revision=payload\.expected_revision/);
  assert.match(service, /action="REQUESTED"/);
  assert.match(service, /action="SUCCEEDED"/);
  assert.match(editorial, /async def regenerate_ai_case/);
  assert.match(editorial, /'AI', NULL/);
  assert.match(editorial, /action=EditorialAction\.CORRECT/);

  const regeneration = editorial.split("async def regenerate_ai_case", 2)[1].split("async def correct_case", 1)[0];
  assert.doesNotMatch(regeneration, /editorial_publication_events|\bPUBLISH\b/);
  assert.match(regeneration, /current_state = 'PENDING'/);
});

test("o painel compara o DRE com a proposta estruturada e exige confirmações", async () => {
  const [catalogue, comparison, detail, actions] = await Promise.all([
    source("app/admin/revisao/ia/page.tsx"),
    source("app/admin/revisao/ai-comparison.tsx"),
    source("app/admin/revisao/[case_id]/page.tsx"),
    source("app/admin/revisao/actions.ts"),
  ]);

  assert.match(catalogue, /Propostas a partir do DRE/);
  assert.match(catalogue, /createAiDreProposal/);
  assert.match(catalogue, /confirm_archived_source_only/);
  assert.match(catalogue, /confirm_ai_not_source/);
  assert.match(comparison, /Texto oficial extraído do DRE/);
  assert.match(comparison, /Âncoras a confirmar no texto/);
  assert.match(comparison, /sourceTruncated/);
  assert.match(detail, /AiEditorialComparison/);
  assert.match(detail, /AiRegenerationAction/);
  assert.match(actions, /regenerateAiDreProposal/);
  assert.match(actions, /confirm_new_immutable_version/);
  assert.doesNotMatch(catalogue, /NEXT_PUBLIC_OPENAI|OPENAI_API_KEY/);
});
