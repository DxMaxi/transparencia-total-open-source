import type { Metadata } from "next";
import { DataModeBanner } from "@/components/data-mode-banner";
import { SourceLink } from "@/components/source-link";
import { loadPublicParliamentActivity } from "@/lib/public-data";

export const metadata: Metadata = {
  title: "Atividade parlamentar",
  description:
    "Reuniões observadas, iniciativas e votações da Assembleia da República com fonte, revisão e limitações visíveis.",
};

export const revalidate = 60;

const choiceLabels = {
  FAVOR: "A favor",
  AGAINST: "Contra",
  ABSTENTION: "Abstenção",
  ABSENT: "Ausência",
  UNKNOWN: "Não determinado",
};

export default async function ParliamentActivityPage() {
  const loaded = await loadPublicParliamentActivity("XVII");
  const { sessions, initiatives, votes, availability } = loaded.data;
  const publishedSources = Array.from(
    new Map(
      [...sessions, ...initiatives, ...votes].map((item) => [
        `${item.source.url}|${item.source.sha256 ?? ""}`,
        item.source,
      ]),
    ).values(),
  );
  const unavailableScopes = [
    !availability.sessions && "reuniões",
    !availability.initiatives && "iniciativas",
    !availability.votes && "votações",
  ].filter((scope): scope is string => Boolean(scope));

  return (
    <main className="page-shell shell parliament-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Assembleia da República · XVII Legislatura</span>
        <h1>Atividade parlamentar</h1>
        <p>
          Consulte reuniões associadas a votações, iniciativas e decisões tal como constam
          das fotografias oficiais revistas. Campos ausentes ficam vazios e posições coletivas
          nunca são atribuídas automaticamente a deputados.
        </p>
      </header>

      <DataModeBanner status={loaded.status} showingFallback={false} />

      {unavailableScopes.length ? (
        <aside className="parliament-endpoint-warning" role="alert">
          <strong>Consulta parcial.</strong>
          <span>
            A API não respondeu para {unavailableScopes.join(", ")}. As outras secções mantêm
            apenas os registos que conseguiram ser validados.
          </span>
        </aside>
      ) : null}

      <section className="parliament-proof card" aria-label="Proveniência das fotografias">
        <div>
          <span className="eyebrow">Fotografias publicadas</span>
          <strong>Arquivo e revisão humana obrigatórios</strong>
          <p>
            Uma nova recolha não substitui esta versão até ser revista. Correções criam uma
            fotografia adicional e preservam o histórico.
          </p>
        </div>
        {publishedSources.length ? (
          <div className="parliament-proof__source">
            {publishedSources.map((source) => (
              <div className="parliament-proof__source-item" key={`${source.url}-${source.sha256}`}>
                <SourceLink source={source} />
                {source.sha256 ? <code>SHA-256 {source.sha256}</code> : null}
              </div>
            ))}
          </div>
        ) : (
          <span className="coverage-chip">Sem fotografia aprovada</span>
        )}
      </section>

      <nav className="parliament-jump-nav" aria-label="Secções da atividade parlamentar">
        <a href="#sessoes"><strong>{sessions.length}</strong><span>Reuniões mostradas</span></a>
        <a href="#iniciativas"><strong>{initiatives.length}</strong><span>Iniciativas mostradas</span></a>
        <a href="#votacoes"><strong>{votes.length}</strong><span>Votações mostradas</span></a>
      </nav>

      <section className="parliament-section" id="sessoes">
        <div className="section-heading-row">
          <div><span className="eyebrow">Reuniões com votação</span><h2>Reuniões observadas</h2></div>
          <p>Não é uma agenda completa: mostra apenas reuniões referidas na fonte de iniciativas.</p>
        </div>
        {sessions.length ? (
          <div className="parliament-session-grid">
            {sessions.map((session) => (
              <article className="parliament-session-card card" key={session.id}>
                <span>{session.startsAt}</span>
                <h3>{session.title}</h3>
                <p>
                  {session.sessionNumber ? `Reunião ${session.sessionNumber}` : "Número não indicado"}
                  {session.endsAt ? ` · termina ${session.endsAt}` : ""}
                </p>
                <SourceLink source={session.source} compact />
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            label={
              availability.sessions
                ? "Ainda não existem reuniões aprovadas para publicação."
                : "Não foi possível consultar as reuniões neste momento."
            }
          />
        )}
      </section>

      <section className="parliament-section" id="iniciativas">
        <div className="section-heading-row">
          <div><span className="eyebrow">Processo legislativo</span><h2>Iniciativas</h2></div>
          <p>O estado só aparece quando está explícito na fonte.</p>
        </div>
        {initiatives.length ? (
          <div className="parliament-list">
            {initiatives.map((initiative) => (
              <article className="parliament-list-card card" key={initiative.id}>
                <div className="parliament-list-card__meta">
                  <span>{initiative.initiativeType}</span>
                  <span>{initiative.number}</span>
                  <span>{initiative.introducedAt ?? "Data não indicada"}</span>
                </div>
                <h3>{initiative.title}</h3>
                {initiative.description ? <p>{initiative.description}</p> : null}
                <div className="parliament-list-card__footer">
                  <span>{initiative.status ?? "Estado não indicado na fonte"}</span>
                  <a href={initiative.officialUrl} target="_blank" rel="noreferrer noopener">
                    Abrir iniciativa oficial
                  </a>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            label={
              availability.initiatives
                ? "Ainda não existem iniciativas aprovadas para publicação."
                : "Não foi possível consultar as iniciativas neste momento."
            }
          />
        )}
      </section>

      <section className="parliament-section" id="votacoes">
        <div className="section-heading-row">
          <div><span className="eyebrow">Decisões registadas</span><h2>Votações</h2></div>
          <p>“Não determinado” significa que a fonte não identifica inequivocamente o ator.</p>
        </div>
        {votes.length ? (
          <div className="parliament-list">
            {votes.map((vote) => (
              <article className="parliament-list-card parliament-vote-card card" key={vote.id}>
                <div className="parliament-list-card__meta">
                  <span>{vote.votedAt ?? "Data não indicada"}</span>
                  <span>{vote.initiativeNumber ?? "Sem iniciativa indicada"}</span>
                  <span>{vote.isNominal ? "Voto nominal" : "Posição coletiva ou indeterminada"}</span>
                </div>
                <h3>{vote.title}</h3>
                <strong className="parliament-vote-result">
                  {vote.result ?? "Resultado não indicado na fonte"}
                </strong>
                {vote.records.length ? (
                  <div className="parliament-position-list" aria-label="Posições registadas">
                    {vote.records.slice(0, 12).map((record) => (
                      <span key={`${record.actorType}-${record.actorLabel}`}>
                        <b>{record.actorLabel}</b>
                        {choiceLabels[record.choice]}
                      </span>
                    ))}
                    {vote.records.length > 12 ? (
                      <small>+ {vote.records.length - 12} posições nesta fotografia</small>
                    ) : null}
                  </div>
                ) : <p>Esta votação não inclui posições normalizáveis na fotografia publicada.</p>}
                <SourceLink source={vote.source} compact />
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            label={
              availability.votes
                ? "Ainda não existem votações aprovadas para publicação."
                : "Não foi possível consultar as votações neste momento."
            }
          />
        )}
      </section>
    </main>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="empty-state card">
      <strong>{label}</strong>
      <span>A recolha e a publicação são etapas independentes.</span>
    </div>
  );
}
