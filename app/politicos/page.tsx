import type { Metadata } from "next";
import { DataModeBanner } from "@/components/data-mode-banner";
import { SourceLink } from "@/components/source-link";
import { loadPublicPoliticians } from "@/lib/public-data";

const roleLabels: Record<string, string> = {
  DEPUTY: "Deputado/a",
  MINISTER: "Ministro/a",
  SECRETARY_OF_STATE: "Secretário/a de Estado",
  MAYOR: "Presidente de Câmara",
  OTHER_PUBLIC_OFFICE: "Titular de cargo público",
};

export const metadata: Metadata = {
  title: "Políticos",
  description: "Perfis de titulares de cargos políticos com fonte oficial e revisão visível.",
};

export const revalidate = 60;

export default async function PoliticiansPage() {
  const loaded = await loadPublicPoliticians();
  return (
    <main className="page-shell shell">
      <header className="page-heading">
        <span className="eyebrow">Diretório auditável</span>
        <h1>Políticos</h1>
        <p>
          Só aparecem perfis cuja publicação foi aprovada. A pertença parlamentar indica a data
          de observação da fonte, nunca uma data de início inferida.
        </p>
      </header>
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <section className="politician-directory" aria-label="Perfis disponíveis">
        {loaded.data.map((person) => (
          <article className="politician-directory__card card" key={person.id}>
            <div className="profile-avatar" aria-hidden="true">{person.partyShort.slice(0, 3)}</div>
            <div>
              <span className="eyebrow">{roleLabels[person.role] ?? person.role.replaceAll("_", " ")}</span>
              <h2><a href={`/politicos/${person.slug}`}>{person.name}</a></h2>
              <p>{person.party} · {person.constituency} · {person.legislature}</p>
              <SourceLink source={person.profileSource} compact />
            </div>
            <a className="text-link" href={`/politicos/${person.slug}`}>Abrir ficha</a>
          </article>
        ))}
      </section>
    </main>
  );
}
