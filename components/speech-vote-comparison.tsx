"use client";

import { useState } from "react";
import { CheckIcon, ExternalLinkIcon, ShieldCheckIcon } from "@/components/icons";
import type { SpeechVoteComparisonData } from "@/types/public-data";

export function SpeechVoteComparison({ data }: { data: SpeechVoteComparisonData }) {
  const [showMethod, setShowMethod] = useState(false);
  const { statement, vote, comparison } = data;
  const excluded = Math.max(comparison.totalStatements - comparison.comparablePairs, 0);
  const outcomeLabel = {
    CONSISTENT: "CONSISTENTE",
    INCONSISTENT: "INCONSISTENTE",
    INCONCLUSIVE: "INCONCLUSIVO",
  }[comparison.outcome];

  return (
    <section className="investigator-card comparison-v2" aria-labelledby="comparison-v2-title">
      <div className="investigator-card__heading">
        <div>
          <span className="eyebrow">Discurso público vs. voto real</span>
          <h2 id="comparison-v2-title">A mesma matéria, lado a lado</h2>
        </div>
        <span className="v2-demo-chip">{data.isDemonstration ? "Amostra fictícia" : "Comparação revista"}</span>
      </div>

      <div className="comparison-topic">
        <span>Matéria comparada</span>
        <strong>{data.subject}</strong>
      </div>

      <div className="comparison-columns">
        <article className="evidence-column">
          <div className="evidence-column__top">
            <span>01 · Declaração pública</span>
            <span className="verified-chip"><ShieldCheckIcon /> Fonte identificada</span>
          </div>
          <blockquote>“{statement.quote}”</blockquote>
          <div className="evidence-column__meta">
            <strong>{statement.speaker}</strong>
            <span>{statement.date}</span>
          </div>
          <a href={statement.source.url} target="_blank" rel="noreferrer">
            <b>{statement.source.publisher}</b>
            <span>{statement.source.label}</span>
            <ExternalLinkIcon />
          </a>
        </article>

        <article className="evidence-column evidence-column--vote">
          <div className="evidence-column__top">
            <span>02 · Registo parlamentar</span>
            <span className="verified-chip"><ShieldCheckIcon /> Voto nominal</span>
          </div>
          <div className="vote-result-large"><CheckIcon /> {vote.choice}</div>
          <div className="evidence-column__meta">
            <strong>{vote.initiative}</strong>
            <span>{vote.date}</span>
          </div>
          <a href={vote.source.url} target="_blank" rel="noreferrer">
            <b>{vote.source.publisher}</b>
            <span>{vote.source.label}</span>
            <ExternalLinkIcon />
          </a>
        </article>
      </div>

      <div className="coherence-result">
        <div
          className="coherence-score"
          role="img"
          aria-label={comparison.score == null ? "Índice agregado ainda indisponível" : `${comparison.score} por cento nos pares comparáveis`}
        >
          <strong>{comparison.score == null ? "—" : `${comparison.score}%`}</strong>
          <span>{data.isDemonstration ? "nesta amostra" : "pares revistos"}</span>
        </div>
        <div className="coherence-copy">
          <span className="outcome-chip"><CheckIcon /> {outcomeLabel}</span>
          <h3>Índice de coerência factual</h3>
          <p>{comparison.rationale}</p>
          <div className="coverage-row">
            <span><strong>{comparison.comparablePairs}</strong> par comparável</span>
            <span><strong>{comparison.totalStatements}</strong> declarações analisadas</span>
            <span><strong>{excluded}</strong> excluídas por insuficiência</span>
          </div>
          <button type="button" className="method-toggle" onClick={() => setShowMethod((value) => !value)}>
            {showMethod ? "Ocultar método" : "Como é calculado?"}
          </button>
          {showMethod && (
            <div className="method-disclosure">
              <p>
                Percentagem = pares consistentes ÷ pares comparáveis revistos. Pares inconclusivos ou sobre matérias diferentes não entram no denominador.
              </p>
              <span>Versão: {comparison.methodologyVersion}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
