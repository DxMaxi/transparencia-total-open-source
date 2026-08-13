import type { Metadata } from "next";
import { InstitutionalContactLink } from "@/components/institutional-contact-link";
import { LEGAL_UPDATED_AT } from "@/lib/site";

export const metadata: Metadata = {
  title: "Declaração de acessibilidade",
  description: "Compromisso, estado e contacto de acessibilidade da Transparência Total.",
};

export default function AccessibilityPage() {
  return (
    <main className="page-shell shell legal-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Acesso para todas as pessoas</span>
        <h1>Declaração de acessibilidade</h1>
        <p>O objetivo é cumprir WCAG 2.2, nível AA, com melhoria contínua.</p>
      </header>
      <section className="card legal-card">
        <h2>Estado atual</h2>
        <p>
          O website procura cumprir as <a href="https://www.w3.org/TR/WCAG22/" target="_blank" rel="noreferrer noopener">WCAG 2.2, nível AA</a>. Inclui navegação por teclado,
          ligação para saltar conteúdo, estrutura semântica, foco visível, adaptação móvel e
          respeito pela preferência de movimento reduzido. Ainda não foi submetido a uma
          auditoria externa completa e é, por isso, considerado parcialmente conforme.
        </p>
        <h2>Método de avaliação</h2>
        <p>
          Foi feita autoavaliação do código, da navegação por teclado, da estrutura de títulos,
          dos nomes acessíveis de controlos, do redimensionamento e das versões móvel e desktop.
          As verificações automáticas complementam, mas não substituem, testes com tecnologias
          de apoio e pessoas com deficiência.
        </p>
        <h2>Limitações conhecidas</h2>
        <ul>
          <li>Documentos e páginas de entidades externas podem não cumprir o mesmo nível.</li>
          <li>Algumas tabelas extensas exigem deslocação horizontal em ecrãs pequenos.</li>
          <li>A conformidade com leitores de ecrã ainda não foi validada em todas as combinações de sistema e navegador.</li>
        </ul>
        <h2>Contacto e alternativa acessível</h2>
        <p>
          Se encontrar uma barreira ou precisar da informação noutro formato, consulte o{" "}
          <InstitutionalContactLink fallbackLabel="canal institucional" />. Quando o email estiver
          operacional, inclua a página e a dificuldade encontrada; procuraremos responder e
          fornecer uma alternativa acessível tão depressa quanto possível.
        </p>
        <p>
          O projeto privado adota voluntariamente os princípios de percetibilidade,
          operabilidade, compreensibilidade e robustez descritos no
          <a href="https://diariodarepublica.pt/dr/detalhe/decreto-lei/83-2018-116734769" target="_blank" rel="noreferrer noopener"> Decreto-Lei n.º 83/2018</a>, sem se apresentar como organismo público.
        </p>
        <p className="legal-updated">Declaração preparada em {LEGAL_UPDATED_AT}.</p>
      </section>
    </main>
  );
}
