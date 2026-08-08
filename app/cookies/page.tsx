import type { Metadata } from "next";
import { CONTACT_EMAIL, LEGAL_UPDATED_AT } from "@/lib/site";

export const metadata: Metadata = {
  title: "Política de cookies",
  description: "Cookies e armazenamento local utilizados pela Transparência Total.",
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
          Na configuração pública atual, a Transparência Total não coloca cookies de
          publicidade, personalização, sessão ou medição de audiência e não regista um
          service worker no navegador. Por isso não apresentamos um aviso de consentimento
          que não teria escolhas reais para gerir.
        </p>
        <p>
          O código remove apenas o service worker e os caches com o prefixo do projeto que
          possam ter sido criados por versões anteriores. Esta limpeza técnica não identifica
          o visitante, não envia o conteúdo desses caches ao projeto e não cria armazenamento novo.
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
          não essencial no equipamento. Se essa configuração mudar, a nova tecnologia ficará
          desativada até existir informação clara e, quando exigido, consentimento prévio.
        </p>
        <h2>Alterações futuras</h2>
        <p>
          Esta página será atualizada antes de ativar analítica, publicidade, notificações
          ou outra tecnologia de armazenamento. Para questões, contacte <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
        <p className="legal-updated">Atualizada em {LEGAL_UPDATED_AT}.</p>
      </section>
    </main>
  );
}
