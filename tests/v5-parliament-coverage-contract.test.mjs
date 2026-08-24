import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("the coverage API exposes only currently reviewed and attested snapshots", async () => {
  const [route, model, repository, health, deploymentGuard] = await Promise.all([
    read("../backend/app/api/routes/public_data.py"),
    read("../backend/app/models/public_parliament.py"),
    read("../backend/app/repositories/public_parliament.py"),
    read("../backend/app/api/routes/health.py"),
    read("../scripts/check-public-api-compatibility.mjs"),
  ]);

  assert.match(route, /"\/parliament\/coverage"/);
  assert.match(route, /response_model=list\[PublishedParliamentCoverageRow\]/);
  assert.match(route, /list_coverage\(limit=limit\)/);
  assert.match(model, /class PublishedParliamentCoverageRow\(BaseModel\):/);
  assert.match(model, /count_is_exact: Literal\[True\] = True/);
  assert.match(model, /historical_completeness: Literal\["NOT_ASSERTED"\]/);
  assert.match(model, /snapshot_sha256: str = Field\(pattern=r"\^\[0-9a-f\]\{64\}\$"\)/);

  assert.match(repository, /WITH latest_reviews AS/);
  assert.match(repository, /review\.publishable = TRUE/);
  assert.match(repository, /attestation\.content_sha256 = source\.content_sha256/);
  assert.match(repository, /attestation\.retrieval_url = source\.url/);
  assert.match(repository, /PARTITION BY snapshot\.legislature, review\.entity_type/);
  assert.match(repository, /session\.source_document_id = published\.source_document_id/);
  assert.match(repository, /initiative\.source_document_id = published\.source_document_id/);
  assert.match(repository, /event\.source_document_id = published\.source_document_id/);
  assert.match(repository, /session_period\.actual_count = published\.session_count/);
  assert.match(repository, /initiative_period\.actual_count = published\.initiative_count/);
  assert.match(repository, /vote_period\.actual_count = published\.vote_count/);
  assert.match(repository, /vote_period\.actual_record_count = published\.vote_record_count/);
  assert.doesNotMatch(repository, /similarity\(|levenshtein/i);
  assert.match(health, /"parliament_coverage_v1"/);
  assert.match(deploymentGuard, /PARLIAMENT_COVERAGE_CAPABILITY/);
  assert.match(deploymentGuard, /assertParliamentCoverageShape\(coverage\)/);
});

test("the public matrix is fail-closed and explains the exact scope of every count", async () => {
  const [page, client, styles, types, artifactGuard] = await Promise.all([
    read("../app/atividade-parlamentar/page.tsx"),
    read("../lib/public-data.ts"),
    read("../app/globals.css"),
    read("../types/public-data.ts"),
    read("../scripts/verify-next-artifact.mjs"),
  ]);

  assert.match(client, /export async function loadPublicParliamentCoverage/);
  assert.match(client, /\/api\/v1\/public\/parliament\/coverage\?limit=100/);
  assert.match(client, /Array\.isArray\(result\.data\)/);
  assert.match(client, /Number\.isSafeInteger\(row\.published_count\)/);
  assert.match(client, /row\.count_is_exact !== true/);
  assert.match(client, /row\.historical_completeness !== "NOT_ASSERTED"/);
  assert.match(client, /row\.source\?\.publisher !== "AR"/);
  assert.match(client, /row\.source\.content_sha256 \?\? ""/);
  assert.match(client, /row\.snapshot_sha256/);
  assert.match(client, /new Set\(rowKeys\)\.size !== rowKeys\.length/);
  assert.match(client, /isto não significa ausência de atividade parlamentar/);
  assert.match(types, /historicalCompleteness: "NOT_ASSERTED"/);

  assert.match(page, /Promise\.all\(\[/);
  assert.match(page, /loadPublicParliamentCoverage\(\)/);
  assert.match(page, /O que existe no portal, legislatura a legislatura/);
  assert.match(page, /Histórico total não afirmado/);
  assert.match(page, /Exatos nesta fotografia/);
  assert.match(page, /Fonte obtida:/);
  assert.match(page, /Fonte \{row\.source\.sha256\}/);
  assert.match(page, /Fotografia \{row\.snapshotSha256\}/);
  assert.match(page, /Não apresentamos zero nem uma lista antiga como substituição/);
  assert.match(page, /data de recolha e SHA-256/);
  assert.match(page, /publicar cada âmbito apenas depois de revisão humana explícita/);
  assert.match(styles, /\.parliament-coverage-table-wrap[^}]*overflow-x: auto/);
  assert.match(
    styles,
    /\.parliament-coverage-table td > \.coverage-chip[^}]*color: #805000/,
  );
  assert.match(styles, /\.parliament-backfill-plan[^}]*grid-template-columns/);
  assert.match(artifactGuard, /"\.parliament-coverage-matrix"/);
});

test("the historical backfill remains a versioned editorial plan, not a publication shortcut", async () => {
  const [documentation, catalogue, checklist, plan, readme] = await Promise.all([
    read("../docs/V5_PARLIAMENT_COVERAGE_AND_BACKFILL.md"),
    read("../docs/V5_PARLIAMENT_SOURCE_CATALOGUE.md"),
    read("../docs/V5_RELEASE_CHECKLIST.md"),
    read("../docs/V5_RELEASE_PLAN.md"),
    read("../README.md"),
  ]);

  assert.match(documentation, /Publicado no portal/);
  assert.match(documentation, /Candidato existente numa fonte oficial/);
  assert.match(documentation, /historical_completeness=NOT_ASSERTED/);
  assert.match(documentation, /source_id` oficial exato/);
  assert.match(documentation, /propostas privadas `PENDING` separadas/);
  assert.match(documentation, /Não existe continuação automática/);
  assert.match(documentation, /nenhum dado real, migração remota, utilizador ou segredo/i);
  assert.match(catalogue, /PENDING_INSPECTION/);
  assert.match(catalogue, /historical_completeness=NOT_ASSERTED/);
  assert.match(catalogue, /não descarrega os ficheiros XML ou JSON/);
  assert.match(catalogue, /não cria casos editoriais `PENDING`/);
  assert.match(catalogue, /produção é recusada pela própria camada de serviço/);
  assert.match(checklist, /\[x\] V5\.21 — matriz de cobertura parlamentar/);
  assert.match(checklist, /\[x\] V5\.22 — catálogo privado e versionado/);
  assert.match(checklist, /\[x\] Plano de backfill versionado/);
  assert.match(checklist, /\[x\] Matriz pública de cobertura parlamentar concluída/);
  assert.match(plan, /V5\.1 a V5\.22 integradas/);
  assert.match(plan, /V5_PARLIAMENT_COVERAGE_AND_BACKFILL\.md/);
  assert.match(plan, /V5_PARLIAMENT_SOURCE_CATALOGUE\.md/);
  assert.match(readme, /V5\.1 a V5\.22 integradas/);
  assert.match(readme, /V5_PARLIAMENT_COVERAGE_AND_BACKFILL\.md/);
  assert.match(readme, /V5_PARLIAMENT_SOURCE_CATALOGUE\.md/);
});
