import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { DataModeBanner } from "@/components/data-mode-banner";
import { PoliticianDirectory } from "@/components/politician-directory";
import { loadPublicPoliticianDirectory } from "@/lib/public-data";

export const metadata: Metadata = {
  title: "Políticos",
  description: "Perfis de titulares de cargos políticos com fonte oficial e revisão visível.",
  alternates: { canonical: "/politicos" },
};

export const revalidate = 60;

const PAGE_SIZE = 24;

type PageSearchParams = Record<string, string | string[] | undefined>;

function readString(
  value: string | string[] | undefined,
  maxLength: number,
): string | undefined {
  const candidate = (Array.isArray(value) ? value[0] : value)?.trim();
  return candidate ? candidate.slice(0, maxLength) : undefined;
}

function readPage(value: string | string[] | undefined): number {
  const parsed = Number.parseInt(readString(value, 8) ?? "1", 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? Math.min(parsed, 500) : 1;
}

function buildDirectoryHref(
  state: { query?: string; partyShort?: string },
  pagination: { cursor?: string; page?: number } = {},
): string {
  const query = new URLSearchParams();
  if (state.query) query.set("q", state.query);
  if (state.partyShort) query.set("grupo", state.partyShort);
  if (pagination.cursor) query.set("cursor", pagination.cursor);
  if (pagination.page && pagination.page > 1) query.set("pagina", String(pagination.page));
  const suffix = query.toString();
  return `/politicos${suffix ? `?${suffix}` : ""}#diretorio`;
}

export default async function PoliticiansPage({
  searchParams,
}: {
  searchParams: Promise<PageSearchParams>;
}) {
  const params = await searchParams;
  const query = readString(params.q, 120);
  const partyShort = readString(params.grupo, 50);
  const cursor = readString(params.cursor, 512);
  const page = readPage(params.pagina);
  const loaded = await loadPublicPoliticianDirectory({
    query,
    partyShort,
    cursor,
    page,
    pageSize: PAGE_SIZE,
  });
  const directory = loaded.data;
  const state = { query, partyShort };
  if (directory.cursorRejected) {
    redirect(buildDirectoryHref(state));
  }
  const pageCount = Math.max(1, Math.ceil(directory.total / directory.limit));
  if (
    directory.paginationMode === "LEGACY_PAGE"
    && directory.totalIsExact
    && page > pageCount
  ) {
    redirect(buildDirectoryHref(state, { page: pageCount }));
  }
  const nextHref = directory.nextCursor
    ? buildDirectoryHref(state, { cursor: directory.nextCursor })
    : directory.hasNext
      ? buildDirectoryHref(state, { page: directory.currentPage + 1 })
      : undefined;
  const previousHref = directory.hasPrevious
    ? directory.paginationMode === "CURSOR"
      ? buildDirectoryHref(state)
      : buildDirectoryHref(state, { page: directory.currentPage - 1 })
    : undefined;

  return (
    <main className="page-shell shell">
      <header className="page-heading">
        <span className="eyebrow">Diretório auditável</span>
        <h1>Políticos</h1>
        <p>
          Só aparecem identidades observadas numa fonte oficial arquivada e aprovadas por revisão
          humana. Cada ficha separa mandatos, presenças, iniciativas, votos e declarações, e mostra
          claramente quando uma dessas áreas ainda não tem cobertura publicável.
        </p>
      </header>
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <PoliticianDirectory
        directory={directory}
        nextHref={nextHref}
        previousHref={previousHref}
      />
    </main>
  );
}
