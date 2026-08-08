import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

const routes = [
  "",
  "/politicos",
  "/atividade-parlamentar",
  "/promessas",
  "/guia-cidadao",
  "/metodologia",
  "/direito-de-resposta",
  "/privacidade",
  "/cookies",
  "/termos",
  "/acessibilidade",
  "/contacto",
];

export default function sitemap(): MetadataRoute.Sitemap {
  return routes.map((route) => ({
    url: `${SITE_URL}${route}`,
    lastModified: new Date("2026-08-08T00:00:00Z"),
    changeFrequency: route === "" ? "daily" : "weekly",
    priority: route === "" ? 1 : 0.7,
  }));
}
