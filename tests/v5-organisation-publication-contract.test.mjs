import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("V5.53 keeps identity and publication as separate human-reviewed processes", async () => {
  const [models, editorial, repository, routes, types, casePage] = await Promise.all([
    read("backend/app/models/base_organisation.py"),
    read("backend/app/models/editorial.py"),
    read("backend/app/repositories/base_organisation_publication.py"),
    read("backend/app/api/routes/editorial.py"),
    read("lib/editorial-types.ts"),
    read("app/admin/revisao/[case_id]/page.tsx"),
  ]);

  assert.match(editorial, /ORGANISATION_PUBLICATION = "ORGANISATION_PUBLICATION"/);
  assert.match(models, /class OrganisationPublicationProposalRequest/);
  assert.match(models, /confirm_separate_review: Literal\[True\]/);
  assert.match(models, /confirm_identity_remains_private: Literal\[True\]/);
  assert.match(models, /confirm_zero_graph: Literal\[True\]/);
  assert.match(repository, /kind=EditorialCaseKind\.ORGANISATION_PUBLICATION/);
  assert.match(repository, /origin_alias="organisation-publication-proposal"/);
  assert.match(repository, /current_state"\] == "APPROVED"/);
  assert.match(routes, /require_editorial_admin/);
  assert.match(
    types,
    /ORGANISATION_PUBLICATION: "Publicação de organização \(âmbito próprio\)"/,
  );
  assert.match(casePage, /OrganisationPublicationAction/);
  assert.match(casePage, /O NIPC e o HMAC nunca entram na fotografia/);
});

test("V5.53 database gate is immutable, fail-closed and creates no graph", async () => {
  const [migration, schema, repository] = await Promise.all([
    read("prisma/migrations/20260903140000_v5_organisation_publication/migration.sql"),
    read("prisma/schema.prisma"),
    read("backend/app/repositories/base_organisation_publication.py"),
  ]);

  assert.match(schema, /model BasePublicOrganisationPublicationSnapshot/);
  assert.match(schema, /currentPublicationSnapshotId\s+String\?\s+@unique/);
  assert.match(migration, /organizações legadas exigem avaliação própria/);
  assert.match(migration, /base_public_organisation_snapshot_immutable/);
  assert.match(migration, /base_public_organisation_snapshot_no_truncate/);
  assert.match(migration, /publication_reviews_no_truncate/);
  assert.match(migration, /interest_entities_block_v553_organisation/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration, /REVOKE ALL ON base_public_organisation_publication_snapshots FROM PUBLIC/);
  assert.match(migration, /assert_v553_organisation_final_state/);
  assert.doesNotMatch(repository, /INSERT INTO interest_entities/);
  assert.doesNotMatch(repository, /INSERT INTO public_contract_parties/);
  assert.doesNotMatch(repository, /INSERT INTO contract_match_reviews/);
  assert.doesNotMatch(repository, /INSERT INTO interest_relationships/);
  assert.doesNotMatch(repository, /DELETE FROM (?:organisations|rights_of_reply)/);
});

test("V5.53 public projection has no private identifier and never falls back", async () => {
  const [publicModel, publicRepository, publicRoutes, frontend, detail, replyForm] =
    await Promise.all([
      read("backend/app/models/public_organisations.py"),
      read("backend/app/repositories/public_organisations.py"),
      read("backend/app/api/routes/public_organisations.py"),
      read("lib/public-organisations.ts"),
      read("app/organizacoes/[public_id]/page.tsx"),
      read("components/right-of-reply-form.tsx"),
    ]);

  assert.match(publicRoutes, /no-store, max-age=0, must-revalidate/);
  assert.match(publicRoutes, /HTTPException\(404, "Organização não publicada ou retirada"\)/);
  assert.match(publicRepository, /publication_status='PUBLISHED'/);
  assert.match(publicRepository, /target_type='BASE_PUBLIC_ORGANISATION'/);
  assert.match(
    publicRepository,
    /snapshot\.public_record_sha256=reply\.original_record_sha256/,
  );
  assert.doesNotMatch(publicModel, /protected_identifier_digest|identity_observation_id|nipc/i);
  assert.doesNotMatch(publicRepository, /protected_identifier_digest|identity_observation_id/);
  assert.match(frontend, /cache: "no-store"/);
  assert.match(frontend, /url\.port !== ""/);
  assert.match(frontend, /status: "unavailable"/);
  assert.match(
    detail,
    /const withdrawn = active\.status === "not_found" && history\.status === "ok"/,
  );
  assert.match(detail, /PublishedReplies replies=\{history\.data\.replies\}/);
  assert.match(detail, /RightOfReplyForm/);
  assert.match(replyForm, /type: "ORGANISATION"/);
  assert.match(replyForm, /A resposta é anexada|registo original/i);
});

test("V5.53 is documented as code-only until staging and production gates pass", async () => {
  const [methodology, readiness, checklist, packageJson] = await Promise.all([
    read("docs/V5_BASE_ORGANISATION_PUBLICATION.md"),
    read("docs/V5_OPERATIONAL_READINESS.md"),
    read("docs/V5_RELEASE_CHECKLIST.md"),
    read("package.json"),
  ]);

  assert.match(methodology, /Não publica o identificador fiscal/);
  assert.match(methodology, /não ativam staging ou produção/i);
  assert.match(readiness, /Próximo desenvolvimento: V5\.54/);
  assert.match(checklist, /\[x\] V5\.53 — publicação e retirada específicas/);
  assert.match(
    JSON.parse(packageJson).scripts["test:frontend"],
    /v5-organisation-publication-contract\.test\.mjs/,
  );
});
