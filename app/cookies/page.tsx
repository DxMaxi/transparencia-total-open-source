import type { Metadata } from "next";
import { InstitutionalContactLink } from "@/components/institutional-contact-link";
import { LEGAL_UPDATED_AT } from "@/lib/site";

export const metadata: Metadata = {
  title: "Política de cookies",
  description: "Cookies e armazenamento local utilizados pela Transparência Total.",
  alternates: { canonical: "/cookies" },
};

export default function CookiesPage() {
  return (
    <main className="page-shell shell legal-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Escolhas digitais</span>
        <h1>Política de cookies</h1>
        <p>O site não usa publicidade, analítica comportamental ou cookies não essenciais.</p>
      </header>
      <section className="card legal-card">
        <h2>Configuração pública atual</h2>
        <p>
          A Transparência Total não coloca cookies de publicidade, personalização, sessão
          ou medição de audiência. O modo offline permanece desativado até a pessoa escolher
          explicitamente “Ativar modo offline” no rodapé; visitar o site, por si só, não
          regista o service worker nem cria os respetivos caches.
        </p>
        <p>
          Quando ativado, o navegador guarda apenas páginas públicas e recursos essenciais
          em caches com o prefixo do projeto. Rotas de administração, autenticação e API,
          respostas privadas ou sem autorização de cache e pedidos com credenciais são excluídos.
          O botão “Desativar e apagar cache” remove o registo e apenas esses caches, sem ler ou
          eliminar armazenamento de outros websites.
        </p>
        <h2>Cache normal do navegador</h2>
        <p>
          Como em qualquer website, o navegador pode conservar temporariamente ficheiros
          segundo os cabeçalhos HTTP e as suas próprias definições. O projeto não usa esse
          mecanismo para identificar visitantes nem para acompanhar navegação.
        </p>
        <h2>Base legal</h2>
        <p>
          O artigo 5.º da Lei n.º 41/2004 exige consentimento para armazenamento ou acesso
          não essencial no equipamento. A escolha do botão é a ação explícita que ativa o modo
          offline; pode ser revogada no mesmo controlo. O projeto não usa essa escolha para
          identificar a pessoa nem recebe uma lista das páginas existentes no cache.
        </p>
        <h2>Alterações futuras</h2>
        <p>
          Esta página será atualizada antes de ativar analítica, publicidade, notificações
          ou outra tecnologia de armazenamento. O modo offline não pede autorização para
          notificações; essa capacidade continua separada e desativada na interface pública.
          Para questões, consulte o{" "}
          <InstitutionalContactLink fallbackLabel="canal institucional" />.
        </p>
        <p className="legal-updated">Atualizada em {LEGAL_UPDATED_AT}.</p>
      </section>
    </main>
  );
}
