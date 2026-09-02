import Link from "next/link";
import { createBaseOrganisationIdentityProposal } from "../actions";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type BaseOrganisationIdentityCandidate,
  type BaseOrganisationIdentityCandidateList,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

const kindLabels: Record<BaseOrganisationIdentityCandidate["kind"], string> = {
  PUBLIC_BODY: "Entidade pública",
  COMPANY: "Empresa",
  NON_PROFIT: "Entidade sem fins lucrativos",
  EUROPEAN_BODY: "Entidade europeia",
  OTHER: "Outra organização",
};

const errorMessages: Record<string, string> = {
  "confirmacao-em-falta": "Confirme os três limites da proposta antes de a enviar.",
  "prova-invalidada": "A prova mudou ou já não permite esta operação. Consulte novamente a observação.",
  "proposta-nao-criada": "Não foi possível concluir a operação. Consulte novamente a fila antes de repetir.",
};

function safeSearchQuery(value: unknown): string | null {
  if (value === undefined || value === "") return "";
  if (typeof value !== "string" || value.length > 100) return null;
  const query = value.normalize("NFKC").trim();
  // Reject protected identifiers before either forwarding or reflecting input.
  const decimalDigits = query.match(/\p{Nd}/gu) ?? [];
  const compactQuery = query.replace(/[^\p{L}\p{N}]/gu, "");
  if (decimalDigits.length >= 9 || /[0-9a-f]{32,}/i.test(compactQuery)) return null;
  if (/[\p{Cc}\p{Cf}]/u.test(query) || (query.length > 0 && query.length < 2)) return null;
  return query;
}

function boundedOffset(value: unknown): number {
  if (typeof value !== "string" || !/^\d{1,5}$/.test(value)) return 0;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed <= 10_000 ? parsed : 0;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "dados indisponíveis" : dateFormatter.format(date);
}

function pageHref(query: string, offset: number): string {
  return `/admin/revisao/organizacoes?${new URLSearchParams({ q: query, offset: String(offset) })}`;
}

