import type { Metadata } from "next";
import { DataModeBanner } from "@/components/data-mode-banner";
import { PoliticianDirectory } from "@/components/politician-directory";
import { loadPublicPoliticians } from "@/lib/public-data";

export const metadata: Metadata = {
  title: "Políticos",
  description: "Perfis de titulares de cargos políticos com fonte oficial e revisão visível.",
  alternates: { canonical: "/politicos" },
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
          Só aparecem identidades observadas numa fonte oficial arquivada e aprovadas por revisão
          humana. Cada ficha separa mandatos, presenças, iniciativas, votos e declarações, e mostra
          claramente quando uma dessas áreas ainda não tem cobertura publicável.
        </p>
      </header>
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <PoliticianDirectory people={loaded.data} />
    </main>
  );
}
