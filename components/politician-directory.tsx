"use client";

import { useMemo, useState } from "react";
import { SourceLink } from "@/components/source-link";
import type { PublicPersonSummary } from "@/types/public-data";

const roleLabels: Record<string, string> = {
  DEPUTY: "Deputado/a",
  MINISTER: "Ministro/a",
  SECRETARY_OF_STATE: "Secretário/a de Estado",
  MAYOR: "Presidente de Câmara",
  OTHER_PUBLIC_OFFICE: "Titular de cargo público",
};

function normalise(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-PT");
}

export function PoliticianDirectory({ people }: { people: PublicPersonSummary[] }) {
  const [query, setQuery] = useState("");
  const [party, setParty] = useState("ALL");
  const parties = useMemo(
    () => [...new Set(people.map((person) => person.partyShort))].sort((a, b) => a.localeCompare(b, "pt")),
    [people],
  );
  const filtered = useMemo(() => {
    const needle = normalise(query.trim());
    return people.filter((person) => {
      const matchesParty = party === "ALL" || person.partyShort === party;
      const haystack = normalise(
        `${person.name} ${person.party} ${person.partyShort} ${person.constituency}`,
      );
      return matchesParty && (!needle || haystack.includes(needle));
    });
  }, [party, people, query]);

  return (
    <section aria-label="Perfis disponíveis">
      <div className="directory-controls card">
        <label>
          <span>Pesquisar</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Nome, partido ou círculo eleitoral"
          />
        </label>
        <label>
          <span>Grupo parlamentar</span>
          <select value={party} onChange={(event) => setParty(event.target.value)}>
            <option value="ALL">Todos</option>
            {parties.map((item) => <option value={item} key={item}>{item}</option>)}
          </select>
        </label>
        <strong aria-live="polite">{filtered.length} de {people.length} perfis</strong>
      </div>

      {filtered.length ? (
        <div className="politician-directory">
          {filtered.map((person) => (
            <article className="politician-directory__card card" key={person.id}>
              <div className="profile-avatar" aria-hidden="true">{person.partyShort.slice(0, 3)}</div>
              <div>
                <span className="eyebrow">
                  {roleLabels[person.role] ?? person.role.replaceAll("_", " ")}
                </span>
                <h2><a href={`/politicos/${person.slug}`}>{person.name}</a></h2>
                <p>{person.party} · {person.constituency} · {person.legislature}</p>
                <SourceLink source={person.profileSource} compact />
              </div>
              <a className="text-link" href={`/politicos/${person.slug}`}>Abrir ficha</a>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state card">
          <strong>Nenhum perfil corresponde à pesquisa</strong>
          <span>Altere o nome ou o grupo parlamentar selecionado.</span>
        </div>
      )}
    </section>
  );
}
