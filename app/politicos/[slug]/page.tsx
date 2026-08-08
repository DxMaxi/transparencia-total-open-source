import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";
import { DataModeBanner } from "@/components/data-mode-banner";
import { PoliticianProfile } from "@/components/politician-profile";
import { loadPublicPolitician } from "@/lib/public-data";

export const revalidate = 60;

const loadPolitician = cache(loadPublicPolitician);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const loaded = await loadPolitician(slug);
  if (!loaded.data) return { title: "Perfil político" };
  return {
    title: loaded.data.name,
    description: `${loaded.data.name}: cargo, grupo parlamentar, círculo e registos oficiais disponíveis.`,
  };
}

export default async function PoliticianPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const loaded = await loadPolitician(slug);
  if (!loaded.data && loaded.status.mode !== "UNAVAILABLE") notFound();

  if (!loaded.data) {
    return (
      <main className="page-shell shell system-page">
        <section className="card system-card">
          <DataModeBanner status={loaded.status} showingFallback={false} />
          <h1>Perfil temporariamente indisponível</h1>
          <p>
            Não apresentamos uma ficha vazia nem transformamos uma falha da API num perfil
            inexistente. Tente novamente ou volte ao diretório.
          </p>
          <a className="button button--primary" href="/politicos">Voltar aos políticos</a>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell shell">
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <PoliticianProfile profile={loaded.data} />
    </main>
  );
}
