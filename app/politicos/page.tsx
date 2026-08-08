import type { Metadata } from "next";
import { DataModeBanner } from "@/components/data-mode-banner";
import { PoliticianDirectory } from "@/components/politician-directory";
import { loadPublicPoliticians } from "@/lib/public-data";

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
      <PoliticianDirectory people={loaded.data} />
    </main>
  );
}
