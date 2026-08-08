import type { Metadata } from "next";
import { DataModeBanner } from "@/components/data-mode-banner";
import { Promessometro } from "@/components/promessometro";
import { initialGovernmentCommitments } from "@/lib/government-programme";
import { loadPublicPromises } from "@/lib/public-data";

export const metadata: Metadata = {
  title: "Promessómetro",
  description:
    "Compromissos do Programa do XXV Governo, com página oficial, estado de verificação e prova de execução quando exista.",
};

export const revalidate = 60;

export default async function PromisesPage() {
  const loaded = await loadPublicPromises();
  return (
    <main className="page-shell shell">
      <header className="page-heading">
        <span className="eyebrow">Fiscalização do programa</span>
        <h1>Promessómetro</h1>
        <p>
          Cobertura editorial inicial do Programa do XXV Governo Constitucional.
          Cada compromisso aponta para o documento oficial; sem prova suficiente de
          execução, o estado permanece “por verificar”.
        </p>
      </header>
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <aside className="catalogue-scope card" role="note">
        <strong>Cobertura inicial: {initialGovernmentCommitments.length} compromissos explícitos</strong>
        <span>
          É uma seleção editorial identificada, não a contagem integral de todas as medidas do
          programa. O catálogo será alargado por versões sem alterar avaliações anteriores.
        </span>
      </aside>
      <Promessometro promises={loaded.data} />
    </main>
  );
}
