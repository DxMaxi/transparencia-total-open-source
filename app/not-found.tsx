import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Página não encontrada",
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <main className="page-shell shell system-page">
      <section className="card system-card">
        <span className="eyebrow">Erro 404</span>
        <h1>Página não encontrada</h1>
        <p>
          A ligação pode estar desatualizada ou o conteúdo pode ter sido retirado por não
          cumprir os critérios de publicação.
        </p>
        <div className="hero-actions">
          <a className="button button--primary" href="/">Voltar ao início</a>
          <a className="button button--ghost" href="/contacto">Reportar uma ligação</a>
        </div>
      </section>
    </main>
  );
}
