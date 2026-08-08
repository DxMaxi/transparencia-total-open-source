"use client";

import { FormEvent, useState } from "react";
import { SearchIcon, ShieldCheckIcon } from "@/components/icons";
import { InterestGraph } from "@/components/interest-graph";
import { SpeechVoteComparison } from "@/components/speech-vote-comparison";
import type { PublicInvestigatorDataset } from "@/types/public-data";

type Filters = {
  year: string;
  party: string;
  minimum: string;
  maximum: string;
  company: string;
};

const defaults: Filters = { year: "Todos", party: "Todos", minimum: "", maximum: "", company: "" };

export function InvestigatorWorkbench({ dataset }: { dataset: PublicInvestigatorDataset }) {
  const [filters, setFilters] = useState(defaults);
  const [applied, setApplied] = useState(defaults);
  const years = [...new Set(
    dataset.edges.map((edge) => edge.data.year).filter((year): year is number => year != null),
  )].sort((a, b) => b - a);
  const parties = [...new Set(
    dataset.edges.map((edge) => edge.data.party).filter((party): party is string => Boolean(party)),
  )].sort((a, b) => a.localeCompare(b, "pt-PT"));
  const filteredEdges = dataset.edges.filter((edge) => {
    const amount = edge.data.amount;
    return (applied.year === "Todos" || String(edge.data.year) === applied.year) &&
      (applied.party === "Todos" || edge.data.party === applied.party) &&
      (!applied.minimum || (amount != null && amount >= Number(applied.minimum))) &&
      (!applied.maximum || (amount != null && amount <= Number(applied.maximum))) &&
      (!applied.company || (edge.data.company ?? "").toLocaleLowerCase("pt-PT")
        .includes(applied.company.toLocaleLowerCase("pt-PT")));
  });
  const connectedNodes = new Set(filteredEdges.flatMap((edge) => [edge.source, edge.target]));
  const filteredGraph = {
    edges: filteredEdges,
    nodes: dataset.nodes.filter((node) => connectedNodes.has(node.id)),
  };
  const matches = filteredEdges.length > 0 || dataset.comparisons.length > 0;
  const relationLabel = filteredEdges.length === 1 ? "relação" : "relações";
  const comparisonLabel = dataset.comparisons.length === 1 ? "comparação revista" : "comparações revistas";
  const relationVerb = filteredEdges.length === 1 ? "corresponde" : "correspondem";
  const comparisonAvailability = dataset.comparisons.length === 1 ? "disponível" : "disponíveis";

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApplied(filters);
  }

  return (
    <>
      <form className="investigator-filters card" onSubmit={apply} aria-label="Filtros do Investigador Cívico">
        <div className="investigator-filter-title">
          <SearchIcon />
          <div><strong>Investigar por critérios</strong><span>Todos os resultados conservam prova e estado de revisão.</span></div>
        </div>
        <label>
          Ano
          <select aria-label="Ano" value={filters.year} onChange={(event) => setFilters({ ...filters, year: event.target.value })}>
            <option>Todos</option>
            {years.map((year) => <option key={year}>{year}</option>)}
          </select>
        </label>
        <label>
          Partido
          <select aria-label="Partido" value={filters.party} onChange={(event) => setFilters({ ...filters, party: event.target.value })}>
            <option>Todos</option>
            {parties.map((party) => <option key={party}>{party}</option>)}
          </select>
        </label>
        <label>
          Montante mínimo (€)
          <input aria-label="Montante mínimo" type="number" min="0" value={filters.minimum} onChange={(event) => setFilters({ ...filters, minimum: event.target.value })} />
        </label>
        <label>
          Montante máximo (€)
          <input aria-label="Montante máximo" type="number" min="0" value={filters.maximum} onChange={(event) => setFilters({ ...filters, maximum: event.target.value })} />
        </label>
        <label>
          Empresa
          <input aria-label="Empresa" type="search" value={filters.company} onChange={(event) => setFilters({ ...filters, company: event.target.value })} placeholder="Designação pública" />
        </label>
        <button className="button button--primary" type="submit">Aplicar</button>
      </form>

      <div className="filter-audit-line" role="status">
        <ShieldCheckIcon />
        <span>{filteredEdges.length} {relationLabel} {relationVerb} aos filtros; {dataset.comparisons.length} {comparisonLabel} {comparisonAvailability}.</span>
        <button type="button" onClick={() => { setFilters(defaults); setApplied(defaults); }}>Limpar filtros</button>
      </div>

      {matches ? (
        <div className="investigator-stack">
          {filteredEdges.length > 0 && <InterestGraph dataset={filteredGraph} />}
          {dataset.comparisons[0] && <SpeechVoteComparison data={dataset.comparisons[0]} />}
        </div>
      ) : (
        <div className="investigator-empty card">
          <SearchIcon />
          <h2>Sem correspondências nesta amostra</h2>
          <p>A ausência de resultados não significa ausência de relações; significa apenas que o conjunto atualmente publicável não contém dados para estes critérios.</p>
        </div>
      )}
    </>
  );
}
