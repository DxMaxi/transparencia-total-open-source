import type { Metadata } from "next";
import Link from "next/link";
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

const SESSION_PAGE_SIZE = 24;
const INITIATIVE_PAGE_SIZE = 25;
const VOTE_PAGE_SIZE = 20;

const withdrawalReasonLabels: Record<string, string> = {
  EXTRACTION_OR_NORMALISATION_ERROR: "Erro de recolha ou normalização",
  SOURCE_DIVERGENCE: "Divergência com a fonte",
  OFFICIAL_SOURCE_CORRECTION: "Correção da fonte oficial",
  DUPLICATE_OR_CORRUPT_DATA: "Duplicação ou corrupção de dados",
  PROVEN_IDENTITY_ERROR: "Erro de identidade demonstrado",
  DOCUMENTED_METHODOLOGY_CHANGE: "Alteração metodológica documentada",
  LEGAL_OR_AUTHORITY_ORDER: "Obrigação legal ou decisão de autoridade",
  DATA_PROTECTION_OR_PERSONALITY_RIGHTS: "Proteção de dados ou direitos de personalidade",
  SECURITY_RISK: "Risco de segurança",
  THIRD_PARTY_RIGHTS: "Direitos de terceiros",
  DECLARED_SCOPE_ERROR: "Erro no âmbito declarado",
};

type PageSearchParams = Record<string, string | string[] | undefined>;

