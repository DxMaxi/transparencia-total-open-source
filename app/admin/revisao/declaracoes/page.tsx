import Link from "next/link";
import { createEptPublicInterestProposal } from "../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type EptPublicInterestEditorialCandidate,
  type EptPublicInterestEditorialCandidateList,
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

function pageHref(query: string, offset: number): string {
  const params = new URLSearchParams({ offset: String(offset) });
  if (query) params.set("q", query);
  return `/admin/revisao/declaracoes?${params.toString()}`;
}

export default async function EptDeclarationEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; offset?: string; erro?: string }>;
}) {
  const input = await searchParams;
  const query = (input.q?.trim() || "").slice(0, 100);
  const offset = boundedOffset(input.offset);
  const limit = 20;
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query.length >= 2) params.set("q", query);
  const catalogue = await editorialFetch<EptPublicInterestEditorialCandidateList>(
    `/ept/public-interest-candidates?${params.toString()}`,
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.46 · EPT com âmbito jurídico fechado</p>
          <h1>Rever registos públicos de interesses</h1>
          <p>
            Esta área recebe apenas metadados de uma prova individual já arquivada. Não recebe
            rendimentos, património, moradas, contactos nem o conteúdo de consulta condicionada.
          </p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao">Voltar à fila editorial</Link>
          <a
            href="https://www.tribunalconstitucional.pt/tc/ept/"
            target="_blank"
            rel="noreferrer noopener"
          >
            Abrir portal institucional EPT
          </a>
        </div>
      </header>

      {input.erro ? (
        <p className="private-message private-message--error" role="alert">
          {input.erro}
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>O portal geral não prova uma declaração individual</strong>
        <p>
          Uma proposta só aparece depois de existir URL oficial individual, identificador exato,
          data de recolha, SHA-256 e arquivo atestado. O nome é apenas texto de consulta: nunca é
          usado para ligar a observação a um perfil político.
        </p>
      </aside>

      <aside className="admin-private-warning">
        <strong>Revisão jurídica independente continua obrigatória</strong>
        <p>
          A aprovação editorial não autoriza uma publicação. A ligação de identidade e qualquer
          projeção pública terão portas separadas; sem prova inequívoca, o resultado correto é
          dados indisponíveis.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Filtrar observações privadas
          <input
            name="q"
            defaultValue={query}
            minLength={2}
            maxLength={100}
            placeholder="Identificador da declaração ou nome publicado"
          />
        </label>
        <button className="button" type="submit">Consultar</button>
        <Link href="/admin/revisao/declaracoes">Limpar</Link>
      </form>

      <p className="admin-form-help" aria-live="polite">
        {catalogue.total.toLocaleString("pt-PT")} observação(ões) nesta consulta. {catalogue.search_rule}
      </p>
      <p className="admin-form-help">{catalogue.legal_scope}</p>

      {catalogue.items.length ? (
        <section className="parliament-snapshot-list" aria-label="Observações privadas EPT">
          {catalogue.items.map((candidate) => (
            <EptCandidateCard candidate={candidate} key={candidate.observation_id} />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem observações individuais com estes filtros.</strong>
          <p>
            Isto significa dados indisponíveis no circuito autorizado; não significa ausência de
            declaração, incumprimento ou ocultação pelo titular.
          </p>
        </section>
      )}

      <nav className="admin-heading-actions" aria-label="Paginação das observações EPT">
        {offset > 0 ? (
          <Link className="button" href={pageHref(query, Math.max(0, offset - limit))}>
            Página anterior
          </Link>
        ) : null}
        {catalogue.next_offset !== null ? (
          <Link className="button" href={pageHref(query, catalogue.next_offset)}>
            Página seguinte
          </Link>
        ) : null}
      </nav>
    </div>
  );
}

function EptCandidateCard({ candidate }: { candidate: EptPublicInterestEditorialCandidate }) {
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">Registo público de interesses</p>
          <h2>{candidate.public_subject_name}</h2>
          <p>Declaração oficial {candidate.official_declaration_id}</p>
        </div>
        <span
          className={`admin-state ${candidate.proposal_eligible ? "state-approved" : "state-rejected"}`}
        >
          {candidate.proposal_eligible ? "Pronta para revisão privada" : "Proposta bloqueada"}
        </span>
      </header>

      <section className="parliament-proof-grid" aria-label="Prova oficial EPT">
        <dl>
          <div><dt>Data declarada</dt><dd>{formatDate(candidate.declared_at)}</dd></div>
          <div><dt>Período</dt><dd>{candidate.period_label ?? "dados indisponíveis"}</dd></div>
          <div><dt>Recolhida</dt><dd>{formatDate(candidate.source.retrieved_at)}</dd></div>
          <div><dt>SHA-256 da fonte</dt><dd><code>{candidate.source.content_sha256}</code></dd></div>
          <div><dt>SHA-256 do registo</dt><dd><code>{candidate.source_record_sha256}</code></dd></div>
          <div>
            <dt>Referência protegida</dt>
            <dd><code>{candidate.official_subject_reference_sha256.slice(0, 16)}…</code></dd>
          </div>
          <div><dt>Ligação de identidade</dt><dd>Não criada</dd></div>
          <div><dt>Revisão jurídica</dt><dd>Pendente e independente</dd></div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Arquivo oficial atestado</strong>
          <span>
            {candidate.archive
              ? `${candidate.archive.byte_size.toLocaleString("pt-PT")} bytes`
              : "dados indisponíveis"}
          </span>
          <a
            className="button"
            href={candidate.source.url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Abrir prova oficial individual
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
          <p className="eyebrow">Processo editorial</p>
          <h3>Proposta já existente</h3>
          <p>
            {STATE_LABELS[candidate.existing_case.state]} · revisão {candidate.existing_case.revision}
          </p>
          <Link className="button" href={`/admin/revisao/${candidate.existing_case.id}`}>
            Abrir processo
          </Link>
        </section>
      ) : (
        <form action={createEptPublicInterestProposal} className="parliament-proposal-card">
          <input type="hidden" name="observation_id" value={candidate.observation_id} />
          <input
            type="hidden"
            name="source_record_sha256"
            value={candidate.source_record_sha256}
          />
          <p className="eyebrow">Revisão humana e jurídica</p>
          <h3>Criar proposta PENDING</h3>
          <p>A proposta continua privada e não cria declaração pública nem ligação ao perfil.</p>
          <label className="admin-confirmation">
            <input name="confirm_private_only" type="checkbox" required />
            <span>Confirmo que esta proposta permanece exclusivamente privada.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_public_interest_register_only" type="checkbox" required />
            <span>Confirmei que a prova se limita ao registo público de interesses.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_income_or_asset_content" type="checkbox" required />
            <span>Não existem rendimentos, património ou conteúdo de consulta condicionada.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_name_matching" type="checkbox" required />
            <span>O nome não será usado para associar esta observação a uma pessoa.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_identity_unlinked" type="checkbox" required />
            <span>Confirmo que a identidade continua sem ligação pública.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_independent_legal_review_required" type="checkbox" required />
            <span>Confirmo que qualquer publicação exige revisão jurídica independente.</span>
          </label>
          <button
            className="button button--primary"
            type="submit"
            disabled={!candidate.proposal_eligible}
          >
            Enviar metadados para revisão privada
          </button>
        </form>
      )}
    </article>
  );
}
