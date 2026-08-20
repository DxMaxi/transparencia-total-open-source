import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { loadPublicAiExplanation } from "@/lib/public-data";

export const revalidate = 60;

function formatDate(value?: string): string {
  if (!value) return "Dados indisponíveis na fonte";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Dados indisponíveis na fonte";
  return new Intl.DateTimeFormat("pt-PT", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Europe/Lisbon",
  }).format(date);
}

function safeOfficialUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ public_id: string }>;
}): Promise<Metadata> {
  const { public_id: publicId } = await params;
  const loaded = await loadPublicAiExplanation(publicId);
  if (!loaded.data) return { title: "Explicação" };
  return {
    title: loaded.data.summary.title,
    description: loaded.data.summary.summary2Minutes.slice(0, 160),
    alternates: { canonical: `/explicacoes/${publicId}` },
  };
}

export default async function AiExplanationPage({
  params,
}: {
  params: Promise<{ public_id: string }>;
}) {
  const { public_id: publicId } = await params;
  const loaded = await loadPublicAiExplanation(publicId);
  if (!loaded.data && loaded.available) notFound();

  if (!loaded.data) {
    return (
      <main className="page-shell shell ai-public-detail">
        <Link href="/explicacoes">← Todas as explicações</Link>
        <div className="endpoint-warning" role="status">
          <strong>Consulta temporariamente indisponível.</strong>
          <span>Não apresentamos uma versão antiga ou conteúdo não oficial como substituição.</span>
        </div>
      </main>
    );
  }

  const item = loaded.data;
  const officialUrl = safeOfficialUrl(item.source.url);
  return (
    <main className="page-shell shell ai-public-detail">
      <Link className="ai-public-back" href="/explicacoes">← Todas as explicações</Link>
      <header className="ai-public-detail__hero">
        <div>
          <span className="ai-label">{item.label}</span>
          <p className="eyebrow">{item.source.officialIdentifier ?? item.source.title}</p>
          <h1>{item.summary.title}</h1>
          <p>{item.summary.summary2Minutes}</p>
        </div>
        <aside>
          <strong>{item.abstained ? "Abstenção explícita" : "Revisão humana concluída"}</strong>
          <span>Publicado em {formatDate(item.editorial.publishedAt)}</span>
          <span>Revisor: {item.editorial.reviewedBy}</span>
        </aside>
      </header>

      {item.generation.sourceTruncated ? (
        <div className="endpoint-warning" role="alert">
          <strong>Documento processado parcialmente pelo modelo.</strong>
          <span>
            O revisor teve acesso ao documento arquivado; a geração recebeu {item.generation.processedCharacters.toLocaleString("pt-PT")} de {item.generation.sourceCharacters.toLocaleString("pt-PT")} caracteres.
          </span>
        </div>
      ) : null}

      <div className="ai-public-detail__grid">
        <article className="ai-public-reading card">
          <SummarySection title="O que muda" items={item.summary.whatChanges} />
          <SummarySection title="Quem é abrangido" items={item.summary.whoIsAffected} />
          <SummarySection title="Datas e prazos" items={item.summary.datesAndDeadlines} />
          <SummarySection title="Direitos e deveres" items={item.summary.dutiesAndRights} />
          <SummarySection title="Incertezas e limites" items={item.summary.uncertainties} warning />

          <section>
            <h2>Âncoras no documento oficial</h2>
            {item.summary.sourceAnchors.length ? (
              <ol className="ai-public-anchor-list">
                {item.summary.sourceAnchors.map((anchor, index) => (
                  <li key={`${anchor.section}-${index}`}>
                    <strong>{anchor.section}</strong>
                    <span>{anchor.reason}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p>Dados indisponíveis — admissível apenas numa abstenção completa.</p>
            )}
          </section>

          {item.summary.glossary.length ? (
            <section>
              <h2>Glossário</h2>
              <dl className="ai-public-glossary">
                {item.summary.glossary.map((entry) => (
                  <div key={entry.term}>
                    <dt>{entry.term}</dt>
                    <dd>{entry.explanation}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ) : null}
        </article>

        <aside className="ai-public-proof card">
          <span className="eyebrow">Fonte antes da conclusão</span>
          <h2>{item.source.title}</h2>
          <dl>
            <div><dt>Publicador</dt><dd>Diário da República</dd></div>
            <div><dt>Identificador</dt><dd>{item.source.officialIdentifier ?? "Dados indisponíveis"}</dd></div>
            <div><dt>Publicação oficial</dt><dd>{formatDate(item.source.publishedAt)}</dd></div>
            <div><dt>Recolha</dt><dd>{formatDate(item.source.retrievedAt)}</dd></div>
          </dl>
          {officialUrl ? (
            <a className="button button--primary" href={officialUrl} target="_blank" rel="noreferrer noopener">
              Abrir documento oficial
            </a>
          ) : null}
          <Proof label="SHA-256 do documento" value={item.source.contentSha256} />
          <Proof label="SHA-256 do texto" value={item.source.normalisedTextSha256} />

          <span className="eyebrow ai-public-proof__section">Transparência da geração</span>
          <dl>
            <div><dt>Fornecedor</dt><dd>{item.generation.provider}</dd></div>
            <div><dt>Modelo</dt><dd>{item.generation.model}</dd></div>
            <div><dt>Instruções</dt><dd>{item.generation.promptVersion}</dd></div>
            <div><dt>Gerado</dt><dd>{formatDate(item.generation.generatedAt)}</dd></div>
            <div><dt>Retenção pedida</dt><dd>Desativada</dd></div>
          </dl>
          <Proof label="SHA-256 das instruções" value={item.generation.promptSha256} />
          <Proof label="SHA-256 da entrada" value={item.generation.inputSha256} />
          <Proof label="SHA-256 da saída" value={item.generation.outputSha256} />
          <Proof label="SHA-256 da versão editorial" value={item.editorial.editorialVersionSha256} />
          <Proof label="SHA-256 da projeção pública" value={item.editorial.publicationProofSha256} />
          <Proof label="Referência do evento" value={item.editorial.publicationEventReferenceSha256} />
        </aside>
      </div>

      <section className="ai-public-limitations card">
        <span className="eyebrow">O que esta página não faz</span>
        <h2>Explicar não é prever, acusar ou aconselhar</h2>
        <p>
          <strong>IA não é fonte.</strong> Sem recomendação de voto, classificação partidária ou
          conclusão sobre intenções: esta explicação só torna mais legível a prova oficial indicada.
        </p>
        <ul>{item.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
        <p>
          Em caso de divergência, prevalece sempre o documento oficial. Uma correção acrescenta
          nova versão e novo histórico; nunca altera silenciosamente esta prova.
        </p>
      </section>
    </main>
  );
}

function SummarySection({
  title,
  items,
  warning = false,
}: {
  title: string;
  items: string[];
  warning?: boolean;
}) {
  return (
    <section className={warning ? "ai-public-summary ai-public-summary--warning" : "ai-public-summary"}>
      <h2>{title}</h2>
      {items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Dados indisponíveis.</p>}
    </section>
  );
}

function Proof({ label, value }: { label: string; value: string }) {
  return (
    <div className="ai-public-proof__hash">
      <span>{label}</span>
      <code>{value}</code>
    </div>
  );
}
