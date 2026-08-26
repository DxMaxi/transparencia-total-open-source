import { CheckIcon, ClockIcon, UserIcon } from "@/components/icons";
import { SourceLink } from "@/components/source-link";
import type {
  PoliticianProfileData,
  ProfileCoverageArea,
  ProfileCoverageState,
  VoteChoice,
  VoteRecord,
} from "@/types/domain";

const voteLabels: Record<VoteChoice, string> = {
  FAVOR: "A favor",
  AGAINST: "Contra",
  ABSTENTION: "Abstenção",
  ABSENT: "Ausente",
};

const coverageStateLabels: Record<ProfileCoverageState, string> = {
  AVAILABLE: "Disponível",
  PARTIAL: "Cobertura parcial",
  UNAVAILABLE: "Dados indisponíveis",
};

const initiativeRelationLabels = {
  AUTHOR: "Autoria",
  COAUTHOR: "Coautoria",
  PROPOSER: "Proponente",
} as const;

function proofDate(value: string | undefined): string {
  if (!value) return "dados indisponíveis";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "dados indisponíveis";
  return new Intl.DateTimeFormat("pt-PT", {
    dateStyle: "medium",
    timeZone: "Europe/Lisbon",
  }).format(date);
}

function coveragePeriod(area: ProfileCoverageArea): string | null {
  if (!area.observedFrom && !area.observedThrough) return null;
  if (area.observedFrom === area.observedThrough) return area.observedFrom ?? null;
  return `${area.observedFrom ?? "Início não indicado"} — ${area.observedThrough ?? "presente"}`;
}

