import type { Metadata } from "next";
import { BrowserStorageCleanup } from "@/components/browser-storage-cleanup";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { SITE_URL } from "@/lib/site";
import "@xyflow/react/dist/style.css";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Transparência Total / Fator Cívico — factos com prova",
    template: "%s · Transparência Total",
  },
  description:
    "Plataforma cívica, neutra e aberta para acompanhar promessas, votações e atividade política em Portugal.",
  applicationName: "Transparência Total / Fator Cívico",
  formatDetection: { telephone: false },
  openGraph: {
    type: "website",
    locale: "pt_PT",
    siteName: "Transparência Total / Fator Cívico",
    title: "Transparência Total — factos com prova",
    description: "Representantes, iniciativas, votações e compromissos políticos com fonte oficial.",
    url: "/",
  },
  robots: { index: true, follow: true },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
    apple: "/icons/icon-192.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-PT">
      <body>
        <BrowserStorageCleanup />
        <a className="skip-link" href="#conteudo">Saltar para o conteúdo</a>
        <SiteHeader />
        <div id="conteudo">{children}</div>
        <SiteFooter />
      </body>
    </html>
  );
}
