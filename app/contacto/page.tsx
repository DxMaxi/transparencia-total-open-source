import type { Metadata } from "next";
import Link from "next/link";
import {
  CONTACT_EMAIL,
  LEGAL_ADDRESS,
  LEGAL_RESPONSIBLE,
  PROJECT_NAME,
} from "@/lib/site";

export const metadata: Metadata = {
  title: "Contacto",
  description: "Contactar a Transparência Total para correções, privacidade ou acessibilidade.",
  alternates: { canonical: "/contacto" },
};

export default function ContactPage() {
  return (
    <main className="page-shell shell legal-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Contacto institucional</span>
        <h1>Fale com o projeto</h1>
        <p>
          Escolha o canal adequado para correções, direito de resposta, privacidade ou
          acessibilidade. Não é necessário enviar dados pessoais que não sejam indispensáveis.
        </p>
      </header>
      <section className="contact-overview" aria-labelledby="contact-responsible">
        <div className="card contact-identity">
          <span className="eyebrow">Responsável pelo projeto</span>
          <h2 id="contact-responsible">{LEGAL_RESPONSIBLE}</h2>
          <p>
            {PROJECT_NAME} é um projeto cívico independente e não é um serviço oficial do Estado.
            {LEGAL_ADDRESS ? <> Endereço público: {LEGAL_ADDRESS}.</> : null}
          </p>
        </div>

        <div className="contact-route-grid">
          <article className="card contact-route-card">
            <span>01</span>
            <h2>Corrigir ou contestar um registo</h2>
            <p>
              O canal próprio preserva a versão original, a resposta, a data e os respetivos
              hashes, sem apagar o histórico.
            </p>
            <Link className="button button--primary" href="/direito-de-resposta">
              Abrir direito de resposta
            </Link>
          </article>
          <article className="card contact-route-card">
            <span>02</span>
            <h2>Privacidade ou acessibilidade</h2>
            <p>
              Consulte primeiro as políticas públicas. O contacto institucional será mostrado
              nesta página assim que estiver operacional.
            </p>
            <div className="contact-route-links">
              <Link href="/privacidade">Privacidade</Link>
              <Link href="/acessibilidade">Acessibilidade</Link>
            </div>
          </article>
        </div>

        {CONTACT_EMAIL ? (
          <div className="card contact-channel contact-channel--ready">
            <div>
              <span className="eyebrow">Email institucional ativo</span>
              <h2>Contacto geral e pedidos formais</h2>
              <p>Use este endereço apenas quando nenhum dos canais específicos for adequado.</p>
            </div>
            <a className="button button--primary" href={`mailto:${CONTACT_EMAIL}`}>
              {CONTACT_EMAIL}
            </a>
          </div>
        ) : (
          <div className="card contact-channel contact-channel--pending" role="status">
            <div>
              <span className="eyebrow">Estado do canal</span>
              <h2>Email institucional em configuração</h2>
              <p>
                Ainda não publicamos um endereço de email geral. Um endereço pessoal não é
                apresentado como substituição; o canal do domínio do projeto ficará visível aqui
                quando estiver validado e operacional.
              </p>
            </div>
            <span className="contact-status-chip">Em preparação</span>
          </div>
        )}

        <aside className="contact-minimisation-note">
          <strong>Proteja os seus dados.</strong>
          <span>
            Não envie NIF, morada, documentos de identificação ou outros dados desnecessários.
            A falta de um canal geral não impede o registo auditável de um direito de resposta.
          </span>
        </aside>
      </section>
    </main>
  );
}
