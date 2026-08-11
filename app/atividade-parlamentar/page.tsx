import type { Metadata } from "next";
import Link from "next/link";
import { DataModeBanner } from "@/components/data-mode-banner";
import { SourceLink } from "@/components/source-link";
import {
  loadPublicParliamentExplorer,
  type PublicParliamentExplorerFilters,
} from "@/lib/public-data";
import type { PublicParliamentaryVote } from "@/types/public-data";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Atividade parlamentar",
  description:
    "Pesquise reuniões, iniciativas e votações da Assembleia da República com filtros, fonte, revisão e limitações visíveis.",
};

export const revalidate = 60;

const PAGE_SIZE = 20;

const choiceLabels = {
  FAVOR: "A favor",
  AGAINST: "Contra",
  ABSTENTION: "Abstenção",
  ABSENT: "Ausência",
  UNKNOWN: "Não determinado",
};

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

const kindLabels = {
  sessions: "Reuniões",
  initiatives: "Iniciativas",
  votes: "Votações",
};

type PageSearchParams = Record<string, string | string[] | undefined>;
type ExplorerKind = keyof typeof kindLabels;
type UrlState = {
  tipo: "sessoes" | "iniciativas" | "votacoes";
  legislatura: string;
  q?: string;
  de?: string;
  ate?: string;
  tipo_iniciativa?: string;
  estado_iniciativa?: string;
  resultado?: string;
  nominal?: "sim" | "nao";
  grupo?: string;
  posicao?: "FAVOR" | "AGAINST" | "ABSTENTION" | "ABSENT" | "UNKNOWN";
};

function readString(
  value: string | string[] | undefined,
  maxLength = 200,
): string | undefined {
  const candidate = (Array.isArray(value) ? value[0] : value)?.trim();
  return candidate ? candidate.slice(0, maxLength) : undefined;
}