function readPage(value: string | string[] | undefined): number {
  const candidate = Array.isArray(value) ? value[0] : value;
  const parsed = Number.parseInt(candidate ?? "1", 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1;
}

function readableSessionTitle(title: string, sessionNumber?: string): string {
  const abbreviation = /^([A-Z]{2,6})\s+—\s+reunião\s+(.+)$/i.exec(title.trim());
  if (!abbreviation) return title;
  return `Reunião parlamentar ${sessionNumber ?? abbreviation[2]} (${abbreviation[1].toUpperCase()})`;
}

function resultTone(result?: string): "positive" | "negative" | "neutral" {
  if (!result) return "neutral";
  if (/rejeitad|chumbad|não aprovad/i.test(result)) return "negative";
  if (/aprova|adotad/i.test(result)) return "positive";
  return "neutral";
}

export default async function ParliamentActivityPage({
  searchParams,
}: {
  searchParams: Promise<PageSearchParams>;
}) {
  const params = await searchParams;
  const pages = {
    sessoes: readPage(params.sessoes),
    iniciativas: readPage(params.iniciativas),
    votacoes: readPage(params.votacoes),
  };
  const loaded = await loadPublicParliamentActivity("XVII", {
    sessions: {
      limit: SESSION_PAGE_SIZE,
      offset: (pages.sessoes - 1) * SESSION_PAGE_SIZE,
    },
    initiatives: {
      limit: INITIATIVE_PAGE_SIZE,
      offset: (pages.iniciativas - 1) * INITIATIVE_PAGE_SIZE,
    },
    votes: {
      limit: VOTE_PAGE_SIZE,
      offset: (pages.votacoes - 1) * VOTE_PAGE_SIZE,
    },
  });
  const { sessions, initiatives, votes, publicationHistory, availability } = loaded.data;
  const initiativesByNumber = new Map(
    initiatives.map((initiative) => [initiative.number.trim(), initiative]),
  );
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

      {!availability.publicationHistory ? (
        <aside className="parliament-endpoint-warning" role="status">
          <strong>Histórico temporariamente indisponível.</strong>
          <span>Os dados parlamentares mantêm a sua própria porta de publicação fail-closed.</span>
        </aside>
      ) : publicationHistory.length ? (
        <section className="parliament-publication-history card" aria-labelledby="publication-history-title">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Decisões públicas imutáveis</span>
              <h2 id="publication-history-title">Histórico de publicação e retirada</h2>
            </div>
            <p>Uma retirada nunca apaga a fotografia, os hashes ou o fundamento anterior.</p>
          </div>
          <ol>
            {publicationHistory.slice(0, 6).map((event) => (
              <li key={event.eventReferenceSha256}>
                <div>
                  <strong>{event.action === "PUBLISHED" ? "Publicado" : "Retirado"}</strong>
                  <span>{event.scopeLabel} · {event.decidedAt} · {event.actorAlias}</span>
                </div>
                {event.reasonCategory ? (
                  <span className="coverage-chip">
                    {withdrawalReasonLabels[event.reasonCategory] ?? event.reasonCategory}
                  </span>
                ) : null}
                <p>{event.publicRationale}</p>
                {event.publicEffect ? <p className="parliament-public-effect">{event.publicEffect.message}</p> : null}
                <div className="parliament-publication-history__proof">
                  <SourceLink source={event.source} compact />
                  <code>Evento {event.eventReferenceSha256}</code>
                  <code>Fotografia {event.snapshotSha256}</code>
                  {event.publicEffectSha256 ? <code>Efeito {event.publicEffectSha256}</code> : null}
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <nav className="parliament-jump-nav" aria-label="Secções da atividade parlamentar">
        <a href="#sessoes"><strong>{loaded.status.counts.parliamentSessions}</strong><span>reuniões publicadas</span></a>
        <a href="#iniciativas"><strong>{loaded.status.counts.parliamentInitiatives}</strong><span>iniciativas publicadas</span></a>
        <a href="#votacoes"><strong>{loaded.status.counts.parliamentVotes}</strong><span>votações publicadas</span></a>
      </nav>

      <section className="parliament-section" id="sessoes">
        <div className="section-heading-row">
          <div><span className="eyebrow">Reuniões com votação</span><h2>Reuniões observadas</h2></div>
          <p>Não é uma agenda completa: mostra apenas reuniões referidas na fonte de iniciativas.</p>
        </div>
        {sessions.length ? (
          <>
            <div className="parliament-session-grid">
              {sessions.map((session) => (
                <article className="parliament-session-card card" key={session.id}>
                  <span>{session.startsAt}</span>
                  <h3>{readableSessionTitle(session.title, session.sessionNumber)}</h3>
                  <p>
                    {session.sessionNumber ? `Reunião ${session.sessionNumber}` : "Número não indicado"}
                    {session.endsAt ? ` · termina ${session.endsAt}` : ""}
                  </p>
                  <SourceLink source={session.source} compact />
                </article>
              ))}
            </div>
            <Paginator
              anchor="sessoes"
              currentPage={pages.sessoes}
              pageSize={SESSION_PAGE_SIZE}
              pages={pages}
              param="sessoes"
              total={loaded.status.counts.parliamentSessions}
            />
          </>
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
          <>
            <div className="parliament-list">
              {initiatives.map((initiative) => (
                <article className="parliament-list-card card" key={initiative.id}>
                  <div className="parliament-list-card__meta">
                    <span>{initiative.initiativeType}</span>
                    <span>{initiative.number}</span>
                    <span>{initiative.introducedAt ?? "Entrada sem data explícita"}</span>
                  </div>
                  <h3>{initiative.title}</h3>
                  {initiative.description ? <p>{initiative.description}</p> : null}
                  <div className="parliament-list-card__footer">
                    <span>{initiative.status ? `Última fase registada: ${initiative.status}` : "Fase atual não indicada"}</span>
                    <a href={initiative.officialUrl} target="_blank" rel="noreferrer noopener">
                      Abrir iniciativa oficial
                    </a>
                  </div>
                </article>
              ))}
            </div>
            <Paginator
              anchor="iniciativas"
              currentPage={pages.iniciativas}
              pageSize={INITIATIVE_PAGE_SIZE}
              pages={pages}
              param="iniciativas"
              total={loaded.status.counts.parliamentInitiatives}
            />
          </>
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
          <>
            <div className="parliament-list">
              {votes.map((vote) => {
                const initiative = vote.initiativeNumber
                  ? initiativesByNumber.get(vote.initiativeNumber.trim())
                  : undefined;
                const numericTitle = /^\s*\d+(?:\/[A-Z0-9.ª-]+)*\s*$/i.test(vote.title);
                const title = numericTitle && initiative
                  ? `${initiative.initiativeType} n.º ${initiative.number} — ${initiative.title}`
                  : numericTitle
                    ? `Votação da iniciativa n.º ${vote.title.trim()}`
                    : vote.title;
                return (
                  <article className="parliament-list-card parliament-vote-card card" key={vote.id}>
                    <div className="parliament-list-card__meta">
                      <span>{vote.votedAt ?? "Data não indicada"}</span>
                      <span>{vote.initiativeNumber ?? "Sem iniciativa indicada"}</span>
                      <span>{vote.isNominal ? "Voto nominal" : "Posição coletiva ou indeterminada"}</span>
                    </div>
                    <h3>{title}</h3>
                    <strong className={`parliament-vote-result parliament-vote-result--${resultTone(vote.result)}`}>
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
                    ) : (
                      <p>Esta votação não inclui posições normalizáveis na fotografia publicada.</p>
                    )}
                    <SourceLink source={vote.source} compact />
                  </article>
                );
              })}
            </div>
            <Paginator
              anchor="votacoes"
              currentPage={pages.votacoes}
              pageSize={VOTE_PAGE_SIZE}
              pages={pages}
              param="votacoes"
              total={loaded.status.counts.parliamentVotes}
            />
          </>
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

function Paginator({
  anchor,
  currentPage,
  pageSize,
  pages,
  param,
  total,
}: {
  anchor: string;
  currentPage: number;
  pageSize: number;
  pages: Record<"sessoes" | "iniciativas" | "votacoes", number>;
  param: "sessoes" | "iniciativas" | "votacoes";
  total: number;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (pageCount === 1) return null;

  const hrefFor = (page: number) => {
    const query = new URLSearchParams();
    Object.entries({ ...pages, [param]: page }).forEach(([key, value]) => {
      if (value > 1) query.set(key, String(value));
    });
    const suffix = query.toString();
    return `${suffix ? `?${suffix}` : ""}#${anchor}`;
  };

  return (
    <nav className="parliament-pagination" aria-label={`Paginação de ${anchor}`}>
      {currentPage > 1 ? <Link href={hrefFor(currentPage - 1)}>Anterior</Link> : <span />}
      <strong>Página {Math.min(currentPage, pageCount)} de {pageCount}</strong>
      {currentPage < pageCount ? <Link href={hrefFor(currentPage + 1)}>Seguinte</Link> : <span />}
    </nav>
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
