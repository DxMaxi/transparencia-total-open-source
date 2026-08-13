import type { Metadata } from "next";
import { InstitutionalContactLink } from "@/components/institutional-contact-link";
import {
  LEGAL_ADDRESS,
  LEGAL_REGISTRATION,
  LEGAL_RESPONSIBLE,
  LEGAL_TAX_ID,
  LEGAL_UPDATED_AT,
  PROJECT_NAME,
} from "@/lib/site";

export const metadata: Metadata = {
  title: "Aviso legal e termos de utilização",
  description: "Identificação, limites editoriais e condições de utilização do projeto.",
};

export default function TermsPage() {
  return (
    <main className="page-shell shell legal-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Aviso legal</span>
        <h1>Termos de utilização</h1>
        <p>Quem publica, o que os dados significam e quais são os limites do serviço.</p>
      </header>
      <section className="card legal-card">
        <h2>Identificação</h2>
        <p>
          {PROJECT_NAME} é um projeto cívico independente, gerido por <strong>{LEGAL_RESPONSIBLE}</strong>.{" "}
          Contacto institucional: <InstitutionalContactLink />.
        </p>
        {LEGAL_ADDRESS || LEGAL_TAX_ID || LEGAL_REGISTRATION ? (
          <dl className="legal-identity-list">
            {LEGAL_ADDRESS ? <><dt>Endereço geográfico</dt><dd>{LEGAL_ADDRESS}</dd></> : null}
            {LEGAL_TAX_ID ? <><dt>Identificação fiscal</dt><dd>{LEGAL_TAX_ID}</dd></> : null}
            {LEGAL_REGISTRATION ? <><dt>Registo aplicável</dt><dd>{LEGAL_REGISTRATION}</dd></> : null}
          </dl>
        ) : null}
        <h2>Natureza não comercial</h2>
        <p>
          O projeto não vende bens ou serviços, não aceita pagamentos, não apresenta
          publicidade e não mantém programas de afiliados. O acesso é gratuito. Esta
          informação será atualizada antes de qualquer alteração desse modelo.
        </p>
        <h2>Independência</h2>
        <p>
          Este não é um website oficial da Assembleia da República, do Governo, de um
          partido ou de qualquer entidade pública. As ligações identificam sempre a fonte
          competente para consulta do original.
        </p>
        <h2>Rigor e limites</h2>
        <ul>
          <li>Ausência de dados não significa ausência, incumprimento ou suspeita.</li>
          <li>Posições de grupos parlamentares não são atribuídas a deputados individuais.</li>
          <li>Uma ligação entre entidades não constitui acusação nem prova de ilegalidade.</li>
          <li>O conteúdo é informativo e não substitui aconselhamento jurídico, fiscal ou financeiro.</li>
        </ul>
        <h2>Correções e direito de resposta</h2>
        <p>
          Pode pedir correção ou apresentar contraditório através do <a href="/direito-de-resposta">canal de direito de resposta</a> ou por email.
          A origem, a decisão editorial e as versões relevantes são preservadas para auditoria.
        </p>
        <h2>Licenças e reutilização</h2>
        <p>
          A partir da V5, o software original do projeto usa a{" "}
          <a href="https://polyformproject.org/licenses/noncommercial/1.0.0">
            PolyForm Noncommercial License 1.0.0
          </a>
          . É código-fonte auditável para utilização não comercial, não uma licença
          open-source segundo a definição da Open Source Initiative.
        </p>
        <ul>
          <li>
            A documentação e os conteúdos editoriais originais identificados pelo projeto
            usam CC BY-NC 4.0, salvo indicação diferente.
          </li>
          <li>O código disponibilizado até à versão v0.4.0 conserva a licença MIT histórica.</li>
          <li>
            Os factos, documentos e dados oficiais mantêm as condições e direitos definidos
            pelas entidades de origem; as licenças do projeto não os substituem.
          </li>
          <li>
            As licenças não autorizam a utilização do nome ou identidade do projeto de forma
            que sugira aprovação, parceria ou caráter oficial.
          </li>
        </ul>
        <h2>Disponibilidade</h2>
        <p>
          Procuramos manter o serviço correto e acessível, mas fontes externas, alojamento e
          recolhas podem sofrer interrupções. Uma secção indisponível é assinalada em vez de
          ser preenchida com dados fictícios.
        </p>
        <h2>Legislação e contacto</h2>
        <p>
          O serviço é gerido a partir de Portugal. A disponibilização permanente de
          identificação e contacto segue o enquadramento português aplicável aos serviços em
          rede. O estado do canal para questões legais ou pedidos formais está disponível no{" "}
          <InstitutionalContactLink fallbackLabel="contacto institucional" />.
        </p>
        <p className="legal-updated">Atualizados em {LEGAL_UPDATED_AT}.</p>
      </section>
    </main>
  );
}
