import { CheckIcon, ClockIcon, UserIcon } from "@/components/icons";
import { SourceLink } from "@/components/source-link";
import type { PoliticianProfileData, VoteChoice, VoteRecord } from "@/types/domain";

const voteLabels: Record<VoteChoice, string> = {
  FAVOR: "A favor",
  AGAINST: "Contra",
  ABSTENTION: "Abstenção",
  ABSENT: "Ausente",
};

function VoteRows({ votes }: { votes: VoteRecord[] }) {
  return (
    <tbody>
      {votes.map((vote) => (
        <tr key={vote.id}>
          <td>
            <strong>{vote.title}</strong>
            <small>{vote.initiativeNumber}</small>
          </td>
          <td><span className="table-date"><ClockIcon /> {vote.date}</span></td>
          <td>
            <span className={`vote-pill vote-pill--${vote.choice.toLowerCase()}`}>
              {voteLabels[vote.choice]}
            </span>
          </td>
          <td>{vote.result}</td>
          <td><SourceLink source={vote.source} compact /></td>
        </tr>
      ))}
    </tbody>
  );
}

export function PoliticianProfile({ profile }: { profile: PoliticianProfileData }) {
  return (
    <article className="politician-profile">
      <section className="profile-hero card">
        <div className="profile-avatar" aria-hidden="true">
          <UserIcon />
        </div>
        <div className="profile-heading">
          <div className="eyebrow-row">
            <span className="eyebrow">Ficha parlamentar</span>
            <span className="verified-chip"><CheckIcon /> Fonte oficial aprovada</span>
          </div>
          <h1>{profile.name}</h1>
          <p>{profile.role}</p>
          <div className="profile-meta">
            <span>
              <strong>{profile.partyShort}</strong>
              {profile.party && profile.party !== profile.partyShort ? ` ${profile.party}` : ""}
            </span>
            <span>{profile.constituency}</span>
            <span>{profile.legislature}</span>
          </div>
        </div>
        <div className="profile-source">
          <span>Fonte observada em</span>
          <strong>{profile.verifiedAt}</strong>
          <SourceLink source={profile.profileSource} compact />
        </div>
      </section>

      <section className="profile-stats" aria-label="Cobertura disponível">
        <div className="stat-card card">
          <span className="stat-card__label">Presenças individuais</span>
          <strong>{profile.attendanceRate == null ? "Não publicadas" : `${profile.attendanceRate}%`}</strong>
          {profile.attendanceRate != null ? (
            <div className="progress-track"><span style={{ width: `${profile.attendanceRate}%` }} /></div>
          ) : null}
          <small>{profile.attendanceLabel}</small>
        </div>
        <div className="stat-card card">
          <span className="stat-card__label">Votos individuais</span>
          <strong>{profile.nominalVotesAvailable ? profile.nominalVoteCount : "Não publicados"}</strong>
          <small>
            Só contamos registos nominais. Uma posição partidária nunca é apresentada
            como voto pessoal.
          </small>
        </div>
        <div className="stat-card card">
          <span className="stat-card__label">Declarações de interesses</span>
          <strong>Pesquisa na fonte oficial</strong>
          <SourceLink source={profile.declarationSource} compact />
        </div>
      </section>

      {profile.nominalVotesAvailable && profile.votes.length ? (
        <section className="card profile-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Registos nominais</span>
              <h2>Votos individuais publicados</h2>
            </div>
          </div>
          <div className="vote-table-wrap">
            <table className="vote-table">
              <thead>
                <tr><th>Iniciativa</th><th>Data</th><th>Voto</th><th>Resultado</th><th>Prova</th></tr>
              </thead>
              <VoteRows votes={profile.votes} />
            </table>
          </div>
        </section>
      ) : (
        <aside className="profile-coverage-note card">
          <strong>Sem votos individuais publicáveis nesta fonte</strong>
          <p>
            Isto não significa que a pessoa não votou. Significa que a fotografia oficial
            publicada não permite atribuir inequivocamente uma posição individual.
          </p>
        </aside>
      )}

      <section className="card profile-section">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Contexto parlamentar</span>
            <h2>Posições recentes do grupo {profile.partyShort}</h2>
          </div>
          <span className="collective-position-label">Não são votos individuais</span>
        </div>
        <p className="profile-section-intro">
          As linhas abaixo são aquelas em que a fonte usa exatamente a sigla do grupo
          parlamentar. São apresentadas como contexto coletivo e nunca como ação pessoal
          de {profile.name}.
        </p>
        {profile.groupPositions.length ? (
          <div className="vote-table-wrap">
            <table className="vote-table">
              <thead>
                <tr><th>Iniciativa</th><th>Data</th><th>Posição</th><th>Resultado</th><th>Prova</th></tr>
              </thead>
              <VoteRows votes={profile.groupPositions} />
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>Sem posições coletivas normalizadas para este grupo</strong>
            <span>A fonte pode não indicar posições por grupo em todas as votações.</span>
          </div>
        )}
      </section>
    </article>
  );
}
