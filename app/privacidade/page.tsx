import type { Metadata } from "next";
import {
  CONTACT_EMAIL,
  LEGAL_ADDRESS,
  LEGAL_RESPONSIBLE,
  LEGAL_TAX_ID,
  LEGAL_UPDATED_AT,
  PROJECT_NAME,
} from "@/lib/site";

export const metadata: Metadata = {
  title: "Política de privacidade",
  description: "Como a Transparência Total trata dados pessoais e protege os seus direitos.",
};

export default function PrivacyPage() {
  return (
    <main className="page-shell shell legal-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Privacidade e RGPD</span>
        <h1>Política de privacidade</h1>
        <p>Informação sobre o responsável, os dados, as fontes, os fundamentos e os direitos.</p>
      </header>

      <section className="card legal-card">
        <h2>1. Responsável pelo tratamento</h2>
        <p>
          O responsável pelo tratamento é <strong>{LEGAL_RESPONSIBLE}</strong>, no âmbito do
          projeto cívico independente {PROJECT_NAME}. O ponto de contacto único para
          privacidade é <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
          {LEGAL_ADDRESS ? <> Endereço de contacto: {LEGAL_ADDRESS}.</> : null}
          {LEGAL_TAX_ID ? <> Identificação fiscal: {LEGAL_TAX_ID}.</> : null} Não foi designado
          encarregado de proteção de dados; os pedidos são tratados diretamente pelo responsável.
        </p>

        <h2>2. Tratamentos, finalidades e conservação</h2>
        <div className="legal-table-wrap">
          <table className="legal-table">
            <thead>
              <tr><th>Contexto</th><th>Dados</th><th>Finalidade e fundamento</th><th>Conservação</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Informação política oficial</td>
                <td>Nome, cargo, círculo, filiação parlamentar, iniciativas e posições que constem de fontes públicas oficiais.</td>
                <td>
                  Informação cívica, escrutínio democrático e preservação da proveniência,
                  com base no interesse legítimo e na liberdade de expressão e informação.
                  Categorias especiais só são tratadas quando manifestamente tornadas públicas
                  pela pessoa ou quando exista outro fundamento legal específico; caso contrário,
                  não são publicadas.
                </td>
                <td>Enquanto forem necessárias ao arquivo factual e ao interesse público, com revisão quando a fonte muda, existe oposição fundamentada ou o contexto deixa de justificar a publicação.</td>
              </tr>
              <tr>
                <td>Navegação e segurança</td>
                <td>IP, data, rota, agente do navegador e eventos técnicos nos registos dos prestadores.</td>
                <td>Disponibilidade, prevenção de abuso e diagnóstico, com base no interesse legítimo de proteger o serviço.</td>
                <td>Pelo prazo operacional mais curto disponibilizado pelos prestadores, salvo preservação temporária necessária para investigar um incidente.</td>
              </tr>
              <tr>
                <td>Direito de resposta</td>
                <td>Nome público, qualidade, declaração, referência contestada, hash do registo e ligação oficial opcional.</td>
                <td>Receber, verificar e relacionar o contraditório com o registo, a pedido do respondente e no interesse legítimo de assegurar rigor editorial.</td>
                <td>Enquanto o registo relacionado estiver publicado e, depois disso, durante o período necessário à auditoria e defesa de direitos.</td>
              </tr>
              <tr>
                <td>Contacto por email</td>
                <td>Endereço, conteúdo da mensagem e metadados de entrega.</td>
                <td>Responder ao pedido e conservar prova do seguimento, conforme o pedido e o interesse legítimo do projeto.</td>
                <td>Até 12 meses após o encerramento do pedido, salvo obrigação legal ou litígio que justifique prazo superior.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h2>3. Origem dos dados sobre pessoas públicas</h2>
        <p>
          Esses dados não são obtidos diretamente junto dos titulares. Provêm das fontes
          identificadas em cada registo, sobretudo Assembleia da República, Diário da
          República e Entidade para a Transparência. Não publicamos moradas, contactos
          privados, NIF em claro, dados familiares ou inferências de filiação e voto. Esta
          secção presta a informação aplicável a dados obtidos de fontes acessíveis ao público.
        </p>

        <h2>4. Interesse legítimo e salvaguardas editoriais</h2>
        <p>
          A finalidade é permitir que o público confirme factos relevantes para o exercício de
          funções públicas. Antes de publicar, limitamos os campos ao necessário, conservamos
          a fonte e a data, distinguimos posições coletivas de atos individuais, exigimos revisão
          humana e disponibilizamos correção, oposição e contraditório. Não são criados perfis
          para publicidade ou recomendação política.
        </p>

        <h2>5. Destinatários, prestadores e transferências</h2>
        <p>
          O website usa Vercel, a API usa Render, a base de dados usa Supabase, o código e as
          operações usam GitHub e o contacto usa Google. Estes prestadores recebem apenas os
          dados técnicos necessários às respetivas funções, sujeitos às suas condições e
          mecanismos de proteção. Alguns podem tratar dados fora do Espaço Económico Europeu;
          quando isso aconteça, o tratamento deve apoiar-se num mecanismo válido do capítulo V
          do RGPD, como uma decisão de adequação ou cláusulas contratuais-tipo. Não vendemos nem
          alugamos dados pessoais.
        </p>

        <h2>6. Direitos</h2>
        <p>
          Pode pedir acesso, retificação, apagamento, limitação, oposição ou portabilidade
          quando aplicável. A oposição baseada na sua situação particular é analisada através
          da ponderação entre os seus direitos e os fundamentos imperiosos de informação
          pública. Escreva para <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>; podemos
          pedir apenas a informação necessária para confirmar identidade e localizar o registo.
          Responderemos sem demora injustificada e, em regra, no prazo de um mês.
        </p>
        <p>
          Pode também reclamar junto da <a href="https://www.cnpd.pt/cidadaos/direitos/" target="_blank" rel="noreferrer noopener">Comissão Nacional de Proteção de Dados</a>.
        </p>

        <h2>7. Automatização, segurança e alterações</h2>
        <p>
          Não existem decisões exclusivamente automatizadas com efeitos jurídicos, publicidade
          comportamental ou classificação política de visitantes. Aplicamos separação entre
          recolha e publicação, controlo de acesso, ligações cifradas, minimização e registos de
          proveniência. Nenhum sistema é infalível; incidentes serão avaliados e notificados
          quando a lei o exigir.
        </p>
        <p>
          Consulte o <a href="https://eur-lex.europa.eu/eli/reg/2016/679/oj?locale=pt" target="_blank" rel="noreferrer noopener">Regulamento Geral sobre a Proteção de Dados</a> e a <a href="https://diariodarepublica.pt/dr/detalhe/lei/58-2019-123815982" target="_blank" rel="noreferrer noopener">Lei n.º 58/2019</a>.
        </p>
        <p className="legal-updated">Versão publicada em {LEGAL_UPDATED_AT}.</p>
      </section>
    </main>
  );
}
