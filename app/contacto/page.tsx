import type { Metadata } from "next";
import {
  CONTACT_EMAIL,
  LEGAL_ADDRESS,
  LEGAL_RESPONSIBLE,
  PROJECT_NAME,
} from "@/lib/site";

export const metadata: Metadata = {
  title: "Contacto",
  description: "Contactar a Transparência Total para correções, privacidade ou acessibilidade.",
};

export default function ContactPage() {
  return (
    <main className="page-shell shell legal-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Contacto direto</span>
        <h1>Fale com o projeto</h1>
        <p>{PROJECT_NAME} recebe correções, questões de privacidade e sugestões de acessibilidade.</p>
      </header>
      <section className="card legal-card contact-card">
        <h2>Responsável</h2>
        <p><strong>{LEGAL_RESPONSIBLE}</strong>{LEGAL_ADDRESS ? <> · {LEGAL_ADDRESS}</> : null}</p>
        <h2>Email</h2>
        <p><a className="button button--primary" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a></p>
        <p>
          Para contestar um registo específico, prefira o <a href="/direito-de-resposta">canal de direito de resposta</a> e não envie NIF, morada ou outros dados desnecessários.
        </p>
      </section>
    </main>
  );
}
