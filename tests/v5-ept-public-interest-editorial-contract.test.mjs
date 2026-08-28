import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("V5.46 admits only private public-interest metadata with exact EPT proof", async () => {
  const [schema, migration, model, staging, editorial, script] = await Promise.all([
    source("prisma/schema.prisma"),
    source("prisma/migrations/20260828224500_v5_ept_public_interest_editorial/migration.sql"),
    source("backend/app/models/ept_declaration.py"),
    source("backend/app/repositories/ept_declaration_staging.py"),
    source("backend/app/repositories/ept_declaration_editorial.py"),
    source("backend/scripts/stage_ept_public_interest.py"),
  ]);

  assert.match(schema, /model EptPublicInterestObservation/);
  assert.match(schema, /officialSubjectDigest[\s\S]*@db\.Char\(64\)/);
  assert.doesNotMatch(schema, /officialSubjectId\s+String/);
  assert.match(migration, /public_access_scope[^]*PUBLIC_INTEREST_REGISTER/);
  assert.match(migration, /declaration_type[^]*INTEREST_REGISTER/);
  assert.match(migration, /source\."official_identifier" = NEW\."official_declaration_id"/);
  assert.match(migration, /source\."publisher" = 'TRANSPARENCY_ENTITY'/);
  assert.match(migration, /source\."kind" = 'DECLARATION'/);
  assert.match(migration, /source\."url" NOT IN/);
  assert.match(migration, /tribunalconstitucional\\\.pt\|entidadetransparencia\\\.pt/);
  assert.match(migration, /archive\."content_sha256" = source\."content_sha256"/);
  assert.match(migration, /BEFORE UPDATE OR DELETE/);
  assert.match(migration, /UPDATE e DELETE são proibidos/);
  assert.match(migration, /LANGUAGE plpgsql SET search_path = pg_catalog, public/);
  assert.match(migration, /LANGUAGE plpgsql SET search_path = pg_catalog;/);
  assert.match(migration, /ENABLE ROW LEVEL SECURITY/);
  assert.match(migration, /REVOKE ALL PRIVILEGES[^]*ept_public_interest_observations/);
  assert.match(migration, /ARRAY\['anon', 'authenticated'\]/);

  assert.match(model, /official_subject_identifier: SecretStr/);
  assert.match(staging, /hmac_private_reference_identifier/);
  assert.match(staging, /protected_identifier_pepper/);
  assert.match(staging, /PROTECTED_IDENTIFIER_PEPPER não configurado/);
  assert.match(staging, /is_individual_ept_source_url/);
  assert.match(staging, /STAGED_PRIVATE/);
  assert.doesNotMatch(staging, /INSERT INTO (people|asset_declaration_metadata|data_publication_reviews)/i);
  assert.match(script, /getpass\(/);
  assert.doesNotMatch(script, /--subject-identifier/);
  assert.match(script, /PROTECTED_IDENTIFIER_PEPPER não configurado/);
  assert.ok(
    script.indexOf("PROTECTED_IDENTIFIER_PEPPER não configurado") <
      script.indexOf("await repository.connect()"),
  );

  assert.match(editorial, /EPT_PUBLIC_INTEREST_OBSERVATION/);
  assert.match(editorial, /UNLINKED_PRIVATE/);
  assert.match(editorial, /REQUIRED_BEFORE_ANY_PUBLICATION/);
  assert.match(editorial, /name_matching_allowed[^]*False/);
  assert.doesNotMatch(editorial, /INSERT INTO (people|asset_declaration_metadata|data_publication_reviews)/i);
  assert.doesNotMatch(editorial, /similarity\s*\(|levenshtein\s*\(|rapidfuzz|fuzzywuzzy/i);
});

test("V5.46 exposes a private review page and closes the generic public bypass", async () => {
  const [routes, dependencies, requestModel, action, page, types, postgres, reviewScript, docs, checklist] =
    await Promise.all([
      source("backend/app/api/routes/editorial.py"),
      source("backend/app/api/dependencies.py"),
      source("backend/app/models/ept_declaration.py"),
      source("app/admin/revisao/actions.ts"),
      source("app/admin/revisao/declaracoes/page.tsx"),
      source("lib/editorial-types.ts"),
      source("backend/app/repositories/postgres.py"),
      source("backend/scripts/review_publication.py"),
      source("docs/V5_EPT_PUBLIC_INTEREST_EDITORIAL.md"),
      source("docs/V5_RELEASE_CHECKLIST.md"),
    ]);

  assert.match(routes, /@router\.get\("\/ept\/public-interest-candidates"\)/);
  assert.match(routes, /@router\.post\("\/ept\/public-interest-proposals"/);
  assert.match(routes, /Depends\(require_editorial_staff\)/);
  assert.match(dependencies, /EptDeclarationEditorialRepository/);
  for (const confirmation of [
    "confirm_private_only",
    "confirm_public_interest_register_only",
    "confirm_no_income_or_asset_content",
    "confirm_no_name_matching",
    "confirm_identity_unlinked",
    "confirm_independent_legal_review_required",
  ]) {
    assert.match(`${requestModel}\n${types}\n${routes}`, new RegExp(confirmation));
    assert.match(action, new RegExp(`"${confirmation}"`));
    assert.match(page, new RegExp(`name="${confirmation}"`));
  }
  assert.match(page, /O portal geral não prova uma declaração individual/);
  assert.match(page, /dados indisponíveis/i);
  assert.match(page, /Não criada/);
  assert.match(postgres, /event\.target_type = 'EPT_PUBLIC_INTEREST_DECLARATION'/);
  assert.match(postgres, /publication_event\.action = 'PUBLISH'/);
  assert.match(postgres, /porta editorial EPT específica/);
  assert.match(reviewScript, /já não pode ser publicada pelo comando genérico/);
  assert.match(docs, /artigo 17\.º da Lei n\.º 52\/2019/);
  assert.match(docs, /zero:[^]*AssetDeclarationMetadata/);
  assert.match(checklist, /\[x\] V5\.46 — entrada privada EPT/);
});
