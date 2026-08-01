import type { Metadata } from "next";
import { DataModeBanner } from "@/components/data-mode-banner";
import { InvestigatorWorkbench } from "@/components/investigator-workbench";
import { loadPublicInvestigator } from "@/lib/public-data";

export const revalidate = 60;

export const metadata: Metadata = {
  title: "Investigador Cívico",
  description: "Explore contratos, ligações documentadas e comparações entre discurso e voto.",
};

export default async function InvestigatorPage() {
  const loaded = await loadPublicInvestigator();
  return (
    <main className="page-shell shell investigator-page">
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <div className="page-heading page-heading--wide investigator-heading">
        <div>
          <span className="eyebrow">Modo Investigador Cívico</span>
          <h1>Siga a prova.<br /><span>Não a insinuação.</span></h1>
        </div>
        <p>
          Cruze períodos, montantes e entidades. Uma correspondência automática é apenas um candidato de revisão; só relações confirmadas por fonte oficial podem ser publicadas.
        </p>
      </div>
      <InvestigatorWorkbench dataset={loaded.data} />
    </main>
  );
}
