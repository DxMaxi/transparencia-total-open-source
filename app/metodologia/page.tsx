import type { Metadata } from "next";
import { SourceLink } from "@/components/source-link";

export const metadata: Metadata = {
  title: "Metodologia e neutralidade",
  description:
    "Critérios de recolha, proveniência, revisão, publicação, correção e neutralidade da Transparência Total.",
  alternates: { canonical: "/metodologia" },
};

const sources = [
  {
    label: "Dados Abertos — Assembleia da República",
    url: "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx",
    publisher: "AR" as const,
  },
  {
    label: "Diário da República",
    url: "https://diariodarepublica.pt/",
    publisher: "DRE" as const,
  },
  {
    label: "Entidade para a Transparência",
    url: "https://www.tribunalconstitucional.pt/tc/ept/",
    publisher: "EPT" as const,
  },
  {
    label: "Portal BASE — contratos públicos",
    url: "https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2025/",
    publisher: "BASE" as const,
  },
  {
    label: "Tribunal de Contas",
    url: "https://www.tcontas.pt/",
    publisher: "TCONTAS" as const,
  },
  {
    label: "Parlamento Europeu — Open Data",
    url: "https://data.europarl.europa.eu/en/home",
    publisher: "PE" as const,
  },
];

export default function MethodologyPage() {
  return (
    <main className="page-shell shell methodology-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Método público e reproduzível</span>
        <h1>Como transformamos documentos em factos auditáveis</h1>
        <p>
          “Transparência Total” é o nome e a ambição do projeto, não uma garantia absoluta. Nenhum sistema pode
          garantir que uma fonte pública está completa; por isso mostramos lacunas,
          atrasos, erros e a data exata de cada recolha.
        </p>
      </header>

      <section className="method-grid">
        <article className="card method-card"><span>01</span><h2>Recolher</h2><p>O coletor descarrega apenas de domínios oficiais autorizados, respeita limites e conserva URL e versão.</p></article>
        <article className="card method-card"><span>02</span><h2>Preservar</h2><p>O documento bruto recebe SHA-256. Uma atualização acrescenta uma versão e nunca apaga a anterior.</p></article>
        <article className="card method-card"><span>03</span><h2>Corresponder</h2><p>Nome ou identificador coincidente cria um candidato técnico pendente; ainda não é uma relação publicável.</p></article>
        <article className="card method-card"><span>04</span><h2>Provar</h2><p>A ligação exige documento oficial que identifique as entidades, o tipo de relação e o período relevante.</p></article>
        <article className="card method-card"><span>05</span><h2>Rever</h2><p>Um revisor verifica identidade, interesse público, proporcionalidade, contexto e direito de resposta.</p></article>
        <article className="card method-card"><span>06</span><h2>Publicar</h2><p>A interface mostra fonte, hash, cobertura, metodologia, decisão editorial e histórico de alterações.</p></article>
      </section>

      <section className="card methodology-block" id="neutralidade">
        <span className="eyebrow">Neutralidade operacional</span>
        <h2>As mesmas regras para todos</h2>
        <ul>
          <li>Não inferir voto individual quando a fonte regista apenas a posição do grupo parlamentar.</li>
          <li>Não apresentar uma coincidência de nome, NIF ou empresa como corrupção, favorecimento ou conflito.</li>
          <li>Não indexar relações familiares, doações ou processos sem prova oficial e teste documentado de interesse público.</li>
          <li>Não classificar uma promessa através de notícias, redes sociais ou opinião partidária.</li>
          <li>Calcular coerência apenas sobre pares comparáveis revistos, publicando o denominador e as exclusões.</li>
          <li>Usar “dados indisponíveis” em vez de transformar ausência de dados em falta, incumprimento ou suspeita.</li>
          <li>Publicar correções sem apagar o histórico, incluindo autor, data e fundamento.</li>
          <li>Separar cálculo técnico, prova documental e decisão humana de publicação.</li>
        </ul>
      </section>

      <section className="card methodology-block">
        <span className="eyebrow">Fontes primárias</span>
        <h2>O ponto de partida é sempre oficial</h2>
        <div className="method-source-list">
          {sources.map((source) => <SourceLink source={source} key={source.publisher} />)}
        </div>
      </section>
    </main>
  );
}
