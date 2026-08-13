import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("the V5.9 directory keeps the legacy endpoint and adds a cursor contract first", async () => {
  const [routes, model, repository] = await Promise.all([
    read("../backend/app/api/routes/public_data.py"),
    read("../backend/app/models/public_politicians.py"),
    read("../backend/app/repositories/public_politicians.py"),
  ]);

  const explorerRoute = routes.indexOf('@router.get("/politicians/explore"');
  const slugRoute = routes.indexOf('@router.get("/politicians/{slug}"');
  assert.ok(explorerRoute >= 0 && slugRoute > explorerRoute);
  assert.match(model, /total_is_exact: Literal\[True\]/);
  assert.match(model, /pagination: Literal\["CURSOR"\]/);
  assert.match(repository, /\(sort_name, slug\) >/);
  assert.match(repository, /source_archive_attestations/);
  assert.doesNotMatch(repository, /\bOFFSET\b/i);
  assert.doesNotMatch(repository, /fuzzy|similarity|levenshtein/i);
});

test("the public page uses shareable server filters and never invents an exact legacy total", async () => {
  const [page, component, loader] = await Promise.all([
    read("../app/politicos/page.tsx"),
    read("../components/politician-directory.tsx"),
    read("../lib/public-data.ts"),
  ]);

  assert.match(page, /loadPublicPoliticianDirectory/);
  assert.match(page, /if \(directory\.cursorRejected\)/);
  assert.match(page, /cursor: directory\.nextCursor/);
  assert.match(page, /directory\.paginationMode === "LEGACY_PAGE"/);
  assert.match(component, /method="get"/);
  assert.match(component, /name="q"/);
  assert.match(component, /name="grupo"/);
  assert.match(component, /total ainda não confirmado/);
  assert.match(loader, /status\.counts\.politicians === legacyPeople\.length/);
  assert.match(loader, /compatibilityMode: complete \? "LEGACY_COMPLETE" : "LEGACY_LIMITED"/);
  assert.doesNotMatch(component, /useState|useMemo/);
});

test("the V5.9 documentation preserves publication and identity boundaries", async () => {
  const [documentation, checklist, readme] = await Promise.all([
    read("../docs/V5_POLITICIAN_DIRECTORY.md"),
    read("../docs/V5_RELEASE_CHECKLIST.md"),
    read("../README.md"),
  ]);

  assert.match(documentation, /apenas\s+(?:sobre\s+)?identidades já publicadas/i);
  assert.match(documentation, /não.*fuzzy matching/is);
  assert.match(documentation, /não publica nem altera dados reais/i);
  assert.match(checklist, /\[x\] Diretório dos políticos medido e preparado/);
  assert.match(readme, /V5\.1 a V5\.10 integradas/);
  assert.match(readme, /V5_POLITICIAN_DIRECTORY\.md/);
});
