import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { loadPublicAiExplanations } from "@/lib/public-data";

export const metadata: Metadata = {
  title: "Explicações com IA",
  description:
    "Explicações de documentos do Diário da República geradas por IA, revistas por humanos e publicadas com fonte e hashes.",
  alternates: { canonical: "/explicacoes" },
};

export const revalidate = 60;
const PAGE_SIZE = 12;

type SearchParams = Record<string, string | string[] | undefined>;

function readText(value: string | string[] | undefined, maxLength: number): string | undefined {
  const candidate = (Array.isArray(value) ? value[0] : value)?.trim();
  return candidate ? candidate.slice(0, maxLength) : undefined;
}
function readPage(value: string | string[] | undefined): number {
  const parsed = Number.parseInt(readText(value, 8) ?? "1", 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? Math.min(parsed, 500) : 1;
}

function pageHref(query: string | undefined, page: number): string {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (page > 1) params.set("pagina", String(page));
  const suffix = params.toString();
  return `/explicacoes${suffix ? `?${suffix}` : ""}#resultados`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-PT", {
    dateStyle: "long",
    timeZone: "Europe/Lisbon",
  }).format(date);
}

const withdrawalReasonLabels: Record<string, string> = {
  EXTRACTION_OR_NORMALISATION_ERROR: "Erro de recolha, extração ou normalização",
  SOURCE_DIVERGENCE: "Divergência reproduzível com a fonte",
  OFFICIAL_SOURCE_CORRECTION: "Correção da fonte oficial",
  DUPLICATE_OR_CORRUPT_DATA: "Duplicação ou corrupção de dados",
  DOCUMENTED_METHODOLOGY_CHANGE: "Alteração metodológica documentada",
  LEGAL_OR_AUTHORITY_ORDER: "Obrigação legal ou decisão de autoridade",
  DATA_PROTECTION_OR_PERSONALITY_RIGHTS: "Proteção de dados ou direitos de personalidade",
  SECURITY_RISK: "Risco de segurança",
  THIRD_PARTY_RIGHTS: "Direitos de terceiros",
  DECLARED_SCOPE_ERROR: "Erro no âmbito declarado",
};

