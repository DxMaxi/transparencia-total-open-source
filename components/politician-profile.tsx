import { CheckIcon, ClockIcon, UserIcon } from "@/components/icons";
import { SourceLink } from "@/components/source-link";
import type { PoliticianProfileData, VoteChoice } from "@/types/domain";

const voteLabels: Record<VoteChoice, string> = {
  FAVOR: "A favor",
  AGAINST: "Contra",
  ABSTENTION: "Abstenção",
  ABSENT: "Ausente",
};

export function PoliticianProfile({ profile }: { profile: PoliticianProfileData }) {
  return (
    <article className="politician-profile">
      <section className="profile-hero card">
        <div className="profile-avatar" aria-hidden="true">
          <UserIcon />
        </div>
        <div className="profile-heading">
          <div className="eyebrow-row">
            <span className="eyebrow">Ficha individual</span>
            <span className="verified-chip"><CheckIcon /> Origem identificada</span>
          </div>
          <h1>{profile.name}</h1>
          <p>{profile.role}</p>
          <div className="profile-meta">
            <span><strong>{profile.partyShort}</strong> {profile.party}</span>
            <span>{profile.constituency}</span>
            <span>{profile.legislature}</span>
          </div>
        </div>
        <div className="profile-source">
          <span>Ficha verificada</span>
          <strong>{profile.verifiedAt}</strong>
          <SourceLink source={profile.profileSource} compact />
        </div>
      </section>

      <section className="profile-stats" aria-label="Indicadores do mandato">
        <div className="stat-card card">
          <span className="stat-card__label">Assiduidade</span>
          <strong>{profile.attendanceRate == null ? "Sem dados" : `${profile.attendanceRate}%`}</strong>
          <div className="progress-track"><span style={{ width: `${profile.attendanceRate ?? 0}%` }} /></div>
          <small>{profile.attendanceLabel}</small>
        </div>
        <div className="stat-card card">
          <span className="stat-card__label">Votações nominais</span>
          <strong>{profile.votes.filter((vote) => vote.isNominal).length}</strong>
          <small>Não atribui votos partidários a pessoas individuais.</small>
        </div>
        <div className="stat-card card">
          <span className="stat-card__label">Declaração de interesses</span>
          <strong>Consultar fonte</strong>
          <SourceLink source={profile.declarationSource} compact />
        </div>
      </section>

      <section className="card profile-section">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Histórico auditável</span>
            <h2>Votações recentes</h2>
          </div>
          <div className="vote-legend" aria-label="Legenda dos votos">
            <span><i className="dot dot--favor" /> A favor</span>
            <span><i className="dot dot--against" /> Contra</span>
            <span><i className="dot dot--abstention" /> Abstenção</span>
          </div>
        </div>
        <div className="vote-table-wrap">
          <table className="vote-table">
            <thead>
              <tr>
                <th>Iniciativa</th>
                <th>Data</th>
                <th>Voto</th>
                <th>Resultado</th>
                <th>Prova</th>
              </tr>
            </thead>
            <tbody>
              {profile.votes.map((vote) => (
                <tr key={vote.id}>
                  <td>
                    <strong>{vote.title}</strong>
                    <small>{vote.initiativeNumber}</small>
                  </td>
                  <td><span className="table-date"><ClockIcon /> {vote.date}</span></td>
                  <td><span className={`vote-pill vote-pill--${vote.choice.toLowerCase()}`}>{voteLabels[vote.choice]}</span></td>
                  <td>{vote.result}</td>
                  <td><SourceLink source={vote.source} compact /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="comparison-panel card">
        <div>
          <span className="eyebrow">Discurso e decisão</span>
          <h2>Comparador de declarações e votos</h2>
          <p>
            Uma comparação só é publicada quando existem transcrição ou vídeo oficial,
            votação identificável e revisão humana. A IA pode sugerir relações; não decide
            se existe contradição.
          </p>
        </div>
        <div className="comparison-empty">
          <strong>Sem comparação validada</strong>
          <span>Nenhuma conclusão editorial é inferida a partir dos dados de demonstração.</span>
        </div>
      </section>
    </article>
  );
}
