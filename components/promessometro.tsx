"use client";

import { useMemo, useState } from "react";
import { CheckIcon, ClockIcon } from "@/components/icons";
import { SourceLink } from "@/components/source-link";
import type { GovernmentPromise, PromiseStatus } from "@/types/domain";

const statusMeta: Record<PromiseStatus, { label: string; description: string }> = {
  UNVERIFIED: {
    label: "Por verificar",
    description: "Compromisso catalogado; execução ainda sem decisão editorial",
  },
  NOT_STARTED: {
    label: "Não iniciada",
    description: "Revisão humana fundamentada; nunca inferida apenas por falta de dados",
  },
  IN_PROGRESS: {
    label: "Em curso",
    description: "Há atos oficiais verificáveis, mas a execução ainda decorre",
  },
  PARTIAL: {
    label: "Parcialmente cumprida",
    description: "Só uma parte verificável dos critérios está documentada",
  },
  FULFILLED: {
    label: "Cumprida",
    description: "As provas revistas satisfazem integralmente os critérios publicados",
  },
};

const filters: Array<{ value: "ALL" | PromiseStatus; label: string }> = [
  { value: "ALL", label: "Todas" },
  { value: "UNVERIFIED", label: "Por verificar" },
  { value: "NOT_STARTED", label: "Não iniciadas" },
  { value: "IN_PROGRESS", label: "Em curso" },
  { value: "PARTIAL", label: "Parcialmente cumpridas" },
  { value: "FULFILLED", label: "Cumpridas" },
];

export function Promessometro({
  promises,
  initialQuery = "",
}: {
  promises: GovernmentPromise[];
  initialQuery?: string;
}) {
  const [activeFilter, setActiveFilter] = useState<"ALL" | PromiseStatus>("ALL");
  const [area, setArea] = useState("ALL");
  const [query, setQuery] = useState(initialQuery);

  const areas = useMemo(
    () => [...new Set(promises.map((promise) => promise.area))].sort(),
    [promises],
  );

  const filtered = promises.filter((promise) => {
    const statusMatches = activeFilter === "ALL" || promise.status === activeFilter;
    const areaMatches = area === "ALL" || promise.area === area;
    const needle = query.trim().toLocaleLowerCase("pt-PT");
    const queryMatches = !needle || [promise.title, promise.area, promise.rationale]
      .join(" ")
      .toLocaleLowerCase("pt-PT")
      .includes(needle);
    return statusMatches && areaMatches && queryMatches;
  });

  const counts = promises.reduce<Record<PromiseStatus, number>>(
    (accumulator, promise) => {
      accumulator[promise.status] += 1;
      return accumulator;
    },
    { UNVERIFIED: 0, NOT_STARTED: 0, IN_PROGRESS: 0, PARTIAL: 0, FULFILLED: 0 },
  );

  return (
    <section className="promessometro">
      <aside className="promise-methodology card" role="note">
        <strong>Como ler estes estados</strong>
        <span>
          Não são previsões, pontuações automáticas nem opiniões da IA. Cada mudança exige prova
          oficial e revisão humana. “Não iniciada” nunca resulta apenas da ausência de dados; uma
          lei ou anúncio, por si só, também não prova execução material.
        </span>
      </aside>
      <div className="promise-summary-grid">
        {(Object.keys(statusMeta) as PromiseStatus[]).map((status) => (
          <article className={`summary-status summary-status--${status.toLowerCase()}`} key={status}>
            <span>{statusMeta[status].label}</span>
            <strong>{counts[status]}</strong>
            <small>{statusMeta[status].description}</small>
          </article>
        ))}
      </div>

      <div className="filter-bar card" aria-label="Filtros do promessómetro">
        <label className="promise-query">
          <span>Pesquisar no catálogo publicado</span>
          <input
            type="search"
            value={query}
            maxLength={120}
            placeholder="Ex.: habitação"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="filter-pills" role="group" aria-label="Filtrar por estado">
          {filters.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={activeFilter === filter.value ? "filter-pill is-active" : "filter-pill"}
              aria-pressed={activeFilter === filter.value}
              onClick={() => setActiveFilter(filter.value)}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <label className="area-select">
          <span>Área governativa</span>
          <select value={area} onChange={(event) => setArea(event.target.value)}>
            <option value="ALL">Todas as áreas</option>
            {areas.map((item) => <option value={item} key={item}>{item}</option>)}
          </select>
        </label>
        <p className="filter-result-count" role="status" aria-live="polite">
          {filtered.length} {filtered.length === 1 ? "compromisso visível" : "compromissos visíveis"}
        </p>
      </div>

      <div className="promise-list">
        {filtered.map((promise) => (
          <article className="promise-card card" id={`promessa-${promise.id}`} key={promise.id}>
            <div className="promise-card__top">
              <div>
                <div className="promise-card__meta">
                  <span>{promise.area}</span>
                  <span>Programa: {promise.programmePage}</span>
                </div>
                <h2>{promise.title}</h2>
              </div>
              <span className={`status-badge status-badge--${promise.status.toLowerCase()}`}>
                {promise.status === "FULFILLED" && <CheckIcon />}
                {(promise.status === "IN_PROGRESS" || promise.status === "PARTIAL") && <ClockIcon />}
                {statusMeta[promise.status].label}
              </span>
            </div>

            {promise.status === "UNVERIFIED" ? (
              <div className="promise-review-pending" role="note">
                A execução ainda não foi classificada: o compromisso aguarda prova oficial e revisão.
              </div>
            ) : promise.status === "NOT_STARTED" ? (
              <div className="promise-review-pending" role="note">
                A classificação “não iniciada” foi tomada por revisão humana dentro do período e
                das fontes indicadas; não é uma conclusão automática tirada de uma lacuna.
              </div>
            ) : (
              <div className="promise-progress-row">
                <div className="promise-progress-heading">
                  <span>Execução documentada pela revisão</span>
                  <strong>{promise.progress}%</strong>
                </div>
                <div className="progress-track progress-track--large">
                  <span style={{ width: `${promise.progress}%` }} />
                </div>
              </div>
            )}

            <p className="promise-rationale">{promise.rationale}</p>

            {promise.evidence.length ? <div className="evidence-box">
              <span className="evidence-box__label">Fundamentação oficial</span>
              {promise.evidence.map((evidence) => (
                <div className="evidence-row" key={evidence.id}>
                  <div>
                    <strong>{evidence.legalReference}</strong>
                    <span>{evidence.summary}</span>
                  </div>
                  <SourceLink source={evidence.source} compact />
                </div>
              ))}
            </div> : (
              <div className="evidence-box evidence-box--pending">
                <span className="evidence-box__label">Avaliação de execução</span>
                <p>Ainda não existe documento oficial associado que permita classificar a execução.</p>
              </div>
            )}

            <footer className="promise-card__footer">
              <SourceLink source={promise.programmeSource} compact />
              <span>Última revisão: {promise.lastReviewedAt}</span>
            </footer>
          </article>
        ))}

        {filtered.length === 0 && (
          <div className="empty-state card">
            <strong>Sem medidas neste filtro</strong>
            <span>Escolha outro estado ou área governativa.</span>
          </div>
        )}
      </div>
    </section>
  );
}
