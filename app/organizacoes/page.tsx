import type { Metadata } from "next";
import Link from "next/link";
import {
  loadPublicOrganisations,
  ORGANISATION_KIND_LABELS,
} from "@/lib/public-organisations";

export const metadata: Metadata = {
  title: "Organizações",
  description: "Organizações publicadas com fonte oficial, SHA-256 e revisão humana explícita.",
  alternates: { canonical: "/organizacoes" },
};
export const dynamic = "force-dynamic";

export default async function OrganisationsPage({ searchParams }: { searchParams: Promise<{ pagina?: string }> }) {
  const { pagina } = await searchParams;
  const parsed = Number.parseInt(pagina ?? "1", 10);
  const page = Number.isSafeInteger(parsed) && parsed > 0 ? Math.min(parsed, 500) : 1;
  const result = await loadPublicOrganisations(page);
  return <main className="page-shell shell organisation-directory">
    <header className="page-heading">
      <span className="eyebrow">Identidade pública com prova</span>
      <h1>Organizações</h1>
      <p>Cada ficha nasce de uma fonte oficial independente e de uma decisão humana específica. Uma designação igual nunca cria uma correspondência automática.</p>
    </header>
    {result.status !== "ok" ? <section className="admin-empty-state" role="status"><strong>Consulta temporariamente indisponível.</strong><p>Não apresentamos organizações antigas ou não revistas como substituição.</p></section>
      : <>
        <aside className="organisation-coverage"><strong>{result.data.total.toLocaleString("pt-PT")} organizações publicadas</strong><p>{result.data.coverage_notice}</p></aside>
        {result.data.items.length ? <section className="organisation-grid" aria-label="Organizações publicadas">{result.data.items.map((item) => <article className="card organisation-card" key={item.id}>
          <span className="eyebrow">{ORGANISATION_KIND_LABELS[item.kind]}</span><h2>{item.legal_name}</h2><p>Referência do ato: {item.registry_record_id}</p>
          <code>{item.public_record_sha256}</code><Link className="button" href={`/organizacoes/${item.id}`}>Ver prova e histórico</Link>
        </article>)}</section> : <section className="admin-empty-state"><strong>Ainda não existem fotografias publicadas.</strong><p>Dados indisponíveis não significam inexistência ou incumprimento.</p></section>}
        <nav className="organisation-pagination" aria-label="Paginação">{page > 1 ? <Link className="button" href={`/organizacoes?pagina=${page - 1}`}>Página anterior</Link> : <span />}{result.data.offset + result.data.limit < result.data.total ? <Link className="button" href={`/organizacoes?pagina=${page + 1}`}>Página seguinte</Link> : null}</nav>
      </>}
  </main>;
}
