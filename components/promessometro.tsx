"use client";

import { useMemo, useState } from "react";
import { CheckIcon, ClockIcon } from "@/components/icons";
import { SourceLink } from "@/components/source-link";
import type { GovernmentPromise, PromiseStatus } from "@/types/domain";

const statusMeta: Record<PromiseStatus, { label: string; description: string }> = {
  UNVERIFIED: {
    label: "Por verificar",
    description: "Compromisso oficial catalogado; execução ainda sem avaliação",
  },
  FULFILLED: { label: "Cumprido", description: "Prova oficial confirma execução integral" },
  IN_PROGRESS: { label: "Em execução", description: "Há atos oficiais, mas a medida não terminou" },
  BROKEN: { label: "Incumprido", description: "Prazo ou objetivo verificável não foi alcançado" },
  ABANDONED: { label: "Abandonado", description: "O Governo declarou cessação ou substituição" },
};

const filters: Array<{ value: "ALL" | PromiseStatus; label: string }> = [
  { value: "ALL", label: "Todas" },
  { value: "UNVERIFIED", label: "Por verificar" },
  { value: "FULFILLED", label: "Cumpridas" },
  { value: "IN_PROGRESS", label: "Em execução" },
  { value: "BROKEN", label: "Incumpridas" },
  { value: "ABANDONED", label: "Abandonadas" },
];

export function Promessometro({ promises }: { promises: GovernmentPromise[] }) {
  const [activeFilter, setActiveFilter] = useState<"ALL" | PromiseStatus>("ALL");
  const [area, setArea] = useState("ALL");

  const areas = useMemo(
    () => [...new Set(promises.map((promise) => promise.area))].sort(),
    [promises],
  );

  const filtered = promises.filter((promise) => {
    const statusMatches = activeFilter === "ALL" || promise.status === activeFilter;
    const areaMatches = area === "ALL" || promise.area === area;
    return statusMatches && areaMatches;
  });

  const counts = promises.reduce<Record<PromiseStatus, number>>(
    (accumulator, promise) => {
      accumulator[promise.status] += 1;
      return accumulator;
    },
    { UNVERIFIED: 0, FULFILLED: 0, IN_PROGRESS: 0, BROKEN: 0, ABANDONED: 0 },
  );

  return (
    <section className="promessometro">
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
        <div className="filter-pills" role="group" aria-label="Filtrar por estado">
          {filters.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={activeFilter === filter.value ? "filter-pill is-active" : "filter-pill"}
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
      </div>

      <div className="promise-list" aria-live="polite">
        {filtered.map((promise) => (
          <article className="promise-card card" key={promise.id}>
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
                {promise.status === "IN_PROGRESS" && <ClockIcon />}
                {statusMeta[promise.status].label}
              </span>
            </div>

            {promise.status === "UNVERIFIED" ? (
              <div className="promise-review-pending" role="note">
                A execução ainda não foi classificada: o compromisso aguarda prova oficial e revisão.
              </div>
            ) : (
              <div className="promise-progress-row">
                <div className="promise-progress-heading">
                  <span>Execução documentada</span>
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
