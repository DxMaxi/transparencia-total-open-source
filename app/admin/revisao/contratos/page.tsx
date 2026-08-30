import Link from "next/link";
import type { ReactNode } from "react";
import { createBaseContractProposal } from "../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type BaseContractEditorialCandidate,
  type BaseContractEditorialCandidateList,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeZone: "Europe/Lisbon",
});
const dateTimeFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});
const PARTY_ROLE_LABELS: Record<
  BaseContractEditorialCandidate["parties"][number]["role"],
  string
> = {
  CONTRACTING_AUTHORITY: "Entidade adjudicante",
  CONTRACTOR: "Adjudicatário",
  CO_CONTRACTOR: "Coadjudicatário",
};
const COVERAGE_LABELS: Record<
  NonNullable<BaseContractEditorialCandidate["catalogue"]>["coverage_state"],
  string
> = {
  HISTORICAL_CLOSED_YEAR: "Ano encerrado e histórico",
  CURRENT_ROLLING_YEAR: "Ano corrente e provisório",
};
const SYNC_STATUS_LABELS: Record<string, string> = {
  SUCCEEDED: "Concluída",
  PARTIAL: "Concluída com limitações registadas",
  FAILED: "Falhou",
  RUNNING: "Em curso",
};
const PROCEDURE_LABELS: Record<string, string> = {
  DIRECT_AWARD: "Ajuste direto",
  PRIOR_CONSULTATION: "Consulta prévia",
  PUBLIC_TENDER: "Concurso público",
  LIMITED_TENDER: "Concurso limitado",
  NEGOTIATED_PROCEDURE: "Procedimento por negociação",
  FRAMEWORK_AGREEMENT: "Acordo-quadro",
  OTHER: "Outro procedimento indicado pela fonte",
  UNKNOWN: "Dados indisponíveis",
};

function boundedYear(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isSafeInteger(parsed) && parsed >= 2012 && parsed <= 2100
    ? parsed
    : null;
}

function formatDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value)) : "dados indisponíveis";
}

function formatDateTime(value: string | null): string {
  return value
    ? dateTimeFormatter.format(new Date(value))
    : "dados indisponíveis";
}

function formatAmount(value: string | null, currency: string): string {
  if (value === null) return "dados indisponíveis";
  const match = /^(0|[1-9][0-9]*)(?:\.([0-9]{1,2}))?$/.exec(value);
  if (!match) return "dados indisponíveis";
  const integer = match[1].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimal = (match[2] ?? "").padEnd(2, "0");
  const exactAmount = `${integer},${decimal}`;
  return currency === "EUR" ? `${exactAmount} €` : `${exactAmount} ${currency}`;
}

function pageHref(
  query: string,
  year: number | null,
  cursor: string | null = null,
): string {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (year !== null) params.set("year", String(year));
  if (cursor) params.set("cursor", cursor);
  const encoded = params.toString();
  return encoded
    ? `/admin/revisao/contratos?${encoded}`
    : "/admin/revisao/contratos";
}