function readPage(value: string | string[] | undefined): number {
  const parsed = Number.parseInt(readString(value, 8) ?? "1", 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? Math.min(parsed, 501) : 1;
}

function readDate(value: string | string[] | undefined): string | undefined {
  const candidate = readString(value, 10);
  return candidate && /^\d{4}-\d{2}-\d{2}$/.test(candidate) ? candidate : undefined;
}

function readKind(value: string | string[] | undefined): ExplorerKind {
  const candidate = readString(value, 20);
  if (candidate === "sessoes") return "sessions";
  if (candidate === "iniciativas") return "initiatives";
  return "votes";
}

function toUrlKind(kind: ExplorerKind): UrlState["tipo"] {
  if (kind === "sessions") return "sessoes";
  if (kind === "initiatives") return "iniciativas";
  return "votacoes";
}

function buildHref(state: UrlState, page = 1): string {
  const query = new URLSearchParams();
  Object.entries(state).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
  if (page > 1) query.set("pagina", String(page));
  return `/atividade-parlamentar?${query.toString()}#explorar`;
}

export default async function ParliamentActivityPage({
  searchParams,
}: {
  searchParams: Promise<PageSearchParams>;
}) {
  const params = await searchParams;
  const kind = readKind(params.tipo);
  const page = readPage(params.pagina);
  const legislature = readString(params.legislatura, 20) ?? "XVII";
  const query = readString(params.q, 120);
  const dateFrom = readDate(params.de);
  const dateTo = readDate(params.ate);
  const initiativeType = readString(params.tipo_iniciativa, 120);
  const initiativeStatus = readString(params.estado_iniciativa, 200);
  const voteResult = readString(params.resultado, 200);
  const requestedNominal = readString(params.nominal, 4);
  const nominalValue =
    requestedNominal === "sim" || requestedNominal === "nao" ? requestedNominal : undefined;
  const isNominal = nominalValue === "sim" ? true : nominalValue === "nao" ? false : undefined;
  const partySourceId = readString(params.grupo, 200);
  const choiceValue = readString(params.posicao, 20);
  const choice = ["FAVOR", "AGAINST", "ABSTENTION", "ABSENT", "UNKNOWN"].includes(
    choiceValue ?? "",
  )
    ? (choiceValue as PublicParliamentExplorerFilters["choice"])
    : undefined;
  const filters: PublicParliamentExplorerFilters = {
    kind,
    legislature,
    query,
    dateFrom,
    dateTo,
    initiativeType,
    initiativeStatus,
    voteResult,
    isNominal,
    partySourceId,
    choice,
    page,
    pageSize: PAGE_SIZE,
  };
  const loaded = await loadPublicParliamentExplorer(filters);
  const explorer = loaded.data;
  const urlState: UrlState = {
    tipo: toUrlKind(kind),
    legislatura: legislature,
    q: query,
    de: dateFrom,
    ate: dateTo,
    tipo_iniciativa: kind === "sessions" ? undefined : initiativeType,
    estado_iniciativa: kind === "initiatives" ? initiativeStatus : undefined,
    resultado: kind === "votes" ? voteResult : undefined,
    nominal: kind === "votes" ? (nominalValue as UrlState["nominal"]) : undefined,
    grupo: kind === "votes" ? partySourceId : undefined,
    posicao: kind === "votes" ? choice : undefined,
  };
  const pageCount = Math.max(1, Math.ceil(explorer.total / explorer.limit));
  if (explorer.availability.explorer && page > pageCount) {
    redirect(buildHref(urlState, pageCount));
  }
  const firstResult = explorer.total ? explorer.offset + 1 : 0;
  const lastResult = Math.min(explorer.offset + explorer.limit, explorer.total);
  const records = [...explorer.sessions, ...explorer.initiatives, ...explorer.votes];
  const publishedSources = Array.from(
    new Map(
      [...records.map((item) => item.source), ...explorer.publicationHistory.map((item) => item.source)]
        .map((source) => [`${source.url}|${source.sha256 ?? ""}`, source]),
    ).values(),
  );
  const advancedFiltersActive = Boolean(
    dateFrom
      || dateTo
      || initiativeType
      || initiativeStatus
      || voteResult
      || nominalValue
      || partySourceId
      || choice,
  );
  const invalidDateRange = Boolean(dateFrom && dateTo && dateFrom > dateTo);

  return (
    <main className="page-shell shell parliament-page">
      <header className="page-heading page-heading--wide">
        <span className="eyebrow">Assembleia da República · dados oficiais publicados</span>
        <h1>Atividade parlamentar, sem labirintos</h1>
        <p>
          Pesquise uma decisão, filtre a fotografia oficial e confirme a fonte. Posições
          coletivas nunca são atribuídas automaticamente a deputados e uma votação não prova,
          por si só, entrada em vigor ou impacto no cidadão.
        </p>
      </header>

      <DataModeBanner status={loaded.status} showingFallback={false} />

      {invalidDateRange ? (
        <aside className="parliament-endpoint-warning" role="alert">
          <strong>Intervalo de datas inválido.</strong>
          <span>A data inicial não pode ser posterior à data final.</span>
        </aside>
      ) : !explorer.availability.explorer ? (
        <aside className="parliament-endpoint-warning" role="alert">
          <strong>Consulta temporariamente indisponível.</strong>
          <span>Não apresentamos listas antigas nem informação não oficial como substituição.</span>
        </aside>
      ) : null}

      <nav className="parliament-jump-nav" aria-label="Tipos de atividade parlamentar">
        <Link
          aria-current={kind === "sessions" ? "page" : undefined}
          href={buildHref({ tipo: "sessoes", legislatura: legislature })}
        >
          <strong>{loaded.status.counts.parliamentSessions}</strong><span>reuniões</span>
        </Link>
        <Link
          aria-current={kind === "initiatives" ? "page" : undefined}
          href={buildHref({ tipo: "iniciativas", legislatura: legislature })}
        >
          <strong>{loaded.status.counts.parliamentInitiatives}</strong><span>iniciativas</span>
        </Link>
        <Link
          aria-current={kind === "votes" ? "page" : undefined}
          href={buildHref({ tipo: "votacoes", legislatura: legislature })}
        >
          <strong>{loaded.status.counts.parliamentVotes}</strong><span>votações</span>
        </Link>
      </nav>

      <section className="parliament-explorer card" id="explorar" aria-labelledby="explorer-title">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Pesquisa na fotografia revista</span>
            <h2 id="explorer-title">Encontrar e compreender</h2>
          </div>
          <p>Os filtros não alteram dados: limitam apenas a consulta pública aprovada.</p>
        </div>

        <form action="/atividade-parlamentar#explorar" method="get" className="parliament-search-form">
          <label className="parliament-search-form__query">
            <span>Pesquisar por título, número ou identificador oficial</span>
            <input
              defaultValue={query}
              maxLength={120}
              name="q"
              placeholder="Ex.: habitação, 815/XVII ou identificador"
              type="search"
            />
          </label>
          <label>
            <span>Consultar</span>
            <select defaultValue={toUrlKind(kind)} name="tipo">
              <option value="votacoes">Votações</option>
              <option value="iniciativas">Iniciativas</option>
              <option value="sessoes">Reuniões observadas</option>
            </select>
          </label>
          <label>
            <span>Legislatura</span>
            <select defaultValue={legislature} name="legislatura">
              {!explorer.facets.legislatures.includes(legislature) ? (
                <option value={legislature}>{legislature} · sem fotografia disponível</option>
              ) : null}
              {explorer.facets.legislatures.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          <button className="button button--primary" type="submit">Pesquisar</button>

          <details className="parliament-advanced-filters" open={advancedFiltersActive}>
            <summary>Filtros adicionais</summary>
            <div>
              <label><span>Desde</span><input defaultValue={dateFrom} name="de" type="date" /></label>
              <label><span>Até</span><input defaultValue={dateTo} name="ate" type="date" /></label>
              <label>
                <span>Tipo de iniciativa</span>
                <select defaultValue={initiativeType ?? ""} disabled={kind === "sessions"} name="tipo_iniciativa">
                  <option value="">Todos os tipos</option>
                  {initiativeType && !explorer.facets.initiativeTypes.some((item) => item.value === initiativeType) ? (
                    <option value={initiativeType}>{initiativeType} · não disponível</option>
                  ) : null}
                  {explorer.facets.initiativeTypes.map((item) => (
                    <option key={item.value} value={item.value}>{item.label} ({item.count})</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Fase da iniciativa</span>
                <select defaultValue={initiativeStatus ?? ""} disabled={kind !== "initiatives"} name="estado_iniciativa">
                  <option value="">Todas as fases indicadas</option>
                  {initiativeStatus && !explorer.facets.initiativeStatuses.some((item) => item.value === initiativeStatus) ? (
                    <option value={initiativeStatus}>{initiativeStatus} · não disponível</option>
                  ) : null}
                  {explorer.facets.initiativeStatuses.map((item) => (
                    <option key={item.value} value={item.value}>{item.label} ({item.count})</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Resultado registado</span>
                <select defaultValue={voteResult ?? ""} disabled={kind !== "votes"} name="resultado">
                  <option value="">Todos os resultados</option>
                  {voteResult && !explorer.facets.voteResults.some((item) => item.value === voteResult) ? (
                    <option value={voteResult}>{voteResult} · não disponível</option>
                  ) : null}
                  {explorer.facets.voteResults.map((item) => (
                    <option key={item.value} value={item.value}>{item.label} ({item.count})</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Grupo com ID oficial</span>
                <select
                  defaultValue={partySourceId ?? ""}
                  disabled={kind !== "votes" || !explorer.facets.parties.length}
                  name="grupo"
                >
                  <option value="">
                    {explorer.facets.parties.length
                      ? "Todos os grupos com ID oficial"
                      : "Dados indisponíveis — sem IDs oficiais"}
                  </option>
                  {partySourceId && !explorer.facets.parties.some((item) => item.value === partySourceId) ? (
                    <option value={partySourceId}>ID indicado · sem correspondência exata</option>
                  ) : null}
                  {explorer.facets.parties.map((item) => (
                    <option key={item.value} value={item.value}>{item.label} ({item.count})</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Natureza da posição</span>
                <select defaultValue={nominalValue ?? ""} disabled={kind !== "votes"} name="nominal">
                  <option value="">Nominal, coletiva ou indeterminada</option>
                  <option value="sim">Apenas votações nominais</option>
                  <option value="nao">Apenas não nominais</option>
                </select>
              </label>
              <label>
                <span>Posição registada</span>
                <select defaultValue={choice ?? ""} disabled={kind !== "votes"} name="posicao">
                  <option value="">Todas as posições</option>
                  {Object.entries(choiceLabels).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
            </div>
          </details>
        </form>

        <div className="parliament-filter-evidence">
          <div>
            <strong>Temas: dados indisponíveis</strong>
            <span>{explorer.facets.topicsNote}</span>
            <span>
              O filtro por grupo só é ativado quando a fonte fornece um identificador oficial
              inequívoco; uma sigla isolada não cria essa associação.
            </span>
            <span>
              Consulta parcial: a lista de reuniões contém apenas observações desta fonte e não é
              uma agenda completa da Assembleia da República.
            </span>
          </div>
          <Link href={buildHref({ tipo: toUrlKind(kind), legislatura: legislature })}>
            Limpar filtros
          </Link>
        </div>
      </section>

      <section className="parliament-proof card" aria-label="Proveniência das fotografias">
        <div>
          <span className="eyebrow">Proveniência</span>
          <strong>Arquivo, SHA-256 e revisão humana obrigatórios</strong>
          <p>
            Uma nova recolha não substitui esta versão até ser revista. Correções acrescentam
            uma fotografia e preservam o histórico anterior.
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
          <span className="coverage-chip">Dados indisponíveis</span>
        )}
      </section>

      <section className="parliament-section parliament-results" aria-labelledby="results-title">
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">{kindLabels[kind]} · {legislature}</span>
            <h2 id="results-title">{explorer.total} resultados na fotografia publicada</h2>
          </div>
          <p>
            {explorer.total
              ? `A mostrar ${firstResult}–${lastResult}.`
              : "Nenhum registo corresponde aos filtros escolhidos."}
          </p>
        </div>

        <p className="parliament-explanation-rule">{explorer.explanationRule}</p>

        {kind === "sessions" && explorer.sessions.length ? (
          <div className="parliament-session-grid">
            {explorer.sessions.map((session) => (
              <article className="parliament-session-card card" key={session.id}>
                <span>{session.startsAt}</span>
                <h3>{session.title}</h3>
                <p>
                  {session.sessionNumber ? `Reunião ${session.sessionNumber}` : "Número não indicado"}
                  {session.endsAt ? ` · termina ${session.endsAt}` : ""}
                </p>
                <small>Observada porque é referida na fonte; não representa uma agenda completa.</small>
                <SourceLink source={session.source} compact />
              </article>
            ))}
          </div>
        ) : null}

        {kind === "initiatives" && explorer.initiatives.length ? (
          <div className="parliament-list">
            {explorer.initiatives.map((initiative) => (
              <article className="parliament-list-card card" key={initiative.id}>
                <div className="parliament-list-card__meta">
                  <span>{initiative.initiativeType}</span>
                  <span>{initiative.number}</span>
                  <span>{initiative.introducedAt ?? "Entrada sem data explícita"}</span>
                </div>
                <h3>{initiative.title}</h3>
                {initiative.description ? <p>{initiative.description}</p> : null}
                <details className="parliament-explainer">
                  <summary>O que esta iniciativa permite concluir</summary>
                  <p>
                    A fonte identifica o tipo e a fase indicada abaixo. A fase não permite, por
                    si só, concluir aprovação, entrada em vigor, execução ou impacto no cidadão.
                  </p>
                  <dl>
                    <div><dt>Tipo oficial</dt><dd>{initiative.initiativeType}</dd></div>
                    <div><dt>Fase indicada</dt><dd>{initiative.status ?? "Dados indisponíveis"}</dd></div>
                  </dl>
                </details>
                <div className="parliament-list-card__footer">
                  <span>{initiative.status ? `Última fase registada: ${initiative.status}` : "Fase atual não indicada"}</span>
                  <a href={initiative.officialUrl} target="_blank" rel="noreferrer noopener">
                    Abrir iniciativa oficial
                  </a>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {kind === "votes" && explorer.votes.length ? (
          <div className="parliament-list">
            {explorer.votes.map((vote) => <VoteCard key={vote.id} vote={vote} />)}
          </div>
        ) : null}

        {!records.length ? (
          <div className="empty-state card">
            <strong>{explorer.availability.explorer ? "Sem resultados para estes filtros" : "Dados indisponíveis"}</strong>
            <span>
              {explorer.availability.explorer
                ? "Altere ou limpe os filtros. A ausência de resultados não significa incumprimento."
                : "A recolha e a publicação são etapas independentes."}
            </span>
          </div>
        ) : null}

        <Paginator currentPage={page} pageCount={pageCount} state={urlState} />
      </section>

      {!explorer.availability.publicationHistory ? (
        <aside className="parliament-endpoint-warning" role="status">
          <strong>Histórico temporariamente indisponível.</strong>
          <span>Os dados parlamentares mantêm a sua própria porta de publicação fail-closed.</span>
        </aside>
      ) : explorer.publicationHistory.length ? (
        <section className="parliament-publication-history card" aria-labelledby="publication-history-title">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Decisões públicas imutáveis</span>
              <h2 id="publication-history-title">Histórico de publicação e retirada</h2>
            </div>
            <p>Uma retirada nunca apaga a fotografia, os hashes ou o fundamento anterior.</p>
          </div>
          <ol>
            {explorer.publicationHistory.slice(0, 6).map((event) => (
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
    </main>
  );
}

function VoteCard({ vote }: { vote: PublicParliamentaryVote }) {
  return (
    <article className="parliament-list-card parliament-vote-card card">
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
        <ul className="parliament-position-list" aria-label="Posições registadas">
          {vote.records.slice(0, 20).map((record) => (
            <li key={`${record.actorType}-${record.actorLabel}-${record.choice}`}>
              <b>{record.actorLabel}</b>
              {choiceLabels[record.choice]}
              <small>
                {record.partySourceId || record.personSourceId ? "ID oficial" : "Sem ID oficial"}
              </small>
            </li>
          ))}
          {vote.records.length > 20 ? (
            <li className="parliament-position-list__remainder">
              + {vote.records.length - 20} posições confirmáveis na fonte oficial
            </li>
          ) : null}
        </ul>
      ) : (
        <p>Esta votação não inclui posições normalizáveis na fotografia publicada.</p>
      )}
      <details className="parliament-explainer">
        <summary>O que esta votação permite concluir</summary>
        <p>
          A fotografia regista o resultado abaixo. Sem diploma, decisão ou prova oficial
          adicional, não é possível determinar entrada em vigor, execução ou impacto material.
        </p>
        <dl>
          <div><dt>Resultado registado</dt><dd>{vote.result ?? "Dados indisponíveis"}</dd></div>
          <div><dt>Tipo da iniciativa</dt><dd>{vote.initiativeType ?? "Dados indisponíveis"}</dd></div>
          <div><dt>Fase indicada</dt><dd>{vote.initiativeStatus ?? "Dados indisponíveis"}</dd></div>
        </dl>
        {vote.initiativeOfficialUrl ? (
          <a href={vote.initiativeOfficialUrl} target="_blank" rel="noreferrer noopener">
            Confirmar a iniciativa oficial associada
          </a>
        ) : (
          <span>Ligação oficial inequívoca à iniciativa: dados indisponíveis.</span>
        )}
      </details>
      <SourceLink source={vote.source} compact />
    </article>
  );
}

function Paginator({
  currentPage,
  pageCount,
  state,
}: {
  currentPage: number;
  pageCount: number;
  state: UrlState;
}) {
  if (pageCount === 1 && currentPage === 1) return null;
  return (
    <nav className="parliament-pagination" aria-label="Paginação dos resultados">
      {currentPage > 1 ? <Link href={buildHref(state, currentPage - 1)}>Anterior</Link> : <span />}
      <strong>Página {Math.min(currentPage, pageCount)} de {pageCount}</strong>
      {currentPage < pageCount ? <Link href={buildHref(state, currentPage + 1)}>Seguinte</Link> : <span />}
    </nav>
  );
}