function CoverageCard({
  title,
  area,
}: {
  title: string;
  area: ProfileCoverageArea;
}) {
  const period = coveragePeriod(area);
  return (
    <article className="profile-coverage-card">
      <div className="profile-coverage-card__heading">
        <h3>{title}</h3>
        <span className={`coverage-state coverage-state--${area.state.toLowerCase()}`}>
          {coverageStateLabels[area.state]}
        </span>
      </div>
      <strong>{area.recordCount.toLocaleString("pt-PT")} registos</strong>
      {period ? <small>Período observado: {period}</small> : null}
      <p>{area.note}</p>
      {area.source ? <SourceLink source={area.source} compact /> : null}
    </article>
  );
}

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
  const coverageAreas = [
    ["Identidade", profile.coverage.identity],
    ["Observações parlamentares", profile.coverage.membershipObservations],
    ["Mandatos datados", profile.coverage.mandates],
    ["Cargos parlamentares", profile.coverage.parliamentaryOffices],
    ["Presenças", profile.coverage.attendance],
    ["Iniciativas individuais", profile.coverage.initiatives],
    ["Votos nominais", profile.coverage.nominalVotes],
    ["Declarações", profile.coverage.declarations],
  ] as const;

  return (
    <article className="politician-profile">
      <section className="profile-hero card">
        <div className="profile-avatar" aria-hidden="true">
          <UserIcon />
        </div>
        <div className="profile-heading">
          <div className="eyebrow-row">
            <span className="eyebrow">Perfil político auditável</span>
            <span className="verified-chip"><CheckIcon /> Fonte oficial aprovada</span>
          </div>
          <h1>{profile.name}</h1>
          <p>{profile.role}</p>
          <div className="profile-meta">
            <span>
              Grupo indicado na fonte: <strong>{profile.partyShort}</strong>
              {profile.party && profile.party !== profile.partyShort ? ` — ${profile.party}` : ""}
            </span>
            <span>Círculo: {profile.constituency}</span>
            <span>Legislatura: {profile.legislature}</span>
          </div>
        </div>
        <div className="profile-source">
          <span>Observado na fonte em</span>
          <strong>{profile.observedAt}</strong>
          <span>Revisão humana em {profile.verifiedAt}</span>
          <SourceLink source={profile.profileSource} compact />
        </div>
      </section>

      {profile.contractVersion === "legacy" ? (
        <aside className="profile-compatibility-note card">
          <strong>API pública em transição para o contrato V5.6</strong>
          <p>
            Esta ficha continua legível, mas algumas áreas ainda não expõem a cobertura e as
            decisões específicas da V5.6. Essas áreas aparecem como parciais ou indisponíveis.
          </p>
        </aside>
      ) : null}

      <section className="card profile-section" aria-labelledby="profile-coverage-title">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">O que sabemos — e o que não sabemos</span>
            <h2 id="profile-coverage-title">Cobertura desta ficha</h2>
          </div>
          <span className="profile-contract-chip">Contrato {profile.contractVersion}</span>
        </div>
        <p className="profile-section-intro">
          Cada área tem a sua própria porta de publicação. “Dados indisponíveis” não significa
          ausência, incumprimento ou ocultação por parte da pessoa.
        </p>
        <div className="profile-coverage-grid">
          {coverageAreas.map(([title, area]) => (
            <CoverageCard key={title} title={title} area={area} />
          ))}
        </div>
        <p className="profile-matching-rule"><strong>Regra de associação:</strong> {profile.coverage.matchingRule}</p>
      </section>

      <section className="profile-two-column">
        <div className="card profile-section">
          <span className="eyebrow">Períodos com datas oficiais</span>
          <h2>Mandatos parlamentares</h2>
          {profile.mandates.length ? (
            <ol className="profile-timeline">
              {profile.mandates.map((mandate) => (
                <li key={mandate.id}>
                  <div>
                    <strong>{mandate.officeTitle}</strong>
                    <span>{mandate.startedAt} — {mandate.endedAt ?? "fim não indicado"}</span>
                    <small>
                      {[mandate.legislature, mandate.constituency, mandate.partyShort]
                        .filter(Boolean)
                        .join(" · ")}
                    </small>
                  </div>
                  <div className="profile-timeline__proof">
                    <small>Revisto em {mandate.verifiedAt}</small>
                    <SourceLink source={mandate.source} compact />
                    <small>Fonte recolhida em {proofDate(mandate.source.retrievedAt)}</small>
                    {mandate.source.sha256 ? (
                      <code title={`SHA-256 da fonte ${mandate.source.sha256}`}>
                        Fonte SHA-256 {mandate.source.sha256}
                      </code>
                    ) : (
                      <small>SHA-256 da fonte: dados indisponíveis</small>
                    )}
                    {mandate.sourcePeriodSha256 ? (
                      <code title={`SHA-256 do intervalo ${mandate.sourcePeriodSha256}`}>
                        Intervalo SHA-256 {mandate.sourcePeriodSha256}
                      </code>
                    ) : (
                      <small>Prova do intervalo: dados indisponíveis</small>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <div className="profile-unavailable-inline">
              <strong>Dados de mandato indisponíveis</strong>
              <p>{profile.coverage.mandates.note}</p>
            </div>
          )}
        </div>

        <div className="card profile-section">
          <span className="eyebrow">Funções com CarId oficial e revisão própria</span>
          <h2>Cargos parlamentares observados</h2>
          <p className="profile-section-intro">
            Estes cargos são apresentados separadamente dos mandatos. O período corresponde ao
            que a fonte oficial indica e não prova competências atuais fora dessas datas.
          </p>
          {profile.parliamentaryOffices.length ? (
            <ol className="profile-timeline">
              {profile.parliamentaryOffices.map((office) => (
                <li key={office.id}>
                  <div>
                    <strong>{office.title}</strong>
                    <span>{office.startedAt} — {office.endedAt ?? "fim não indicado"}</span>
                    <small>
                      {office.legislature} · {office.constituency} · CarId {office.officialOfficeId}
                    </small>
                  </div>
                  <div className="profile-timeline__proof">
                    <small>Revisto em {office.verifiedAt}</small>
                    <SourceLink source={office.source} compact />
                    <small>Fonte recolhida em {proofDate(office.source.retrievedAt)}</small>
                    <code title={`SHA-256 da fonte ${office.source.sha256}`}>
                      Fonte SHA-256 {office.source.sha256 ?? "dados indisponíveis"}
                    </code>
                    <code title={`SHA-256 do período ${office.sourcePeriodSha256}`}>
                      Período SHA-256 {office.sourcePeriodSha256}
                    </code>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <div className="profile-unavailable-inline">
              <strong>Dados de cargos indisponíveis</strong>
              <p>{profile.coverage.parliamentaryOffices.note}</p>
            </div>
          )}
        </div>
      </section>

      <section className="card profile-section">
          <span className="eyebrow">Fotografias oficiais sucessivas</span>
          <h2>Pertença parlamentar observada</h2>
          <p className="profile-section-intro">
            Estas datas dizem apenas quando a pessoa apareceu na fonte recolhida. Não são datas
            inferidas de início ou fim de mandato.
          </p>
          {profile.membershipObservations.length ? (
            <details className="profile-history" open={profile.membershipObservations.length <= 3}>
              <summary>
                Ver {profile.membershipObservations.length.toLocaleString("pt-PT")} observações
              </summary>
              <ol className="profile-observation-list">
                {profile.membershipObservations.map((observation) => (
                  <li key={observation.id}>
                    <div>
                      <strong>{observation.observedAt}</strong>
                      <span>{observation.legislature} · {observation.constituency}</span>
                      <small>
                        Grupo indicado na fonte: {observation.partyShort} — {observation.party}
                      </small>
                    </div>
                    <SourceLink source={observation.source} compact />
                  </li>
                ))}
              </ol>
            </details>
          ) : (
            <div className="profile-unavailable-inline">
              <strong>Histórico de observações indisponível</strong>
              <p>{profile.coverage.membershipObservations.note}</p>
            </div>
          )}
      </section>

      <section className="card profile-section">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Registos individuais revistos</span>
            <h2>Presenças</h2>
          </div>
          {profile.attendance.observedFrom || profile.attendance.observedThrough ? (
            <span className="profile-period-label">
              {profile.attendance.observedFrom ?? "Início não indicado"} — {profile.attendance.observedThrough ?? "presente"}
            </span>
          ) : null}
        </div>
        {profile.attendance.available ? (
          <div className="profile-stat-grid">
            <div><span>Taxa nos registos disponíveis</span><strong>{profile.attendance.attendanceRate ?? 0}%</strong></div>
            <div><span>Registos com presença</span><strong>{profile.attendance.presentCount.toLocaleString("pt-PT")}</strong></div>
            <div><span>Registos sem presença</span><strong>{profile.attendance.absentCount.toLocaleString("pt-PT")}</strong></div>
            <div><span>Com justificação indicada</span><strong>{profile.attendance.excusedCount.toLocaleString("pt-PT")}</strong></div>
          </div>
        ) : (
          <div className="profile-unavailable-inline">
            <strong>Presenças individuais não publicadas</strong>
            <p>{profile.attendance.note}</p>
          </div>
        )}
        {profile.attendance.available ? <p className="profile-data-note">{profile.attendance.note}</p> : null}
        {profile.attendance.source ? <SourceLink source={profile.attendance.source} compact /> : null}
      </section>

      <section className="card profile-section">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Autoria individual verificável</span>
            <h2>Iniciativas parlamentares</h2>
          </div>
        </div>
        {profile.initiatives.length ? (
          <ol className="profile-initiative-list">
            {profile.initiatives.map((initiative) => (
              <li key={initiative.id}>
                <div>
                  <span className="eyebrow">{initiativeRelationLabels[initiative.relation]} · {initiative.initiativeType}</span>
                  <strong>{initiative.title}</strong>
                  <small>{initiative.number}{initiative.status ? ` · ${initiative.status}` : ""}</small>
                </div>
                <SourceLink source={initiative.source} compact />
              </li>
            ))}
          </ol>
        ) : (
          <div className="profile-unavailable-inline">
            <strong>Associação individual indisponível</strong>
            <p>{profile.coverage.initiatives.note}</p>
          </div>
        )}
      </section>

      <section className="card profile-section">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Metadados sujeitos a revisão jurídica</span>
            <h2>Declarações</h2>
          </div>
        </div>
        {profile.declarations.length ? (
          <div className="profile-declaration-list">
            {profile.declarations.map((declaration) => (
              <article className="profile-declaration-record" key={declaration.id}>
                <div>
                  <strong>{declaration.declarationType}</strong>
                  <span>{declaration.periodLabel ?? "Período não indicado"}</span>
                  <small>
                    Data declarada: {declaration.declaredAt ?? "dados indisponíveis"} · Estado de
                    acesso: {declaration.publicAccessStatus}
                  </small>
                </div>
                <div>
                  <small>Revisto em {declaration.verifiedAt}</small>
                  <SourceLink source={declaration.source} compact />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="profile-declaration-lookup">
            <div>
              <strong>Sem metadados individuais aprovados para publicação</strong>
              <p>{profile.coverage.declarations.note}</p>
              <small>{profile.declarationLookupSource.note}</small>
            </div>
            <a
              className="button button--ghost"
              href={profile.declarationLookupSource.url}
              target="_blank"
              rel="noreferrer"
            >
              Consultar portal institucional
            </a>
          </div>
        )}
      </section>

      {profile.nominalVotesAvailable && profile.votes.length ? (
        <section className="card profile-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Identificador oficial exato</span>
              <h2>Votos individuais publicados</h2>
            </div>
            <span className="profile-period-label">
              {profile.nominalVoteCount.toLocaleString("pt-PT")} na fotografia publicada
            </span>
          </div>
          <p className="profile-section-intro">
            A tabela mostra até 50 registos recentes. A contagem refere-se à fotografia oficial
            publicada, não ao tamanho desta página.
          </p>
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
          <strong>Sem votos individuais publicáveis nesta fotografia</strong>
          <p>{profile.coverage.nominalVotes.note}</p>
        </aside>
      )}

      <aside className="profile-method-note card">
        <strong>O que esta ficha nunca faz</strong>
        <p>
          Não atribui à pessoa posições coletivas do grupo, não reconstrói mandatos a partir de
          fotografias isoladas e não conclui ausência, incumprimento ou intenção a partir de uma
          lacuna. Uma sigla ou um nome semelhante não é suficiente e nunca substitui um
          identificador oficial inequívoco.
        </p>
      </aside>
    </article>
  );
}
