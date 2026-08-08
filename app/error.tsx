"use client";

import { useEffect } from "react";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("page_render_failed", error.digest ?? error.name);
  }, [error]);

  return (
    <main className="page-shell shell system-page">
      <section className="card system-card" role="alert">
        <span className="eyebrow">Indisponibilidade temporária</span>
        <h1>Não foi possível apresentar esta página</h1>
        <p>Os dados não foram substituídos por exemplos. Pode tentar novamente ou voltar ao início.</p>
        <div className="hero-actions">
          <button className="button button--primary" type="button" onClick={reset}>Tentar novamente</button>
          <a className="button button--ghost" href="/">Voltar ao início</a>
        </div>
      </section>
    </main>
  );
}
