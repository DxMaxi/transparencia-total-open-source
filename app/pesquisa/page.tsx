import type { Metadata } from "next";
import Link from "next/link";
import { SearchIcon } from "@/components/icons";
import { loadPublicGlobalSearch } from "@/lib/public-data";

export const metadata: Metadata = {
  title: "Pesquisa global",
  description:
    "Pesquisa políticos, atividade parlamentar, promessas e explicações já publicadas, sempre com fonte, data, hash e cobertura.",
  alternates: { canonical: "/pesquisa" },
};

export const revalidate = 60;

type SearchParams = Record<string, string | string[] | undefined>;

function readText(value: string | string[] | undefined, maxLength: number): string {
  return ((Array.isArray(value) ? value[0] : value) ?? "").trim().slice(0, maxLength);
}

function formatDate(value?: string): string {
  if (!value) return "Data não indicada";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Data não indicada";
  return new Intl.DateTimeFormat("pt-PT", {
    dateStyle: "long",
    timeZone: "Europe/Lisbon",
  }).format(date);
}

function resultLabel(total: number): string {
  return total === 1 ? "1 resultado publicado" : `${total.toLocaleString("pt-PT")} resultados publicados`;
}

export default async function GlobalSearchPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const parameters = await searchParams;
  const query = readText(parameters.q, 120);
  const canSearch = query.length >= 2;
  const search = canSearch ? await loadPublicGlobalSearch(query) : null;
  const resultSections = search?.sections.filter(
    (section) => section.availability === "UNAVAILABLE" || (section.total ?? 0) > 0,
  ) ?? [];

  return (
    <main className="page-shell shell global-search-page">
      <header className="page-heading page-heading--wide global-search-heading">
        <span className="eyebrow">Uma porta para a informação publicada</span>
        <h1>Pesquisar a atividade pública</h1>
        <p>
          Encontre pessoas, reuniões, iniciativas, votações, compromissos e explicações de IA.
          Cada resultado mostra de onde veio, quando foi recolhido e revisto, e o que a cobertura
          permite afirmar — sem procurar em dados privados ou por rever.
        </p>
      </header>

      <section className="global-search-box card" aria-labelledby="global-search-title">
        <div>
          <span className="eyebrow">Pesquisa global</span>
          <h2 id="global-search-title">O que procura?</h2>
          <p>Use um tema, nome, número oficial ou expressão com pelo menos dois caracteres.</p>
        </div>
        <form action="/pesquisa" method="get" role="search">
          <label htmlFor="global-search-query">Tema, pessoa ou documento</label>
          <div>
            <SearchIcon />
            <input
              id="global-search-query"
              name="q"
              type="search"
              defaultValue={query}
              minLength={2}
              maxLength={120}
              placeholder="Ex.: habitação, orçamento, nome de deputado"
              autoComplete="off"
            />
            <button className="button button--primary" type="submit">Pesquisar</button>
          </div>
        </form>
      </section>

      {!query ? (
        <section className="global-search-intro" aria-labelledby="search-scope-title">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Cobertura transparente</span>
              <h2 id="search-scope-title">Seis áreas, sem ranking artificial</h2>
            </div>
            <p>As contagens permanecem separadas porque uma votação não é comparável a uma pessoa.</p>
          </div>
          <div className="global-search-scope-grid">
            {[
              ["Políticos", "Identidades oficiais já publicadas"],
              ["Reuniões", "Fotografias parlamentares revistas"],
              ["Iniciativas", "Títulos e números da fonte oficial"],
              ["Votações", "Resultados publicados sem inferir impacto"],
              ["Promessas", "Compromissos e provas aprovados"],
              ["Explicações IA", "Textos publicados após revisão humana"],
            ].map(([title, description]) => (
              <article className="card" key={title}>
                <strong>{title}</strong>
                <span>{description}</span>
              </article>
            ))}
          </div>
        </section>
      ) : !canSearch ? (
        <div className="endpoint-warning" role="status">
          <strong>Pesquisa demasiado curta.</strong>
          <span>Introduza pelo menos dois caracteres para limitar a consulta publicada.</span>
        </div>
      ) : !search?.available ? (
        <div className="endpoint-warning" role="status">
          <strong>Pesquisa temporariamente indisponível.</strong>
          <span>Não apresentamos listas antigas, exemplos locais ou dados por rever como substituição.</span>
        </div>
      ) : (
        <section className="global-search-results" id="resultados" aria-labelledby="search-results-title">
          <div className="global-search-summary card">
            <div>
              <span className="eyebrow">Resultado publicado</span>
              <h2 id="search-results-title">{resultLabel(search.totalResults)} para “{search.query}”</h2>
            </div>
            <dl>
              <div>
                <dt>Áreas consultadas</dt>
                <dd>{search.availableSections}</dd>
              </div>
              <div>
                <dt>Indisponíveis</dt>
                <dd>{search.unavailableSections}</dd>
              </div>
            </dl>
            <p>{search.publicationRule}</p>
          </div>

          {search.totalResults === 0 ? (
            <div className="admin-empty-state global-search-empty">
              <strong>
                Nenhum resultado publicado nas áreas {search.unavailableSections ? "disponíveis" : "consultadas"}.
              </strong>
              <p>
                Isto não prova que o assunto não exista. Significa apenas que não foi encontrado
                nas projeções atualmente publicadas e dentro da cobertura declarada
                {search.unavailableSections ? "; as áreas indisponíveis não foram substituídas" : ""}.
              </p>
            </div>
          ) : null}

          <div className="global-search-sections">
            {resultSections.map((section) => (
              <section className="global-search-section" key={section.kind} aria-labelledby={`section-${section.kind}`}>
                <header>
                  <div>
                    <span className="eyebrow">{section.availability === "AVAILABLE" ? "Fonte consultada" : "Cobertura interrompida"}</span>
                    <h2 id={`section-${section.kind}`}>{section.label}</h2>
                  </div>
                  {section.availability === "AVAILABLE" ? (
                    <strong>{resultLabel(section.total ?? 0)}</strong>
                  ) : (
                    <span className="coverage-chip coverage-chip--warning">Dados indisponíveis</span>
                  )}
                </header>
                <p className="global-search-section__coverage">{section.coverageNote}</p>

                {section.availability === "AVAILABLE" ? (
                  <div className="global-search-result-list">
                    {section.items.map((item) => (
                      <article className="global-search-result card" key={`${item.kind}-${item.id}`}>
                        <div className="global-search-result__body">
                          <span className="coverage-chip">Publicado e revisto</span>
                          <h3><Link href={item.href}>{item.title}</Link></h3>
                          <p>{item.description}</p>
                          <small>{item.coverageNote}</small>
                        </div>
                        <dl className="global-search-result__proof">
                          <div>
                            <dt>Fonte oficial</dt>
                            <dd>
                              <a href={item.source.url} target="_blank" rel="noreferrer">
                                {item.source.label}
                              </a>
                            </dd>
                          </div>
                          <div>
                            <dt>Recolhida</dt>
                            <dd>{formatDate(item.source.retrievedAt)}</dd>
                          </div>
                          <div>
                            <dt>Revista</dt>
                            <dd>{formatDate(item.verifiedAt)}</dd>
                          </div>
                          <div>
                            <dt>SHA-256 da fonte</dt>
                            <dd><code title={item.source.sha256}>{item.source.sha256?.slice(0, 16)}…</code></dd>
                          </div>
                        </dl>
                        <Link className="text-link global-search-result__open" href={item.href}>
                          Abrir com contexto →
                        </Link>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="endpoint-warning" role="status">
                    <strong>Esta área não respondeu.</strong>
                    <span>As restantes áreas mantêm os seus resultados e critérios próprios.</span>
                  </div>
                )}

                <Link className="button button--ghost global-search-section__all" href={section.viewAllHref}>
                  Ver toda a área
                </Link>
              </section>
            ))}
          </div>

          <aside className="global-search-rule card" role="note">
            <strong>O que esta pesquisa não faz</strong>
            <p>{search.searchRule}</p>
          </aside>
        </section>
      )}
    </main>
  );
}
