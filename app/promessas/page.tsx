import type { Metadata } from "next";
import { DataModeBanner } from "@/components/data-mode-banner";
import { Promessometro } from "@/components/promessometro";
import { loadPublicPromises } from "@/lib/public-data";

export const metadata: Metadata = {
  title: "Promessómetro",
  description:
    "Compromissos do Programa do XXV Governo, com página oficial, estado de verificação e prova de execução quando exista.",
  alternates: { canonical: "/promessas" },
};

export const revalidate = 60;

type SearchParams = Record<string, string | string[] | undefined>;

export default async function PromisesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const parameters = await searchParams;
  const query = ((Array.isArray(parameters.q) ? parameters.q[0] : parameters.q) ?? "")
    .trim()
    .slice(0, 120);
  const loaded = await loadPublicPromises();
  return (
    <main className="page-shell shell">
      <header className="page-heading">
        <span className="eyebrow">Fiscalização do programa</span>
        <h1>Promessómetro</h1>
        <p>
          Compromissos identificáveis do Programa do XXV Governo Constitucional, explicados com
          critérios públicos. Cada estado aponta para a prova oficial e para a revisão que o
          fundamenta; sem prova suficiente, permanece “por verificar”.
        </p>
      </header>
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <aside className="catalogue-scope card" role="note">
        <strong>
          {loaded.showingFallback ? "Cobertura editorial inicial" : "Catálogo publicado"}: {loaded.data.length} compromissos explícitos
        </strong>
        <span>
          {loaded.showingFallback
            ? "É uma seleção editorial identificada, não a contagem integral de todas as medidas do programa."
            : "A contagem corresponde aos compromissos que cumprem a porta pública; não inclui recolhas por rever."}
        </span>
      </aside>
      <Promessometro promises={loaded.data} initialQuery={query} />
    </main>
  );
}