export default async function AiExplanationsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const query = readText(params.q, 120);
  const page = readPage(params.pagina);
  const loaded = await loadPublicAiExplanations({ query, page, pageSize: PAGE_SIZE });
  const listing = loaded.data;
  const pageCount = Math.max(1, Math.ceil(listing.total / listing.limit));
  if (listing.available && page > pageCount) redirect(pageHref(query, pageCount));

  return (
    <main className="page-shell shell ai-public-page">
      <header className="page-heading page-heading--wide ai-public-heading">
        <span className="eyebrow">IA responsável · Diário da República</span>
        <h1>Explicações com fonte, não notícias automáticas</h1>
        <p>
          A IA ajuda a transformar linguagem jurídica em leitura clara. Cada texto começa num
          documento oficial arquivado, conserva os hashes do que recebeu e só aparece aqui depois
          de comparação e publicação humana explícitas.
        </p>
        <div className="ai-public-principles" aria-label="Limites das explicações">
          <span>IA não é fonte</span>
          <span>Sem previsões políticas</span>
          <span>Sem recomendação de voto</span>
          <span>Direito a abster-se</span>
        </div>
      </header>

      <section className="ai-public-search card" aria-labelledby="ai-search-title">
        <div>
          <span className="eyebrow">Pesquisa na publicação revista</span>
          <h2 id="ai-search-title">Encontrar uma explicação</h2>
          <p>A pesquisa limita conteúdos já publicados; nunca gera uma resposta nova.</p>
        </div>
        <form method="get" action="/explicacoes">
          <label>
            Documento, título ou identificador oficial
            <input name="q" defaultValue={query} maxLength={120} placeholder="Ex.: Lei, habitação" />
          </label>
          <button className="button button--primary" type="submit">Pesquisar</button>
          {query ? <Link href="/explicacoes#resultados">Limpar</Link> : null}
        </form>
      </section>

      <section className="ai-public-results" id="resultados" aria-labelledby="ai-results-title">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Publicação ativa</span>
            <h2 id="ai-results-title">
              {listing.available
                ? `${listing.total.toLocaleString("pt-PT")} explicação(ões) revista(s)`
                : "Consulta temporariamente indisponível"}
            </h2>
          </div>
          <p>{listing.publicationRule}</p>
        </div>

        {!listing.available ? (
          <div className="endpoint-warning" role="status">
            <strong>Dados indisponíveis.</strong>
            <span>Não mostramos exemplos, notícias ou texto local como substituição.</span>
          </div>
        ) : listing.items.length ? (
          <div className="ai-public-card-grid">
            {listing.items.map((item) => (
              <article className="ai-public-card" key={item.id}>
                <header>
                  <span className="ai-label">{item.label}</span>
                  {item.abstained ? <span className="coverage-chip">Abstenção explícita</span> : null}
                </header>
                <p className="eyebrow">
                  {item.source.officialIdentifier ?? item.source.title}
                </p>
                <h3>{item.summary.title}</h3>
                <p>{item.summary.summary2Minutes}</p>
                <dl>
                  <div>
                    <dt>Fonte</dt>
                    <dd>Diário da República</dd>
                  </div>
                  <div>
                    <dt>Revisto e publicado</dt>
                    <dd>{formatDate(item.editorial.publishedAt)}</dd>
                  </div>
                </dl>
                <footer>
                  <code title={item.source.contentSha256}>
                    Fonte {item.source.contentSha256.slice(0, 12)}…
                  </code>
                  <Link className="text-link" href={`/explicacoes/${item.id}`}>
                    Ler com as provas →
                  </Link>
                </footer>
              </article>
            ))}
          </div>
        ) : (
          <div className="admin-empty-state ai-public-empty">
            <strong>Ainda não existem explicações publicadas para esta pesquisa.</strong>
            <p>
              Recolher ou gerar não basta. O primeiro conteúdo só surge depois de fonte atestada,
              revisão humana e decisão de publicação separada.
            </p>
          </div>
        )}

        {listing.available && pageCount > 1 ? (
          <nav className="politician-pagination" aria-label="Paginação das explicações">
            {page > 1 ? <Link href={pageHref(query, page - 1)}>← Anterior</Link> : <span />}
            <strong>Página {page} de {pageCount}</strong>
            {page < pageCount ? <Link href={pageHref(query, page + 1)}>Seguinte →</Link> : <span />}
          </nav>
        ) : null}
      </section>

      <section className="ai-public-history" aria-labelledby="ai-history-title">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Histórico imutável</span>
            <h2 id="ai-history-title">Publicações e retiradas</h2>
          </div>
          <p>As razões públicas são redigidas; as notas editoriais privadas nunca são expostas.</p>
        </div>
        {loaded.history.length ? (
          <ol>
            {loaded.history.map((event) => (
              <li key={event.eventReferenceSha256}>
                <div>
                  <span className={`coverage-chip ${event.action === "WITHDRAWN" ? "coverage-chip--warning" : ""}`}>
                    {event.action === "PUBLISHED" ? "Publicado" : "Retirado"}
                  </span>
                  <strong>{event.title}</strong>
                  <small>{formatDate(event.decidedAt)} · {event.actorAlias}</small>
                </div>
                <p>{event.publicRationale}</p>
                {event.reasonCategory ? (
                  <span>{withdrawalReasonLabels[event.reasonCategory] ?? event.reasonCategory}</span>
                ) : null}
                {event.publicEffect ? <em>{event.publicEffect.message}</em> : null}
                <code>{event.eventReferenceSha256}</code>
              </li>
            ))}
          </ol>
        ) : (
          <p className="admin-empty-inline">Ainda não existem eventos públicos neste circuito.</p>
        )}
      </section>
    </main>
  );
}
