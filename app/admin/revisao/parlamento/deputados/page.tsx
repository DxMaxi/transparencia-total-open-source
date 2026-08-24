import Link from "next/link";
import { createPoliticianProfileProposal } from "../../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type PoliticianProfileEditorialCandidate,
  type PoliticianProfileEditorialCandidateList,
  type PoliticianProfilePeriod,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeZone: "Europe/Lisbon",
});

function boundedOffset(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "0", 10);
  return Number.isSafeInteger(parsed) && parsed >= 0 && parsed <= 10_000 ? parsed : 0;
}

function safeOfficialSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function pageHref({
  legislature,
  query,
  offset,
}: {
  legislature: string;
  query: string;
  offset: number;
}): string {
  const params = new URLSearchParams({ legislature, offset: String(offset) });
  if (query) params.set("q", query);
  return `/admin/revisao/parlamento/deputados?${params.toString()}`;
}

export default async function PoliticianProfileEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{
    legislature?: string;
    q?: string;
    offset?: string;
    erro?: string;
  }>;
}) {
  const input = await searchParams;
  const legislature = (input.legislature?.trim() || "XVII").slice(0, 20);
  const query = (input.q?.trim() || "").slice(0, 100);
  const offset = boundedOffset(input.offset);
  const limit = 20;
  const params = new URLSearchParams({
    legislature,
    limit: String(limit),
    offset: String(offset),
  });
  if (query.length >= 2) params.set("q", query);
  const catalogue = await editorialFetch<PoliticianProfileEditorialCandidateList>(
    `/parliament/deputies?${params.toString()}`,
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.28 · perfis por prova oficial</p>
          <h1>Observações de deputados para revisão</h1>
          <p>
            Compare cada ficha arquivada com os campos normalizados e envie apenas essa observação
            para a fila privada. Aprovar não cria nem publica uma pessoa ou um mandato.
          </p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao/parlamento/deputados/prontidao">
            Ver prontidão da fotografia
          </Link>
          <Link href="/admin/revisao/parlamento">Voltar às fotografias</Link>
        </div>
      </header>

      {input.erro ? (
        <p className="private-message private-message--error" role="alert">
          {input.erro}
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>DepId exato, sem correspondência de nomes</strong>
        <p>
          A pesquisa abaixo limita observações já separadas pela Assembleia. Nunca associa duas
          pessoas, partidos ou mandatos por nome semelhante, sigla ou texto livre.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Legislatura
          <input name="legislature" defaultValue={legislature} maxLength={20} required />
        </label>
        <label>
          Filtrar observações
          <input
            name="q"
            defaultValue={query}
            minLength={2}
            maxLength={100}
            placeholder="Nome observado ou DepId exato"
          />
        </label>
        <button className="button" type="submit">
          Consultar
        </button>
        <Link href="/admin/revisao/parlamento/deputados">Limpar</Link>
      </form>

      <p className="admin-form-help" aria-live="polite">
        {catalogue.total.toLocaleString("pt-PT")} observação(ões) privadas nesta consulta. {catalogue.search_rule}
      </p>

      {catalogue.items.length ? (
        <section className="parliament-snapshot-list" aria-label="Observações oficiais de deputados">
          {catalogue.items.map((candidate) => (
            <CandidateCard candidate={candidate} key={candidate.observation_id} />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem observações atestadas para estes filtros.</strong>
          <p>A ausência permanece dados indisponíveis; não prova omissão nem incumprimento.</p>
        </section>
      )}

      <nav className="admin-heading-actions" aria-label="Paginação das observações">
        {offset > 0 ? (
          <Link
            className="button"
            href={pageHref({ legislature, query, offset: Math.max(0, offset - limit) })}
          >
            Página anterior
          </Link>
        ) : null}
        {catalogue.next_offset !== null ? (
          <Link
            className="button"
            href={pageHref({ legislature, query, offset: catalogue.next_offset })}
          >
            Página seguinte
          </Link>
        ) : null}
      </nav>
    </div>
  );
}

function CandidateCard({ candidate }: { candidate: PoliticianProfileEditorialCandidate }) {
  const officialUrl = safeOfficialSourceUrl(candidate.source.url);
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">Legislatura {candidate.legislature}</p>
          <h2>{candidate.parliamentary_name}</h2>
          <p>{candidate.full_name ?? "Nome completo: dados indisponíveis"}</p>
        </div>
        <span
          className={`admin-state ${candidate.proposal_eligible ? "state-approved" : "state-rejected"}`}
        >
          {candidate.proposal_eligible ? "Prova confirmada" : "Proposta bloqueada"}
        </span>
      </header>

      <section className="parliament-proof-grid" aria-label="Identificadores e prova oficial">
        <dl>
          <div>
            <dt>DepId oficial</dt>
            <dd><code>{candidate.official_deputy_id}</code></dd>
          </div>
          <div>
            <dt>Círculo observado</dt>
            <dd>{candidate.constituency.label ?? "Dados indisponíveis"}</dd>
          </div>
          <div>
            <dt>Recolhida</dt>
            <dd>{dateFormatter.format(new Date(candidate.source.retrieved_at))}</dd>
          </div>
          <div>
            <dt>SHA-256 da fonte</dt>
            <dd><code>{candidate.source.content_sha256}</code></dd>
          </div>
          <div>
            <dt>SHA-256 da observação</dt>
            <dd><code>{candidate.observation_sha256}</code></dd>
          </div>
          <div>
            <dt>SHA-256 normalizado</dt>
            <dd><code>{candidate.snapshot.normalised_sha256}</code></dd>
          </div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Original privado atestado</strong>
          <span>{candidate.archive.byte_size.toLocaleString("pt-PT")} bytes</span>
          <span>{candidate.snapshot.parser_version}</span>
          {officialUrl ? (
            <a className="button" href={officialUrl} target="_blank" rel="noreferrer noopener">
              Abrir fonte oficial
            </a>
          ) : (
            <span>URL oficial indisponível</span>
          )}
        </div>
      </section>

      <section className="parliament-review-grid">
        <div>
          <p className="eyebrow">Grupos observados</p>
          <PeriodList
            empty="Dados indisponíveis"
            periods={candidate.parliamentary_groups}
            label={(period) => period.short_name}
          />
        </div>
        <div>
          <p className="eyebrow">Situações declaradas</p>
          <PeriodList
            empty="Dados indisponíveis"
            periods={candidate.mandate_situations}
            label={(period) => period.description}
          />
        </div>
        <div>
          <p className="eyebrow">Cargos observados</p>
          <PeriodList
            empty="Dados indisponíveis"
            periods={candidate.offices}
            label={(period) => period.title}
          />
        </div>
      </section>

      <details className="parliament-limitations">
        <summary>Limitações e anomalias preservadas</summary>
        <ul>
          {candidate.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      </details>

      {candidate.editorial_case ? (
        <section className="parliament-proposal-card parliament-proposal-card--existing">
          <p className="eyebrow">Perfil político</p>
          <h3>Processo já existente</h3>
          <p>
            {STATE_LABELS[candidate.editorial_case.state]} · revisão {candidate.editorial_case.revision}
          </p>
          <Link className="button" href={`/admin/revisao/${candidate.editorial_case.id}`}>
            Abrir processo
          </Link>
        </section>
      ) : (
        <form action={createPoliticianProfileProposal} className="parliament-proposal-card">
          <input type="hidden" name="observation_id" value={candidate.observation_id} />
          <input type="hidden" name="legislature" value={candidate.legislature} />
          <p className="eyebrow">Perfil político</p>
          <h3>Criar proposta PENDING</h3>
          <p>O servidor reconstrói a versão a partir da observação e do arquivo atestado.</p>
          <label className="admin-confirmation">
            <input name="confirm_private_only" type="checkbox" required />
            <span>Confirmo que esta proposta permanece privada.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_exact_official_id_only" type="checkbox" required />
            <span>Confirmo que a identidade se apoia apenas no DepId oficial exato.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_mandate_inference" type="checkbox" required />
            <span>Confirmo que esta observação não prova um mandato.</span>
          </label>
          <button
            className="button button--primary"
            type="submit"
            disabled={!candidate.proposal_eligible}
          >
            Enviar perfil para a fila privada
          </button>
        </form>
      )}
    </article>
  );
}

function PeriodList<T extends Omit<PoliticianProfilePeriod, "source_id">>({
  periods,
  label,
  empty,
}: {
  periods: T[];
  label: (period: T) => string;
  empty: string;
}) {
  if (!periods.length) return <p className="admin-form-help">{empty}</p>;
  return (
    <ul className="parliament-limitations">
      {periods.map((period, index) => (
        <li key={`${label(period)}-${index}`}>
          <strong>{label(period)}</strong>
          {" · "}
          {period.starts_at ? dateFormatter.format(new Date(period.starts_at)) : "início indisponível"}
          {" → "}
          {period.ends_at ? dateFormatter.format(new Date(period.ends_at)) : "fim indisponível"}
        </li>
      ))}
    </ul>
  );
}
