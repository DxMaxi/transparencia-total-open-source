import type { Metadata } from "next";
import {
  ArrowRightIcon,
  BellIcon,
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
import { initialGovernmentCommitments } from "@/lib/government-programme";
import { loadPublicDataStatus } from "@/lib/public-data";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

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
  {
    label: "Programa do XXV Governo Constitucional",
    url: "https://portugal.gov.pt/gc25/governo/programa-do-governo",
    publisher: "OFICIAL" as const,
  },
];

export const revalidate = 60;

export default async function Home() {
  const dataStatus = await loadPublicDataStatus();
  const hasLiveData = dataStatus.mode === "LIVE";
  const promiseCount = Math.max(
    dataStatus.counts.promises,
    initialGovernmentCommitments.length,
  );
  return (
    <main>
      <section className="hero-section">
        <div className="hero-grid shell">
          <div className="hero-copy">
            <div className="hero-kicker"><ShieldCheckIcon /> Dados públicos com fonte identificada</div>
            <h1>Política portuguesa.<br /><span>Factos que pode confirmar.</span></h1>
            <p>
              Consulte representantes, iniciativas, votações e compromissos do Governo.
              Cada registo publicado mostra a sua origem e os limites do que é possível concluir.
            </p>
            <div className="hero-actions">
              <a className="button button--primary" href="/atividade-parlamentar">
                Consultar o Parlamento <ArrowRightIcon />
              </a>
              <a className="button button--ghost" href="/politicos">
                Ver representantes
              </a>
              <a className="button button--ghost" href="/explicacoes">
                Explicações com IA revista
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

      <div className="shell status-wrap">
        <DataModeBanner status={dataStatus} showingFallback={!hasLiveData} />
      </div>

      <section className="overview-section shell">
        <div className="section-intro">
          <div>
            <span className="eyebrow">Uma só plataforma</span>
            <h2>Do contrato público ao impacto no cidadão</h2>
          </div>
          <p>
            A plataforma torna visíveis proveniência, cobertura, exclusões metodológicas,
            lacunas, datas de atualização e decisões de publicação.
          </p>
        </div>

        <div className="feature-grid">
          <a className="feature-card feature-card--large" href="/politicos">
            <div className="feature-icon"><UserIcon /></div>
            <span className="eyebrow">Representantes</span>
            <h3>Consulte os deputados da XVII Legislatura e a respetiva origem oficial.</h3>
            <p>Partido, círculo eleitoral, fonte oficial, data de verificação e limites dos dados individuais.</p>
            <span className="text-link">Ver {dataStatus.counts.politicians} perfis publicados <ArrowRightIcon /></span>
            <div className="profile-mini-card">
              <div className="profile-mini-avatar"><LandmarkIcon /></div>
              <div><strong>Dados parlamentares oficiais</strong><span>Assembleia da República · XVII Legislatura</span></div>
              <div className="mini-score"><strong>{dataStatus.counts.politicians}</strong><span>perfis</span></div>
            </div>
          </a>

          <a className="feature-card feature-card--accent" href="/promessas">
            <div className="feature-icon"><ChartIcon /></div>
            <span className="eyebrow">Promessómetro</span>
            <h3>Compromissos oficiais sem classificações precipitadas.</h3>
            <p>O catálogo começa pelo Programa do XXV Governo. Sem prova de execução, a medida fica por verificar.</p>
            <span className="text-link">Consultar {promiseCount} compromissos <ArrowRightIcon /></span>
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
              A plataforma separa ingestão, correspondência técnica, prova oficial, revisão editorial
              e publicação. O estado de cada passo permanece visível.
            </p>
            <a className="button button--light" href="/metodologia">Ler metodologia completa</a>
          </div>
          <div className="principle-list">
            <div><span>01</span><div><strong>Correspondência não é conclusão</strong><p>Nome ou NIF coincidente gera revisão, nunca uma acusação.</p></div></div>
            <div><span>02</span><div><strong>Direito de resposta imutável</strong><p>A contestação é anexada com timestamp e SHA-256.</p></div></div>
            <div><span>03</span><div><strong>Sem conclusões automáticas</strong><p>Sem factos suficientes, a plataforma mostra a lacuna e não atribui intenções ou responsabilidades.</p></div></div>
          </div>
        </div>
      </section>

      <section className="local-alert-section shell" aria-labelledby="local-alert-title">
        <div className="local-alert-copy">
          <BellIcon />
          <div>
            <span className="eyebrow">Escolha do cidadão</span>
            <h2 id="local-alert-title">Acompanhe apenas o que decidiu seguir</h2>
            <p>
              Escolha uma região e ative notificações apenas se quiser. O pedido de permissão só
              acontece depois do seu consentimento, e a subscrição pode ser alterada ou apagada.
            </p>
          </div>
        </div>
        <PushSubscribe />
      </section>

    </main>
  );
}
