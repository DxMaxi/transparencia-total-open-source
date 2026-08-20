import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REQUIRED_CSS_MARKERS = [
  ".parliament-page--v551",
  ".parliament-search-form__primary",
  ".parliament-coverage__facts",
  ".contact-channel--pending",
  ".profile-coverage-grid",
  ".profile-declaration-list",
  ".ai-publication-panel",
  ".ai-public-card-grid",
  ".ai-public-detail__hero",
  ".global-search-box",
  ".global-search-result__proof",
];

async function cssFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) files.push(...await cssFiles(path));
    else if (entry.name.endsWith(".css")) files.push(path);
  }
  return files;
}

export async function verifyNextArtifact(projectRoot = process.cwd()) {
  const staticDirectory = resolve(projectRoot, ".next", "static");
  let files;
  try {
    files = await cssFiles(staticDirectory);
  } catch {
    throw new Error("Artefacto Next.js ausente: execute primeiro npm run build:next.");
  }
  if (!files.length) throw new Error("O artefacto Next.js não contém ficheiros CSS.");
  const bundledCss = (await Promise.all(files.map((file) => readFile(file, "utf8")))).join("\n");
  const missing = REQUIRED_CSS_MARKERS.filter((marker) => !bundledCss.includes(marker));
  if (missing.length) {
    throw new Error(`CSS público incompleto no artefacto: ${missing.join(", ")}`);
  }
  return { cssFiles: files.length, markers: REQUIRED_CSS_MARKERS.length };
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  verifyNextArtifact()
    .then((result) => {
      console.log(
        `Artefacto Next.js verificado: ${result.cssFiles} ficheiros CSS, ${result.markers} marcadores públicos.`,
      );
    })
    .catch((error) => {
      console.error(error.message);
      process.exitCode = 1;
    });
}
