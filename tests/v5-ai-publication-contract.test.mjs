import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const source = (path) => readFile(new URL(path, root), "utf8");

test("V5.15 separa aprovação, publicação ADMIN+MFA e retirada imutável de IA", async () => {
  const [route, dependencies, repository, models] = await Promise.all([
    source("backend/app/api/routes/editorial.py"),
    source("backend/app/api/dependencies.py"),
    source("backend/app/repositories/ai_editorial_publication.py"),
    source("backend/app/models/editorial.py"),
  ]);

  for (const endpoint of ["publication", "withdrawal"]) {
    assert.match(route, new RegExp(`@router\\.get\\(\"/ai/cases/\\{case_id\\}/${endpoint}\"\\)`));
    assert.match(route, new RegExp(`@router\\.post\\(\"/ai/cases/\\{case_id\\}/${endpoint}\"\\)`));
  }
  assert.match(route, /publish_ai_case[\s\S]*Depends\(require_editorial_admin\)/);
  assert.match(route, /withdraw_ai_case[\s\S]*Depends\(require_editorial_admin\)/);
  assert.match(dependencies, /session\.assurance_level != "aal2"/);
  assert.match(models, /class AiEditorialPublicationRequest/);
  assert.match(models, /confirm_no_prediction_or_recommendation: Literal\[True\]/);
  assert.match(models, /class AiEditorialWithdrawalRequest/);
  assert.match(repository, /connection\.transaction\(\)/);
  assert.match(repository, /INSERT INTO data_publication_reviews/);
  assert.match(repository, /INSERT INTO audit_events/);
  assert.match(repository, /EditorialAction\.PUBLISH/);
  assert.match(repository, /EditorialAction\.WITHDRAW/);
  assert.match(repository, /INSERT INTO editorial_publication_events/);
  assert.doesNotMatch(repository, /similarity\s*\(|levenshtein\s*\(|fuzzy/i);

  const publishMethod = repository
    .split("async def publish(", 2)[1]
    .split("async def withdraw(", 1)[0];
  assert.doesNotMatch(publishMethod, /summarize|get_summarizer|openai/i);
});

test("a projeção pública revalida fonte, hashes, âncoras, evento e porta pública", async () => {
  const [repository, publicRoute, publicModels, healthRoute] = await Promise.all([
    source("backend/app/repositories/ai_editorial_publication.py"),
    source("backend/app/api/routes/public_data.py"),
    source("backend/app/models/public_ai.py"),
    source("backend/app/api/routes/health.py"),
  ]);

  for (const evidence of [
    "_snapshot_from_row",
    "validate_summary_against_source",
    "INPUT_HASH_MISMATCH",
    "OUTPUT_HASH_MISMATCH",
    "EDITORIAL_HASH_MISMATCH",
    "_event_is_valid",
    "_audit_matches",
    "_public_review_by_reference",
    "repeatable_read",
  ]) {
    assert.match(repository, new RegExp(evidence));
  }
  assert.match(repository, /AI_PUBLIC_LABEL = "Explicação gerada por IA — revista por humano"/);
  assert.match(repository, /"not_prediction": True/);
  assert.match(repository, /"no_voting_recommendation": True/);
  assert.match(repository, /"kind": "DATA_UNAVAILABLE"/);
  assert.match(publicRoute, /@router\.get\("\/ai-explanations"/);
  assert.match(publicRoute, /\/ai-explanations\/publication-history/);
  assert.match(publicRoute, /\/ai-explanations\/\{public_id\}/);
  assert.match(publicModels, /human_reviewed: Literal\[True\]/);
  assert.match(publicModels, /ai_is_source: Literal\[False\]/);
  assert.doesNotMatch(publicModels, /case_id|version_id|rationale.*internal/i);
  assert.match(publicRoute, /_AI_PUBLIC_DATABASE_ERRORS/);
  assert.match(publicRoute, /_ai_unavailable/);
  assert.match(healthRoute, /_ai_public_schema_is_ready/);
  assert.match(healthRoute, /to_regclass\(name\)/);
  assert.match(healthRoute, /FROM "_prisma_migrations"/);
  assert.match(healthRoute, /finished_at IS NOT NULL/);
  assert.match(healthRoute, /rolled_back_at IS NULL/);
  assert.match(
    healthRoute,
    /if await _ai_public_schema_is_ready\(repository\):[\s\S]*capabilities\.append\("ai_explanations_v1"\)/,
  );
});

test("o painel e o site tornam o rótulo, os limites e as provas impossíveis de omitir", async () => {
  const [actions, detail, listing, publicDetail, navigation, documentation] = await Promise.all([
    source("app/admin/revisao/actions.ts"),
    source("app/admin/revisao/[case_id]/page.tsx"),
    source("app/explicacoes/page.tsx"),
    source("app/explicacoes/[public_id]/page.tsx"),
    source("components/site-header.tsx"),
    source("docs/V5_AI_PUBLICATION.md"),
  ]);

  for (const confirmation of [
    "confirm_source_reviewed",
    "confirm_ai_label_reviewed",
    "confirm_no_prediction_or_recommendation",
    "confirm_publication",
    "confirm_no_selective_removal",
    "confirm_public_effect_reviewed",
  ]) {
    assert.match(actions, new RegExp(confirmation));
    assert.match(detail, new RegExp(confirmation));
  }
  assert.match(listing, /não notícias automáticas/i);
  assert.match(listing, /nunca gera uma resposta nova/i);
  assert.match(publicDetail, /IA não é fonte/i);
  assert.match(publicDetail, /Sem recomendação de voto/i);
  assert.match(publicDetail, /SHA-256 da projeção pública/i);
  assert.match(navigation, /\/explicacoes/);
  assert.match(actions, /revalidatePath\(`\/explicacoes\/\$\{publicId\}`\)/);
  assert.match(actions, /revalidatePath\("\/sitemap\.xml"\)/);
  assert.match(documentation, /nenhum conteúdo é publicado\s+automaticamente/i);
  assert.match(documentation, /PostgreSQL descartável/i);
});