export default async function BaseContractEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    year?: string;
    cursor?: string;
    erro?: string;
    sucesso?: string;
  }>;
}) {
  const input = await searchParams;
  const operationSucceeded =
    input.sucesso === "contrato-base-importado" ||
    input.sucesso === "contrato-base-existente";
  const query = (input.q?.trim() || "").slice(0, 100);
  const year = boundedYear(input.year);
  const cursor = input.cursor?.trim().slice(0, 1600) || null;
  const limit = 20;
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.length >= 2) params.set("q", query);
  if (year !== null) params.set("year", String(year));
  if (cursor) params.set("cursor", cursor);
  const catalogue = await editorialFetch<BaseContractEditorialCandidateList>(
    `/base/contract-candidates?${params.toString()}`,
  );

  return (
    <div className="admin-page parliament-editorial-page base-contract-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">
            V5.50 · Portal BASE com porta editorial privada
          </p>
          <h1>Rever contratos públicos recolhidos</h1>
          <p>
            Compare o contrato normalizado com o ficheiro anual oficial, o
            arquivo SHA-256 e o catálogo temporal. A prova abrange este registo
            e o lote normalizado; não presume que todas as linhas do ZIP se
            tornaram candidatos. Criar uma proposta não publica nada.
          </p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao">Voltar à fila editorial</Link>
          <a
            href="https://www.base.gov.pt/Base4/pt/pesquisa/?type=contratos"
            target="_blank"
            rel="noreferrer noopener"
            aria-label="Abrir Portal BASE num novo separador"
          >
            Abrir Portal BASE
          </a>
        </div>
      </header>

      {input.erro ? (
        <p className="private-message private-message--error" role="alert">
          {input.erro}
        </p>
      ) : null}
      {operationSucceeded ? (
        <p className="private-message private-message--success" role="status">
          Proposta BASE privada criada ou localizada; nenhuma publicação foi
          executada.
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>A designação de uma parte não prova a sua identidade</strong>
        <p>
          Nomes e HMAC servem apenas para conservar a observação privada. Uma
          organização só pode nascer mais tarde com identificador e fonte
          oficial independentes; não existe fuzzy matching nem associação
          automática por designação.
        </p>
      </aside>

      <aside className="admin-private-warning">
        <strong>Ano corrente: cobertura provisória</strong>
        <p>
          Apenas recursos de anos encerrados podem avançar. Uma ausência no ano
          corrente significa dados ainda indisponíveis e nunca ausência de
          contrato, incumprimento ou ocultação.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Localizar no staging privado
          <input
            name="q"
            defaultValue={query}
            minLength={2}
            maxLength={100}
            placeholder="ID exato; com ano, objeto ou designação"
          />
        </label>
        <label>
          Ano do recurso
          <input
            name="year"
            type="number"
            min={2012}
            max={2100}
            defaultValue={year ?? ""}
          />
        </label>
        <button className="button" type="submit">
          Consultar
        </button>
        <Link href="/admin/revisao/contratos">Limpar</Link>
      </form>

      <p className="admin-form-help" aria-live="polite">
        {catalogue.filter_required
          ? `Nenhuma consulta executada. ${catalogue.search_rule}`
          : `${catalogue.total.toLocaleString("pt-PT")} ${
              catalogue.total === 1 ? "contrato" : "contratos"
            } nesta consulta. ${catalogue.search_rule}`}
      </p>
      <p className="admin-form-help">{catalogue.coverage_rule}</p>

      {catalogue.filter_required ? (
        <section className="admin-empty-state">
          <strong>Defina primeiro uma consulta limitada.</strong>
          <p>
            Indique o identificador oficial exato ou selecione um ano. A
            pesquisa por objeto ou designação literal só é permitida dentro de
            um ano, para evitar varrer todo o staging privado.
          </p>
        </section>
      ) : catalogue.items.length ? (
        <section
          className="parliament-snapshot-list"
          aria-label="Snapshots privados BASE"
        >
          {catalogue.items.map((candidate) => (
            <BaseContractCandidateCard
              candidate={candidate}
              key={candidate.contract_snapshot_id}
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Nenhum snapshot corresponde a esta consulta limitada.</strong>
          <p>
            Este resultado não prova ausência de contratos, incumprimento ou
            ocultação. Significa apenas que a fonte privada validada não
            devolveu um registo para estes critérios.
          </p>
        </section>
      )}

      <nav
        className="admin-heading-actions"
        aria-label="Paginação de contratos BASE"
      >
        {cursor ? (
          <Link className="button" href={pageHref(query, year)}>
            Voltar ao início
          </Link>
        ) : null}
        {catalogue.next_cursor !== null ? (
          <Link
            className="button"
            href={pageHref(query, year, catalogue.next_cursor)}
          >
            Página seguinte
          </Link>
        ) : null}
      </nav>
    </div>
  );
}

function BaseContractCandidateCard({
  candidate,
}: {
  candidate: BaseContractEditorialCandidate;
}) {
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">
            Contrato BASE · {candidate.batch.resource_year}
          </p>
          <h2>{candidate.object}</h2>
          <p>Identificador oficial {candidate.official_contract_id}</p>
        </div>
        <span
          className={`admin-state ${candidate.proposal_eligible ? "state-approved" : "state-pending"}`}
        >
          {candidate.proposal_eligible
            ? "Pronto para revisão privada"
            : "Prova ainda insuficiente"}
        </span>
      </header>

      <section
        className="parliament-proof-grid"
        aria-label="Prova oficial BASE"
      >
        <dl>
          <div>
            <dt>Valor do contrato</dt>
            <dd>
              {formatAmount(candidate.contract_value, candidate.currency)}
            </dd>
          </div>
          <div>
            <dt>Valor base</dt>
            <dd>{formatAmount(candidate.base_value, candidate.currency)}</dd>
          </div>
          <div>
            <dt>Procedimento</dt>
            <dd>
              {PROCEDURE_LABELS[candidate.procedure] ?? "Dados indisponíveis"}
            </dd>
          </div>
          <div>
            <dt>Vocabulário CPV</dt>
            <dd>{candidate.cpv_code ?? "dados indisponíveis"}</dd>
          </div>
          <div>
            <dt>Decisão</dt>
            <dd>{formatDate(candidate.decision_at)}</dd>
          </div>
          <div>
            <dt>Assinatura</dt>
            <dd>{formatDate(candidate.signed_at)}</dd>
          </div>
          <div>
            <dt>Publicado na fonte</dt>
            <dd>{formatDate(candidate.published_at)}</dd>
          </div>
          <div>
            <dt>Recolhido</dt>
            <dd>{formatDateTime(candidate.source.retrieved_at)}</dd>
          </div>
          <div>
            <dt>Prazo de execução</dt>
            <dd>
              {candidate.execution_days === null
                ? "dados indisponíveis"
                : `${candidate.execution_days.toLocaleString("pt-PT")} dias`}
            </dd>
          </div>
          <div>
            <dt>Contratos normalizados no lote</dt>
            <dd>{candidate.batch.contract_count.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Partes normalizadas no lote</dt>
            <dd>{candidate.batch.party_count.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>SHA-256 da fonte</dt>
            <dd>
              <code>{candidate.source.content_sha256}</code>
            </dd>
          </div>
          <div>
            <dt>SHA-256 do registo</dt>
            <dd>
              <code>{candidate.source_record_sha256}</code>
            </dd>
          </div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Original anual arquivado</strong>
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
            aria-label="Abrir ou descarregar o ZIP oficial num novo separador"
          >
            Abrir ZIP oficial (
            {candidate.archive
              ? `${Math.max(0.01, candidate.archive.byte_size / 1_000_000).toLocaleString("pt-PT", { maximumFractionDigits: 2 })} MB`
              : "tamanho indisponível"}
            )
          </a>
          {candidate.direct_official_url ? (
            <a
              className="button"
              href={candidate.direct_official_url}
              target="_blank"
              rel="noreferrer noopener"
              aria-label="Abrir registo individual no Portal BASE num novo separador"
            >
              Abrir registo individual
            </a>
          ) : null}
        </div>
      </section>

      <details className="parliament-proposal-card">
        <summary>Ver cadeia técnica integral antes de confirmar</summary>
        <p>
          Estes valores são reconstruídos pelo servidor. A proposta fica
          bloqueada se uma contagem, URL, data ou SHA-256 deixar de coincidir.
        </p>
        <dl className="admin-proof-inline">
          <div>
            <dt>Contratos normalizados declarados / materializados</dt>
            <dd>
              {candidate.batch.contract_count.toLocaleString("pt-PT")} /{" "}
              {candidate.batch.actual_contract_count.toLocaleString("pt-PT")}
            </dd>
          </div>
          <div>
            <dt>Partes normalizadas declaradas / materializadas</dt>
            <dd>
              {candidate.batch.party_count.toLocaleString("pt-PT")} /{" "}
              {candidate.batch.actual_party_count.toLocaleString("pt-PT")}
            </dd>
          </div>
          <div>
            <dt>Registos lidos / escritos</dt>
            <dd>
              {candidate.batch.records_read.toLocaleString("pt-PT")} /{" "}
              {candidate.batch.records_written.toLocaleString("pt-PT")}
            </dd>
          </div>
          <div>
            <dt>Contagens coincidentes</dt>
            <dd>
              {candidate.batch.counts_match
                ? "Sim"
                : "Não — proposta bloqueada"}
            </dd>
          </div>
          <div>
            <dt>Estado da recolha</dt>
            <dd>
              {SYNC_STATUS_LABELS[candidate.batch.sync_status] ??
                "Estado técnico indisponível"}
            </dd>
          </div>
          <div>
            <dt>Recolha terminada</dt>
            <dd>{formatDateTime(candidate.batch.sync_finished_at)}</dd>
          </div>
          <div>
            <dt>Versão do parser</dt>
            <dd>
              <code>{candidate.batch.parser_version}</code>
            </dd>
          </div>
          <div>
            <dt>SHA-256 do lote normalizado</dt>
            <dd>
              <code>{candidate.batch.normalised_sha256}</code>
            </dd>
          </div>
          <div>
            <dt>SHA-256 da atestação do original</dt>
            <dd>
              <code>
                {candidate.archive?.attestation_sha256 ?? "dados indisponíveis"}
              </code>
            </dd>
          </div>
          <div>
            <dt>Original arquivado</dt>
            <dd>{formatDateTime(candidate.archive?.archived_at ?? null)}</dd>
          </div>
          <div>
            <dt>Tamanho arquivado / catalogado</dt>
            <dd>
              {candidate.archive && candidate.catalogue
                ? `${candidate.archive.byte_size.toLocaleString("pt-PT")} / ${candidate.catalogue.byte_size.toLocaleString("pt-PT")} bytes`
                : "dados indisponíveis"}
            </dd>
          </div>
          <div>
            <dt>Ano do recurso catalogado</dt>
            <dd>
              {candidate.catalogue?.resource_year ?? "dados indisponíveis"}
            </dd>
          </div>
          <div>
            <dt>Cobertura do recurso</dt>
            <dd>
              {candidate.catalogue
                ? COVERAGE_LABELS[candidate.catalogue.coverage_state]
                : "dados indisponíveis"}
            </dd>
          </div>
          <div>
            <dt>Atualização declarada do recurso</dt>
            <dd>
              {formatDateTime(candidate.catalogue?.source_modified_at ?? null)}
            </dd>
          </div>
          <div>
            <dt>SHA-256 do âmbito temporal</dt>
            <dd>
              <code>
                {candidate.catalogue?.scope_sha256 ?? "dados indisponíveis"}
              </code>
            </dd>
          </div>
          <div>
            <dt>SHA-256 dos metadados anuais</dt>
            <dd>
              <code>
                {candidate.catalogue?.metadata_sha256 ?? "dados indisponíveis"}
              </code>
            </dd>
          </div>
          <div>
            <dt>SHA-256 da fonte do catálogo</dt>
            <dd>
              <code>
                {candidate.catalogue?.source_sha256 ?? "dados indisponíveis"}
              </code>
            </dd>
          </div>
          <div>
            <dt>SHA-256 da atestação do catálogo</dt>
            <dd>
              <code>
                {candidate.catalogue?.archive_attestation_sha256 ??
                  "dados indisponíveis"}
              </code>
            </dd>
          </div>
          <div>
            <dt>Alcance desta prova</dt>
            <dd>
              Registo oficial específico; sem alegação de cobertura integral do
              ZIP anual
            </dd>
          </div>
        </dl>
        {candidate.catalogue ? (
          <div className="admin-heading-actions">
            <a
              className="button"
              href={candidate.catalogue.versioned_url}
              target="_blank"
              rel="noreferrer noopener"
              aria-label="Abrir recurso anual versionado num novo separador"
            >
              Abrir recurso versionado
            </a>
            <a
              className="button"
              href={candidate.catalogue.stable_url}
              target="_blank"
              rel="noreferrer noopener"
              aria-label="Abrir URL estável do recurso anual num novo separador"
            >
              Abrir URL estável
            </a>
          </div>
        ) : null}
      </details>

      {candidate.batch.warnings.length ? (
        <section className="parliament-proposal-card">
          <p className="eyebrow">Limitações declaradas pela recolha</p>
          <h3>Leia antes de propor</h3>
          <ul className="parliament-limitations">
            {candidate.batch.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
          <p>
            Estas limitações não são conclusões sobre a fonte. Uma amostragem
            truncada bloqueia a proposta; as restantes ficam preservadas para a
            revisão deste registo específico.
          </p>
        </section>
      ) : null}

      <section className="parliament-proposal-card">
        <p className="eyebrow">Partes tal como aparecem na fonte</p>
        <h3>Observação sem correspondência</h3>
        {candidate.parties.length ? (
          <ul className="parliament-limitations">
            {candidate.parties.map((party) => (
              <li key={party.id}>
                {party.source_name} · {PARTY_ROLE_LABELS[party.role]}
                {party.protected_identifier_observed
                  ? " · HMAC privado observado"
                  : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p>Dados das partes indisponíveis na fonte normalizada.</p>
        )}
      </section>

      {candidate.blocked_reasons.length ? (
        <section
          className="parliament-proposal-card"
          id={`base-blockers-${candidate.contract_snapshot_id}`}
        >
          <p className="eyebrow">Prova insuficiente</p>
          <h3>A proposta não pode avançar nesta fotografia</h3>
          <ul className="parliament-limitations">
            {candidate.blocked_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {candidate.existing_case ? (
        <section className="parliament-proposal-card parliament-proposal-card--existing">
          <p className="eyebrow">Processo editorial</p>
          <h3>Proposta já existente</h3>
          <p>
            {STATE_LABELS[candidate.existing_case.state]} · revisão{" "}
            {candidate.existing_case.revision}
          </p>
          <Link
            className="button"
            href={`/admin/revisao/${candidate.existing_case.id}`}
          >
            Abrir processo
          </Link>
        </section>
      ) : (
        <form
          action={createBaseContractProposal}
          className="parliament-proposal-card"
        >
          <input
            type="hidden"
            name="contract_snapshot_id"
            value={candidate.contract_snapshot_id}
          />
          <input
            type="hidden"
            name="source_record_sha256"
            value={candidate.source_record_sha256}
          />
          <p className="eyebrow">Revisão humana</p>
          <h3>Criar proposta pendente</h3>
          <p>
            Esta operação só copia prova normalizada para o circuito editorial
            privado.
          </p>
          <Confirmation name="confirm_private_only">
            Confirmo que a proposta permanece exclusivamente privada.
          </Confirmation>
          <Confirmation name="confirm_normalized_batch_consistency">
            Li as limitações e confirmei as contagens do lote normalizado; não
            assumo cobertura integral do ficheiro anual.
          </Confirmation>
          <Confirmation name="confirm_exact_official_contract_id">
            Confirmei o identificador oficial exato do contrato.
          </Confirmation>
          <Confirmation name="confirm_no_party_identity_or_name_matching">
            Não usarei nomes ou HMAC para associar automaticamente partes.
          </Confirmation>
          <Confirmation name="confirm_organisations_require_independent_sources">
            Cada organização exigirá uma fonte oficial independente e
            inequívoca.
          </Confirmation>
          <Confirmation name="confirm_no_contract_or_relationship_publication">
            Esta ação não publica contrato, organização, correspondência ou
            relação.
          </Confirmation>
          <button
            className="button button--primary"
            type="submit"
            disabled={!candidate.proposal_eligible}
            aria-describedby={
              candidate.proposal_eligible
                ? undefined
                : `base-blockers-${candidate.contract_snapshot_id}`
            }
          >
            Enviar para revisão privada
          </button>
        </form>
      )}
    </article>
  );
}

function Confirmation({
  name,
  children,
}: {
  name: string;
  children: ReactNode;
}) {
  return (
    <label className="admin-confirmation">
      <input name={name} type="checkbox" required />
      <span>{children}</span>
    </label>
  );
}
