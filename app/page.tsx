import {
  ArrowRightIcon,
  ChartIcon,
  LandmarkIcon,
  MapPinIcon,
  ShieldCheckIcon,
  UserIcon,
} from "@/components/icons";
import { DataModeBanner } from "@/components/data-mode-banner";
import { DataStatusCard } from "@/components/data-status-card";
import { PushSubscribe } from "@/components/push-subscribe";
import { SourceLink } from "@/components/source-link";
import { loadPublicDataStatus } from "@/lib/public-data";

const officialSources = [
  {
    label: "Assembleia da República — Dados Abertos",
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
    label: "Portal BASE — Contratos Públicos",
    url: "https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2025/",
    publisher: "BASE" as const,
  },
];

export const revalidate = 60;

export default async function Home() {
  const dataStatus = await loadPublicDataStatus();
  const hasLiveData = dataStatus.mode === "LIVE";
  return (
    <main>
      <section className="hero-section">
        <div className="hero-grid shell">
          <div className="hero-copy">
            <div className="hero-kicker"><ShieldCheckIcon /> V4 · Dados oficiais com publicação controlada</div>
            <h1>Realidade nacional.<br /><span>Cada ligação com prova.</span></h1>
            <p>
              Cruze contratos públicos, cargos, votações, declarações e impacto das leis.
              Sem acusações automáticas: cada relação visível identifica fonte, hash e estado de revisão.
            </p>
            <div className="hero-actions">
              <a className="button button--primary" href="/investigador">
                Abrir Investigador Cívico <ArrowRightIcon />
              </a>
              <a className="button button--ghost" href="/guia-cidadao">
                Simular impacto de uma lei
              </a>
            </div>
            <div className="source-stack">
              <span>Fontes oficiais acompanhadas</span>
              <div>
                {officialSources.map((source) => <SourceLink source={source} compact key={source.publisher} />)}
              </div>
            </div>
          </div>

          <DataStatusCard status={dataStatus} />
        </div>
      </section>

      <div className="shell demo-wrap">
        <DataModeBanner status={dataStatus} showingFallback={!hasLiveData} />
      </div>

      <section className="overview-section shell">
        <div className="section-intro">
          <div>
            <span className="eyebrow">Uma só plataforma</span>
            <h2>Do contrato público ao impacto no cidadão</h2>
          </div>
          <p>
            A V4 torna visíveis proveniência, cobertura, exclusões metodológicas,
            lacunas, datas de actualização e decisões de publicação.
          </p>
        </div>

        <div className="feature-grid">
          <a className="feature-card feature-card--large" href="/investigador">
            <div className="feature-icon"><UserIcon /></div>
            <span className="eyebrow">Investigador Cívico</span>
            <h3>Veja como pessoas, cargos, organizações e contratos se ligam.</h3>
            <p>Filtros por ano, montante e entidade. Cada aresta abre a prova que a sustenta.</p>
            <span className="text-link">{hasLiveData ? "Explorar dados publicados" : "Explorar amostra identificada"} <ArrowRightIcon /></span>
            <div className="profile-mini-card">
              <div className="profile-mini-avatar"><LandmarkIcon /></div>
              <div><strong>Contratos públicos publicáveis</strong><span>Fonte BASE · revisão humana obrigatória</span></div>
              <div className="mini-score"><strong>{dataStatus.counts.contracts}</strong><span>aprovados</span></div>
            </div>
          </a>

          <a className="feature-card feature-card--accent" href="/guia-cidadao">
            <div className="feature-icon"><ChartIcon /></div>
            <span className="eyebrow">Guia Neutro do Cidadão</span>
            <h3>Primeiro calcula a regra. Depois a IA explica.</h3>
            <p>Perfis genéricos, sem NIF nem rendimento exacto, com fonte e incerteza visíveis.</p>
            <span className="text-link">Testar simulador privado <ArrowRightIcon /></span>
          </a>

          <a className="feature-card" href="/atividade-parlamentar">
            <div className="feature-icon"><MapPinIcon /></div>
            <span className="eyebrow">Atividade parlamentar</span>
            <h3>Sessões, iniciativas e votações numa fotografia verificável.</h3>
            <p>O histórico permanece imutável e nenhuma nova recolha é publicada sem revisão.</p>
            <div className="region-preview">
              <span>XVII Legislatura</span>
              <strong>{dataStatus.counts.parliamentVotes} votações aprovadas</strong>
            </div>
          </a>
        </div>
      </section>

      <section className="principles-section">
        <div className="shell principles-grid">
          <div>
            <span className="eyebrow eyebrow--light">Contrato de confiança</span>
            <h2>Uma ligação não é uma acusação.<br />É uma hipótese a provar.</h2>
            <p>
              A V4 separa ingestão, correspondência técnica, prova oficial, revisão editorial
              e publicação. O estado de cada passo permanece visível.
            </p>
            <a className="button button--light" href="/metodologia">Ler metodologia completa</a>
          </div>
          <div className="principle-list">
            <div><span>01</span><div><strong>Correspondência não é conclusão</strong><p>Nome ou NIF coincidente gera revisão, nunca uma acusação.</p></div></div>
            <div><span>02</span><div><strong>Direito de resposta imutável</strong><p>A contestação é anexada com timestamp e SHA-256.</p></div></div>
            <div><span>03</span><div><strong>IA com direito a abster-se</strong><p>Sem factos suficientes, a resposta correcta é “não é possível determinar”.</p></div></div>
          </div>
        </div>
      </section>

      <section className="local-alert-section shell">
        <div className="local-alert-copy">
          <LandmarkIcon />
          <div>
            <span className="eyebrow">PWA V4 instalável</span>
            <h2>Alertas úteis, não propaganda.</h2>
            <p>Escolha apenas região e temas cívicos. Sem publicidade, filiação política, geolocalização exacta ou recomendação eleitoral.</p>
          </div>
        </div>
        <PushSubscribe />
      </section>
    </main>
  );
}
