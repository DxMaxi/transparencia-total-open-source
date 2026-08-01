import { notFound } from "next/navigation";
import { DataModeBanner } from "@/components/data-mode-banner";
import { PoliticianProfile } from "@/components/politician-profile";
import { loadPublicPolitician } from "@/lib/public-data";

export const revalidate = 60;

export default async function PoliticianPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const loaded = await loadPublicPolitician(slug);
  if (!loaded.data) notFound();

  return (
    <main className="page-shell shell">
      <DataModeBanner status={loaded.status} showingFallback={loaded.showingFallback} />
      <PoliticianProfile profile={loaded.data} />
    </main>
  );
}
