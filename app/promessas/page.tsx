import { DataModeBanner } from "@/components/data-mode-banner";
import { Promessometro } from "@/components/promessometro";
import { loadPublicPromises } from "@/lib/public-data";

export const revalidate = 60;

export default async function PromisesPage() {
  const loaded = await loadPublicPromises();
  return (
    <main className="page-shell shell">
      <header className="page-heading">
        <span className="eyebrow">Fiscalização do programa</span>
        <h1>Promessómetro</h1>
        <p>
          Cada medida tem regra de classificação, fundamentação e ligação para o
          documento oficial. Estados sem prova suficiente permanecem “por verificar”.
        </p>
      </header>
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <Promessometro promises={loaded.data} />
    </main>
  );
}
