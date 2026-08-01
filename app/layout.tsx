import type { Metadata } from "next";
import { PwaRegister } from "@/components/pwa-register";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import "@xyflow/react/dist/style.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Transparência Total / Fator Cívico — factos com prova",
    template: "%s · Transparência Total",
  },
  description:
    "Plataforma cívica, neutra e aberta para acompanhar promessas, votações e atividade política em Portugal.",
  applicationName: "Transparência Total / Fator Cívico",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Transparência Total",
  },
  formatDetection: { telephone: false },
  other: {
    "codex-preview": "development",
  },
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
        <a className="skip-link" href="#conteudo">Saltar para o conteúdo</a>
        <SiteHeader />
        <div id="conteudo">{children}</div>
        <SiteFooter />
        <PwaRegister />
      </body>
    </html>
  );
}
