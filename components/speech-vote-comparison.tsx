"use client";

import { useId, useState } from "react";
import { CheckIcon, ExternalLinkIcon, ShieldCheckIcon } from "@/components/icons";
import type { SpeechVoteComparisonData } from "@/types/public-data";

export function SpeechVoteComparison({ data }: { data: SpeechVoteComparisonData }) {
  const [showMethod, setShowMethod] = useState(false);
  const { statement, vote, comparison } = data;
  const titleId = useId();
  const outcomeLabel = {
    CONSISTENT: "CONSISTENTE",
    INCONSISTENT: "INCONSISTENTE",
    INCONCLUSIVE: "INCONCLUSIVO",
  }[comparison.outcome];

  return (
    <section className="investigator-card comparison-v2" aria-labelledby={titleId}>
      <div className="investigator-card__heading">
        <div>
          <span className="eyebrow">Discurso público vs. voto real</span>
          <h2 id={titleId}>A mesma matéria, lado a lado</h2>
        </div>
        <span className="review-state-chip">Comparação revista</span>
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
        <div className="coherence-copy">
          <span className="outcome-chip"><CheckIcon /> {outcomeLabel}</span>
          <h3>Resultado deste par</h3>
          <p>{comparison.rationale}</p>
          <p>Esta revisão abrange apenas a declaração e o voto apresentados. Não representa uma avaliação global da pessoa.</p>
          <button type="button" className="method-toggle" onClick={() => setShowMethod((value) => !value)}>
            {showMethod ? "Ocultar método" : "Método e limites"}
          </button>
          {showMethod && (
            <div className="method-disclosure">
              <p>
                Um índice agregado exige um universo revisto, período e metodologia comuns. Esses elementos não estão comprovados por este par; não são apresentados percentagens ou totais de cobertura.
              </p>
              <span>Versão: {comparison.methodologyVersion}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
