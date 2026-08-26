import Link from "next/link";
import { createPoliticianOfficeProposal } from "../../../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type PoliticianOfficeEditorialCandidate,
  type PoliticianOfficeEditorialCandidateList,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeZone: "Europe/Lisbon",
});

function boundedOffset(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "0", 10);
  return Number.isSafeInteger(parsed) && parsed >= 0 && parsed <= 10_000 ? parsed : 0;
}

function formatDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value)) : "dados indisponíveis";
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
  return `/admin/revisao/parlamento/deputados/cargos?${params.toString()}`;
}

export default async function PoliticianOfficeEditorialPage({
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
  const catalogue = await editorialFetch<PoliticianOfficeEditorialCandidateList>(
    `/parliament/office-candidates?${params.toString()}`,
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.36 · cargos parlamentares observados</p>
          <h1>Preparar cargos para revisão humana</h1>
          <p>
            Cada linha conserva o CarId, o título e o intervalo fornecidos pela Assembleia. A
            proposta permanece privada e não cria cargo público, mandato, filiação ou conclusão
            jurídica.
          </p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao/parlamento/deputados/mandatos">Rever mandatos</Link>
          <Link href="/admin/revisao/parlamento/deputados">Voltar aos perfis</Link>
        </div>
      </header>

      {input.erro ? (
        <p className="private-message private-message--error" role="alert">
          {input.erro}
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Cargo observado não é mandato nem prova de competências atuais</strong>
        <p>
          Um candidato só avança com DepId e CarId exatos, identidade já publicada, círculo
          oficial, fonte arquivada e intervalo coerente. Um campo em falta fica como dados
          indisponíveis; nomes e siglas nunca completam identificadores.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Legislatura
          <input name="legislature" defaultValue={legislature} maxLength={20} required />
        </label>
        <label>
          Filtrar candidatos
          <input
            name="q"
            defaultValue={query}
            minLength={2}
            maxLength={100}
            placeholder="Título, nome observado ou DepId exato"
          />
        </label>
        <button className="button" type="submit">Consultar</button>
        <Link href="/admin/revisao/parlamento/deputados/cargos">Limpar</Link>
      </form>

      <p className="admin-form-help" aria-live="polite">
        {catalogue.total.toLocaleString("pt-PT")} cargo(s) observado(s) nesta consulta. {catalogue.search_rule}
      </p>

      {catalogue.items.length ? (
        <section className="parliament-snapshot-list" aria-label="Candidatos privados a cargo">
          {catalogue.items.map((candidate) => (
            <OfficeCandidateCard
              candidate={candidate}
              key={`${candidate.observation_id}-${candidate.source_period_sha256}`}
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem cargos oficiais para estes filtros.</strong>
          <p>A lacuna permanece dados indisponíveis e não prova ausência de funções.</p>
        </section>
      )}

      <nav className="admin-heading-actions" aria-label="Paginação dos candidatos a cargo">
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

function OfficeCandidateCard({ candidate }: { candidate: PoliticianOfficeEditorialCandidate }) {
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">Legislatura {candidate.legislature}</p>
          <h2>{candidate.source_office.title}</h2>
          <p>{candidate.parliamentary_name} · {candidate.full_name ?? "nome completo indisponível"}</p>
        </div>
        <span
          className={`admin-state ${candidate.proposal_eligible ? "state-approved" : "state-rejected"}`}
        >
          {candidate.proposal_eligible ? "Pronto para revisão" : "Candidato bloqueado"}
        </span>
      </header>

      <section className="parliament-proof-grid" aria-label="Prova do cargo oficial">
        <dl>
          <div><dt>DepId oficial</dt><dd><code>{candidate.official_deputy_id}</code></dd></div>
          <div><dt>CarId oficial</dt><dd><code>{candidate.source_office.source_id ?? "dados indisponíveis"}</code></dd></div>
          <div><dt>Início observado</dt><dd>{formatDate(candidate.source_office.starts_at)}</dd></div>
          <div><dt>Fim observado</dt><dd>{formatDate(candidate.source_office.ends_at)}</dd></div>
          <div><dt>Círculo</dt><dd>{candidate.constituency.label ?? "Dados indisponíveis"}</dd></div>
          <div><dt>ID do círculo</dt><dd><code>{candidate.constituency.source_id ?? "dados indisponíveis"}</code></dd></div>
          <div><dt>SHA-256 do período</dt><dd><code>{candidate.source_period_sha256}</code></dd></div>
          <div><dt>SHA-256 da fonte</dt><dd><code>{candidate.source.content_sha256}</code></dd></div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Arquivo oficial atestado</strong>
          <span>{candidate.archive.byte_size.toLocaleString("pt-PT")} bytes</span>
          <span>Recolha: {formatDate(candidate.source.retrieved_at)}</span>
          <a className="button" href={candidate.source.url} target="_blank" rel="noreferrer noopener">
            Abrir fonte oficial
          </a>
        </div>
      </section>

      {candidate.blocked_reasons.length ? (
        <section className="parliament-proposal-card">
          <p className="eyebrow">Prova insuficiente</p>
          <h3>Dados indisponíveis ou contraditórios</h3>
          <ul className="parliament-limitations">
            {candidate.blocked_reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </section>
      ) : null}

      {candidate.existing_case ? (
        <section className="parliament-proposal-card parliament-proposal-card--existing">
          <p className="eyebrow">Cargo observado</p>
          <h3>Processo privado já existente</h3>
          <p>
            {STATE_LABELS[candidate.existing_case.state]} · revisão {candidate.existing_case.revision}
          </p>
          <Link className="button" href={`/admin/revisao/${candidate.existing_case.id}`}>
            Abrir processo
          </Link>
        </section>
      ) : (
        <form action={createPoliticianOfficeProposal} className="parliament-proposal-card">
          <input type="hidden" name="observation_id" value={candidate.observation_id} />
          <input type="hidden" name="source_period_sha256" value={candidate.source_period_sha256} />
          <input type="hidden" name="legislature" value={candidate.legislature} />
          <p className="eyebrow">Cargo por período oficial</p>
          <h3>Criar proposta PENDING</h3>
          <p>Aprovar este processo continuará sem criar qualquer projeção pública.</p>
          <label className="admin-confirmation">
            <input name="confirm_private_only" type="checkbox" required />
            <span>Confirmo que esta proposta permanece privada.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_exact_official_ids_only" type="checkbox" required />
            <span>Confirmo o uso exclusivo dos DepId e CarId oficiais exatos.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_observed_period_requires_human_review" type="checkbox" required />
            <span>Confirmo que o intervalo observado exige revisão humana própria.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_mandate_or_party_inference" type="checkbox" required />
            <span>Confirmo que não será inferido mandato, filiação ou continuidade jurídica.</span>
          </label>
          <button
            className="button button--primary"
            type="submit"
            disabled={!candidate.proposal_eligible}
          >
            Enviar cargo para revisão privada
          </button>
        </form>
      )}
    </article>
  );
}
