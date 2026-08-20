import type { MetadataRoute } from "next";
import { loadPublicAiExplanations, loadPublicPoliticians } from "@/lib/public-data";
import { SITE_URL } from "@/lib/site";

const publicRoutes = [
  "",
  "/politicos",
  "/atividade-parlamentar",
  "/promessas",
  "/explicacoes",
  "/guia-cidadao",
  "/metodologia",
  "/direito-de-resposta",
  "/privacidade",
  "/cookies",
  "/termos",
  "/acessibilidade",
  "/contacto",
];

export const revalidate = 60;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticEntries: MetadataRoute.Sitemap = publicRoutes.map((route) => ({
    url: `${SITE_URL}${route}`,
    lastModified: new Date("2026-08-13T00:00:00Z"),
    changeFrequency: route === "" ? "daily" : "weekly",
    priority: route === "" ? 1 : 0.7,
  }));

  const [politicians, explanations] = await Promise.all([
    loadPublicPoliticians(),
    loadPublicAiExplanations({ pageSize: 100 }),
  ]);
  const profilePaths = [...new Set(
    politicians.data
      .map((person) => person.slug.trim())
      .filter(Boolean)
      .map((slug) => `/politicos/${slug}`),
  )].sort();
  const profileEntries: MetadataRoute.Sitemap = profilePaths.map((path) => ({
    url: `${SITE_URL}${path}`,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  const explanationEntries: MetadataRoute.Sitemap = explanations.data.items.map((item) => ({
    url: `${SITE_URL}/explicacoes/${item.id}`,
    lastModified: new Date(item.editorial.publishedAt),
    changeFrequency: "weekly",
    priority: 0.65,
  }));

  return [...staticEntries, ...profileEntries, ...explanationEntries];
}
