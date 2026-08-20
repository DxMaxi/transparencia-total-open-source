import Link from "next/link";
import type { AiDreSourceEvidence } from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

type AiSummaryView = {
  title: string;
  summary: string;
  whatChanges: string[];
  affected: string[];
  dates: string[];
  duties: string[];
  uncertainties: string[];
  glossary: Array<{ term: string; explanation: string }>;
  anchors: Array<{ section: string; reason: string }>;
  abstained: boolean;
  provider: string;
  model: string;
  promptVersion: string;
  promptSha256: string;
  generatedAt: string;
  processedCharacters: number;
  sourceTruncated: boolean;
};

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function textList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function parseAiSummary(value: Record<string, unknown>): AiSummaryView | null {
  const summary = record(value.summary);
  const generation = record(value.generation);
  if (!summary || !generation) return null;
  const title = text(summary.title);
  const summaryText = text(summary.summary_2_minutes);
  if (!title || !summaryText) return null;

  const glossary = Array.isArray(summary.glossary)
    ? summary.glossary.flatMap((item) => {
        const entry = record(item);
        const term = text(entry?.term);
        const explanation = text(entry?.explanation);
        return term && explanation ? [{ term, explanation }] : [];
      })
    : [];
  const anchors = Array.isArray(summary.source_anchors)
    ? summary.source_anchors.flatMap((item) => {
        const entry = record(item);
        const section = text(entry?.section);
        const reason = text(entry?.reason);
        return section && reason ? [{ section, reason }] : [];
      })
    : [];

  return {
    title,
    summary: summaryText,
    whatChanges: textList(summary.what_changes),
    affected: textList(summary.who_is_affected),
    dates: textList(summary.dates_and_deadlines),
    duties: textList(summary.duties_and_rights),
    uncertainties: textList(summary.uncertainties),
    glossary,
    anchors,
    abstained: value.abstained === true,
    provider: text(generation.provider),
    model: text(generation.model),
    promptVersion: text(generation.prompt_version),
    promptSha256: text(generation.prompt_sha256),
    generatedAt: text(generation.generated_at),
    processedCharacters:
      typeof generation.processed_characters === "number" ? generation.processed_characters : 0,
    sourceTruncated: generation.source_truncated === true,
  };
}

function safeOfficialSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function AiEditorialComparison({
  evidence,
  normalizedData,
  normalizedSha256,
  origin,
  createdByAlias,
}: {
  evidence: AiDreSourceEvidence;
  normalizedData: Record<string, unknown>;
  normalizedSha256: string;
  origin: "HUMAN" | "INGESTION" | "AI";
  createdByAlias: string;
}) {
  const proposal = parseAiSummary(normalizedData);
  const officialUrl = safeOfficialSourceUrl(evidence.source_url);

  return (
    <section className="ai-review-comparison" aria-label="Comparação da proposta de IA com o DRE">
      <article className="ai-source-document">
        <header>
          <div>
            <p className="eyebrow">Fonte oficial arquivada</p>
            <h2>{evidence.title}</h2>
            <p>{evidence.official_identifier ?? "Identificador indisponível na fonte"}</p>
          </div>
          {officialUrl ? (
            <a className="button" href={officialUrl} target="_blank" rel="noreferrer noopener">
              Abrir no DRE
            </a>
          ) : null}
        </header>
        <dl className="ai-evidence-grid">
          <div>
            <dt>Recolhido</dt>
            <dd>{dateFormatter.format(new Date(evidence.retrieved_at))}</dd>
          </div>
          <div>
            <dt>Texto verificado</dt>
            <dd>{evidence.source_characters.toLocaleString("pt-PT")} caracteres</dd>
          </div>
          <div>
            <dt>SHA-256 da fonte</dt>
            <dd><code>{evidence.source_content_sha256}</code></dd>
          </div>
          <div>
            <dt>SHA-256 do texto</dt>
            <dd><code>{evidence.normalised_text_sha256}</code></dd>
          </div>
          <div>
            <dt>Atestação do arquivo</dt>
            <dd><code>{evidence.archive.attestation_sha256}</code></dd>
          </div>
        </dl>
        <p className="ai-review-rule">{evidence.review_rule}</p>
        <nav className="ai-source-pagination" aria-label="Percorrer o texto oficial">
          <span>
            Caracteres {(evidence.text_offset + 1).toLocaleString("pt-PT")}–{evidence.text_end.toLocaleString("pt-PT")} de {evidence.source_characters.toLocaleString("pt-PT")}
          </span>
          <div>
            {evidence.has_previous_text ? (
              <Link
                href={`/admin/revisao/${encodeURIComponent(evidence.case_id)}?source_offset=${Math.max(0, evidence.text_offset - evidence.text_limit)}#texto-dre`}
              >
                Excerto anterior
              </Link>
            ) : null}
            {evidence.has_next_text ? (
              <Link
                href={`/admin/revisao/${encodeURIComponent(evidence.case_id)}?source_offset=${evidence.text_end}#texto-dre`}
              >
                Excerto seguinte
              </Link>
            ) : null}
          </div>
        </nav>
        <pre
          className="ai-source-text"
          id="texto-dre"
          tabIndex={0}
          aria-label="Texto oficial extraído do DRE"
        >
          {evidence.extracted_text}
        </pre>
      </article>

      <article className="ai-summary-document">
        <header>
          <div>
            <p className="eyebrow">
              {origin === "AI" ? "Proposta do modelo · por rever" : "Correção humana · por rever"}
            </p>
            <h2>{proposal?.title ?? "Estrutura da proposta indisponível"}</h2>
            <p>Origem técnica: {createdByAlias}</p>
          </div>
          <span className="admin-state state-pending">
            {proposal?.abstained ? "Abstenção explícita" : "Revisão obrigatória"}
          </span>
        </header>

        {proposal ? (
          <>
            {proposal.sourceTruncated ? (
              <p className="private-message private-message--error" role="alert">
                O modelo recebeu apenas {proposal.processedCharacters.toLocaleString("pt-PT")} de {evidence.source_characters.toLocaleString("pt-PT")} caracteres. Não aprove sem verificar o conteúdo omitido.
              </p>
            ) : null}
            <section className="ai-summary-lead">
              <h3>Leitura em dois minutos</h3>
              <p>{proposal.summary}</p>
            </section>
            <div className="ai-summary-sections">
              <SummaryList title="O que muda" items={proposal.whatChanges} />
              <SummaryList title="Quem é abrangido" items={proposal.affected} />
              <SummaryList title="Datas e prazos" items={proposal.dates} />
              <SummaryList title="Direitos e deveres" items={proposal.duties} />
              <SummaryList title="Incertezas e limites" items={proposal.uncertainties} warning />
            </div>
            <section className="ai-anchor-section">
              <h3>Âncoras a confirmar no texto</h3>
              {proposal.anchors.length ? (
                <ol>
                  {proposal.anchors.map((anchor, index) => (
                    <li key={`${anchor.section}-${index}`}>
                      <strong>{anchor.section}</strong>
                      <span>{anchor.reason}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p>Dados indisponíveis na proposta. Só é admissível numa abstenção completa.</p>
              )}
            </section>
            {proposal.glossary.length ? (
              <section className="ai-glossary-section">
                <h3>Glossário proposto</h3>
                <dl>
                  {proposal.glossary.map((item) => (
                    <div key={item.term}>
                      <dt>{item.term}</dt>
                      <dd>{item.explanation}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null}
            <footer className="ai-generation-proof">
              <dl>
                <div><dt>Fornecedor</dt><dd>{proposal.provider || "Dados indisponíveis"}</dd></div>
                <div><dt>Modelo</dt><dd>{proposal.model || "Dados indisponíveis"}</dd></div>
                <div><dt>Prompt</dt><dd>{proposal.promptVersion || "Dados indisponíveis"}</dd></div>
                <div>
                  <dt>Gerado</dt>
                  <dd>{proposal.generatedAt ? dateFormatter.format(new Date(proposal.generatedAt)) : "Dados indisponíveis"}</dd>
                </div>
              </dl>
              <span>SHA-256 do prompt</span>
              <code>{proposal.promptSha256 || "Dados indisponíveis"}</code>
              <span>SHA-256 desta versão editorial</span>
              <code>{normalizedSha256}</code>
            </footer>
          </>
        ) : (
          <div className="ai-invalid-proposal">
            <strong>Não foi possível apresentar a proposta de forma estruturada.</strong>
            <p>Os dados brutos continuam disponíveis no histórico para diagnóstico e correção.</p>
            <pre>{JSON.stringify(normalizedData, null, 2)}</pre>
          </div>
        )}
      </article>
    </section>
  );
}

function SummaryList({
  title,
  items,
  warning = false,
}: {
  title: string;
  items: string[];
  warning?: boolean;
}) {
  return (
    <section className={warning ? "ai-summary-block ai-summary-block--warning" : "ai-summary-block"}>
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
        </ul>
      ) : (
        <p>Dados indisponíveis na proposta.</p>
      )}
    </section>
  );
}