export default async function OrganisationIdentityEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[]; offset?: string | string[]; erro?: string | string[] }>;
}) {
  await getEditorialContext();
  const input = await searchParams;
  const safeQuery = safeSearchQuery(input.q);
  const query = safeQuery ?? "";
  const offset = safeQuery === null ? 0 : boundedOffset(input.offset);
  const limit = 20;
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query) params.set("q", query);
  let catalogue: BaseOrganisationIdentityCandidateList | null = null;
  let unavailable = false;
  if (safeQuery !== null) {
    try {
      catalogue = await editorialFetch<BaseOrganisationIdentityCandidateList>(
        `/base/organisation-identity-candidates?${params.toString()}`,
      );
    } catch {
      unavailable = true;
    }
  }
  const errorMessage = typeof input.erro === "string" && Object.hasOwn(errorMessages, input.erro)
    ? errorMessages[input.erro] ?? null
    : null;
  const nextOffset = catalogue && offset + catalogue.limit < catalogue.total
    ? offset + catalogue.limit
    : null;

  return (
    <div className="admin-page parliament-editorial-page base-contract-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.52 · Provas de identidade independentes</p>
          <h1>Rever identidades de organizações</h1>
          <p>Consulte a prova oficial arquivada e proponha a sua revisão. Este circuito é exclusivamente privado.</p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao">Voltar à fila editorial</Link>
          <a href="https://registo.justica.gov.pt/Empresas/Publicacoes" target="_blank" rel="noreferrer noopener">
            Conhecer o serviço oficial do IRN
          </a>
        </div>
      </header>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Denominação ou referência do ato oficial
          <input name="q" type="search" defaultValue={query} minLength={2} maxLength={100}
            placeholder="Nome da organização ou referência não fiscal" aria-describedby="identity-search-help" />
        </label>
        <button className="button" type="submit">Consultar provas privadas</button>
        <Link href="/admin/revisao/organizacoes">Limpar</Link>
      </form>
      <p id="identity-search-help" className="admin-form-help">
        Não introduza NIPC, NIF ou identificadores protegidos. A pesquisa apenas localiza observações;
        não estabelece correspondências nem liga organizações pelo nome.
      </p>

      {safeQuery === null ? (
        <p className="private-message private-message--error" role="alert">
          Pesquisa não aceite. Utilize entre 2 e 100 caracteres, sem identificadores fiscais ou protegidos.
          O valor recebido não é repetido nem enviado à consulta editorial.
        </p>
      ) : null}
      {errorMessage ? <p className="private-message private-message--error" role="alert">{errorMessage}</p> : null}
      {unavailable ? (
        <p className="private-message private-message--error" role="alert">
          Consulta privada temporariamente indisponível. Não é possível confirmar as observações neste momento.
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Um contrato não prova, por si só, a identidade de uma organização</strong>
        <p>
          Cada observação exige um ato individual do registo oficial do IRN, independente do Portal BASE,
          com data de recolha, SHA-256 e arquivo atestado. O portal ou a página de pesquisa não substituem
          a prova individual. A identidade fiscal fica protegida no servidor e não é enviada ao navegador.
        </p>
        <p>
          Mesmo depois de aprovada, esta prova não publica organizações, partes de contratos,
          correspondências ou relações. Corrigir exige nova observação; o histórico é conservado.
        </p>
      </aside>

      {catalogue ? (
        <>
          <p className="admin-form-help">{catalogue.search_rule} {catalogue.coverage_rule}</p>
          {catalogue.filter_required ? (
            <section className="admin-empty-state">
              <strong>Indique uma denominação ou referência para começar.</strong>
              <p>As observações são privadas e consultadas de forma limitada.</p>
            </section>
          ) : catalogue.items.length ? (
            <section className="parliament-snapshot-list" aria-label="Provas privadas de identidade">
              <p className="admin-form-help" aria-live="polite">{catalogue.total.toLocaleString("pt-PT")} observação(ões) nesta consulta.</p>
              {catalogue.items.map((candidate) => <IdentityCandidateCard candidate={candidate} key={candidate.observation_id} />)}
            </section>
          ) : (
            <section className="admin-empty-state">
              <strong>Dados indisponíveis com estes filtros.</strong>
              <p>Não encontrar uma observação não demonstra inexistência, irregularidade ou incumprimento.</p>
            </section>
          )}
          <nav className="admin-heading-actions" aria-label="Paginação das provas de identidade">
            {offset > 0 ? <Link className="button" href={pageHref(query, Math.max(0, offset - limit))}>Página anterior</Link> : null}
            {nextOffset !== null && nextOffset <= 10_000 ? <Link className="button" href={pageHref(query, nextOffset)}>Página seguinte</Link> : null}
          </nav>
        </>
      ) : null}
    </div>
  );
}

function IdentityCandidateCard({ candidate }: { candidate: BaseOrganisationIdentityCandidate }) {
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">{kindLabels[candidate.kind]}</p>
          <h2>{candidate.legal_name}</h2>
          <p>Referência do ato: {candidate.registry_record_id}</p>
        </div>
        <span className={`admin-state ${candidate.proposal_eligible ? "state-approved" : "state-pending"}`}>
          {candidate.existing_case ? STATE_LABELS[candidate.existing_case.state] : candidate.proposal_eligible ? "Pronta para proposta privada" : "Proposta bloqueada"}
        </span>
      </header>
      <section className="parliament-proof-grid" aria-label="Prova oficial independente">
        <dl>
          <div><dt>Fonte</dt><dd>{candidate.source.title}</dd></div>
          <div><dt>Recolhida</dt><dd>{formatDate(candidate.source.retrieved_at)}</dd></div>
          <div><dt>SHA-256 da fonte</dt><dd><code>{candidate.source.content_sha256}</code></dd></div>
          <div><dt>SHA-256 do registo não fiscal</dt><dd><code>{candidate.source_record_sha256}</code></dd></div>
          <div><dt>Identificador fiscal</dt><dd>Protegido; não disponível neste painel</dd></div>
          <div><dt>Ligação a contratos ou relações</dt><dd>Não criada</dd></div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Arquivo oficial atestado</strong>
          {candidate.archive ? (
            <>
              <span>{candidate.archive.byte_size.toLocaleString("pt-PT")} bytes · {formatDate(candidate.archive.archived_at)}</span>
              <code>{candidate.archive.attestation_sha256}</code>
            </>
          ) : <span>dados indisponíveis</span>}
          <a className="button" href={candidate.source.url} target="_blank" rel="noreferrer noopener">Abrir serviço de prova oficial</a>
          <small>O serviço do IRN pode exigir nova pesquisa. Confirme o ato e o SHA-256 do arquivo, não apenas o endereço.</small>
        </div>
      </section>
      {candidate.blocked_reasons.length ? (
        <section className="parliament-proposal-card">
          <h3>Prova insuficiente para propor revisão</h3>
          <ul className="parliament-limitations">{candidate.blocked_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </section>
      ) : null}
      {candidate.existing_case ? (
        <section className="parliament-proposal-card parliament-proposal-card--existing">
          <h3>Processo privado já existente</h3>
          <p>{STATE_LABELS[candidate.existing_case.state]} · revisão {candidate.existing_case.revision}. Mesmo aprovada, a identidade permanece privada.</p>
          <Link className="button" href={`/admin/revisao/${encodeURIComponent(candidate.existing_case.id)}`}>Abrir processo</Link>
        </section>
      ) : candidate.proposal_eligible ? (
        <form action={createBaseOrganisationIdentityProposal} className="parliament-proposal-card">
          <input type="hidden" name="observation_id" value={candidate.observation_id} />
          <input type="hidden" name="source_record_sha256" value={candidate.source_record_sha256} />
          <input type="hidden" name="proposal_confirmation_sha256" value={candidate.proposal_confirmation_sha256} />
          <h3>Criar proposta por rever (PENDING)</h3>
          <p>A fonte não é aprovada automaticamente. A proposta de ingestão e a revisão humana são etapas separadas.</p>
          <label className="admin-confirmation">
            <input name="confirm_independent_official_source" type="checkbox" required />
            <span>Confirmei a prova individual do IRN e o arquivo, independentes do contrato BASE.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_private_identity_only" type="checkbox" required />
            <span>Confirmo uma prova privada de identidade, sem correspondência de nomes ou ligação automática.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_publication" type="checkbox" required />
            <span>Confirmo que não serão publicadas organizações, partes de contratos, candidatos ou relações.</span>
          </label>
          <button className="button button--primary" type="submit">Propor revisão privada</button>
        </form>
      ) : null}
    </article>
  );
}
