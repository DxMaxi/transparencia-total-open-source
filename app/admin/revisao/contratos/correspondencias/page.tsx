import Link from "next/link";
import { createBaseContractOrganisationMatchCandidate } from "../../actions";
import {
  EditorialApiError,
  editorialFetch,
  getEditorialContext,
} from "@/lib/editorial-api";
import type {
  BaseContractOrganisationMatchCandidate,
  BaseContractOrganisationMatchCandidateList,
  BaseContractOrganisationMatchSourceProof,
} from "@/lib/editorial-types";

const BASE_PUBLIC_CONTRACT_ID = /^base_contract_[0-9a-f]{64}$/;

const roleLabels: Record<
  BaseContractOrganisationMatchCandidate["contract_party"]["role"],
  string
> = {
  CONTRACTING_AUTHORITY: "Entidade adjudicante",
  CONTRACTOR: "Adjudicatário",
  CO_CONTRACTOR: "Coadjudicatário",
};

const kindLabels: Record<
  BaseContractOrganisationMatchCandidate["organisation"]["kind"],
  string
> = {
  PUBLIC_BODY: "Entidade pública",
  COMPANY: "Empresa",
  NON_PROFIT: "Entidade sem fins lucrativos",
  EUROPEAN_BODY: "Entidade europeia",
  OTHER: "Outra organização",
};

const actionErrorMessages: Record<string, string> = {
  "confirmacao-em-falta":
    "Confirme todos os limites antes de criar o candidato privado.",
  "identificador-invalido":
    "O identificador público do contrato não tem o formato esperado.",
  "prova-invalidada":
    "Uma fotografia ou prova mudou. Consulte novamente as duas fontes antes de repetir.",
  "operacao-nao-concluida":
    "Não foi possível criar o candidato privado. Consulte novamente antes de repetir.",
};

const successMessages: Record<string, string> = {
  "candidato-criado":
    "Candidato privado criado em PENDING_REVIEW. Nenhuma relação foi publicada.",
  "candidato-existente":
    "O candidato privado já existia e permanece em PENDING_REVIEW.",
};

function safePublicContractId(value: unknown): string | null {
  if (value === undefined || value === "") return "";
  if (typeof value !== "string") return null;
  const candidate = value.trim();
  return BASE_PUBLIC_CONTRACT_ID.test(candidate) ? candidate : null;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "dados indisponíveis";
  return new Intl.DateTimeFormat("pt-PT", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Lisbon",
  }).format(date);
}

type QueryFailure = "not-found" | "proof-invalidated" | "unavailable";

export default async function ContractOrganisationMatchPage({
  searchParams,
}: {
  searchParams: Promise<{
    public_contract_id?: string | string[];
    erro?: string | string[];
    sucesso?: string | string[];
  }>;
}) {
  await getEditorialContext();
  const input = await searchParams;
  const safeId = safePublicContractId(input.public_contract_id);
  const publicContractId = safeId ?? "";
  let inspection: BaseContractOrganisationMatchCandidateList | null = null;
  let queryFailure: QueryFailure | null = null;

  if (publicContractId) {
    const params = new URLSearchParams({
      public_contract_id: publicContractId,
    });
    try {
      inspection =
        await editorialFetch<BaseContractOrganisationMatchCandidateList>(
          `/base/contract-organisation-match-candidates?${params.toString()}`,
        );
    } catch (error) {
      if (error instanceof EditorialApiError && error.status === 404) {
        queryFailure = "not-found";
      } else if (
        error instanceof EditorialApiError &&
        [409, 422].includes(error.status)
      ) {
        queryFailure = "proof-invalidated";
      } else {
        queryFailure = "unavailable";
      }
    }
  }

  const actionError =
    typeof input.erro === "string" &&
    Object.hasOwn(actionErrorMessages, input.erro)
      ? actionErrorMessages[input.erro]
      : null;
  const success =
    typeof input.sucesso === "string" &&
    Object.hasOwn(successMessages, input.sucesso)
      ? successMessages[input.sucesso]
      : null;

  return (
    <div className="admin-page parliament-editorial-page base-contract-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">
            V5.54 · Correspondência exata, privada e por rever
          </p>
          <h1>Preparar correspondências entre partes e organizações</h1>
          <p>
            Procure pelo identificador público exato de um contrato já
            publicado. O servidor compara apenas identificadores protegidos das
            duas fontes oficiais. O identificador fiscal e o respetivo HMAC nunca são enviados ao navegador.
            Criar um candidato não confirma nem publica uma relação.
          </p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao/contratos">Voltar aos contratos</Link>
          <Link href="/admin/revisao/organizacoes">
            Rever identidades de organizações
          </Link>
          <Link href="/admin/revisao">Voltar à fila editorial</Link>
        </div>
      </header>

      <aside className="admin-private-warning">
        <strong>Correspondência não é conclusão</strong>
        <p>
          Mesmo uma igualdade exata origina apenas um candidato privado em
          PENDING_REVIEW. Não prova representação, controlo, benefício, conflito
          ou irregularidade e não cria uma parte nem uma relação pública.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Identificador público exato do contrato
          <input
            name="public_contract_id"
            type="search"
            defaultValue={publicContractId}
            minLength={78}
            maxLength={78}
            pattern="base_contract_[0-9a-f]{64}"
            placeholder="base_contract_…"
            autoComplete="off"
            spellCheck={false}
            aria-describedby="contract-match-search-help"
          />
        </label>
        <button className="button" type="submit">
          Comparar provas privadas
        </button>
        <Link href="/admin/revisao/contratos/correspondencias">Limpar</Link>
      </form>
      <p id="contract-match-search-help" className="admin-form-help">
        Use apenas o identificador público apresentado pelo circuito V5.51. Não
        pesquise por nomes, siglas ou identificadores protegidos.
      </p>

      {safeId === null ? (
        <p className="private-message private-message--error" role="alert">
          Pesquisa não aceite. Introduza um identificador público de contrato no
          formato exato esperado; o valor recebido não foi enviado à API nem é
          repetido nesta página.
        </p>
      ) : null}
      {actionError ? (
        <p className="private-message private-message--error" role="alert">
          {actionError}
        </p>
      ) : null}
      {success ? (
        <p className="private-message private-message--success" role="status">
          {success}
        </p>
      ) : null}
      {queryFailure === "not-found" ? (
        <p className="private-message private-message--error" role="alert">
          Não foi localizada uma fotografia pública ativa para este
          identificador. Isto não demonstra inexistência de um contrato na fonte
          nem autoriza usar dados antigos como substituição.
        </p>
      ) : null}
      {queryFailure === "proof-invalidated" ? (
        <p className="private-message private-message--error" role="alert">
          A fotografia ou a prova atual não permite esta comparação. Nenhum
          candidato foi criado; consulte novamente depois de a fonte e a revisão
          estarem coerentes.
        </p>
      ) : null}
      {queryFailure === "unavailable" ? (
        <p className="private-message private-message--error" role="alert">
          Consulta privada temporariamente indisponível. Não apresentamos uma
          ausência de resultados como ausência factual de dados.
        </p>
      ) : null}

      {!publicContractId && safeId !== null ? (
        <section className="admin-empty-state">
          <strong>Indique primeiro um contrato público exato.</strong>
          <p>
            Esta porta não permite explorar organizações por nome nem varrer o
            staging privado.
          </p>
        </section>
      ) : null}

      {inspection ? (
        <InspectionSummary inspection={inspection} />
      ) : null}
    </div>
  );
}

function InspectionSummary({
  inspection,
}: {
  inspection: BaseContractOrganisationMatchCandidateList;
}) {
  return (
    <>
      <section className="parliament-proposal-card">
        <p className="eyebrow">Contrato publicado consultado</p>
        <h2>{inspection.public_contract.object}</h2>
        <dl className="admin-proof-inline">
          <div>
            <dt>Identificador oficial</dt>
            <dd>{inspection.public_contract.official_contract_id}</dd>
          </div>
          <div>
            <dt>Identificador público</dt>
            <dd>
              <code>{inspection.public_contract.id}</code>
            </dd>
          </div>
          <div>
            <dt>Partes observadas na fotografia</dt>
            <dd>{inspection.party_count.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Partes com identificador protegido observado</dt>
            <dd>{inspection.protected_party_count.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Partes com uma correspondência exata única</dt>
            <dd>
              {inspection.exact_matched_party_count.toLocaleString("pt-PT")}
            </dd>
          </div>
          <div>
            <dt>Pares privados encontrados</dt>
            <dd>{inspection.candidate_pair_count.toLocaleString("pt-PT")}</dd>
          </div>
        </dl>
        <p>{inspection.creation_rule}</p>
      </section>

      {inspection.items.length ? (
        <section
          className="parliament-snapshot-list"
          aria-label="Correspondências exatas candidatas"
        >
          {inspection.items.map((candidate) => (
            <MatchCandidateCard
              candidate={candidate}
              publicContract={inspection.public_contract}
              key={candidate.candidate_proof_sha256}
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Dados indisponíveis para criar um candidato exato.</strong>
          <p>
            Nenhuma parte desta fotografia coincide de forma exata e única com
            uma organização atualmente publicada. Isto não prova que a parte ou
            a organização não existem, nem permite uma pesquisa por nome.
          </p>
        </section>
      )}
    </>
  );
}

function MatchCandidateCard({
  candidate,
  publicContract,
}: {
  candidate: BaseContractOrganisationMatchCandidate;
  publicContract: BaseContractOrganisationMatchCandidateList["public_contract"];
}) {
  const existing = candidate.existing_candidate;
  const blockedId = `match-blockers-${candidate.candidate_proof_sha256}`;

  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">
            {kindLabels[candidate.organisation.kind]} · candidato privado
          </p>
          <h2>{candidate.organisation.legal_name}</h2>
          <p>
            {publicContract.object} · parte {candidate.contract_party.ordinal} ·{" "}
            {roleLabels[candidate.contract_party.role]}
          </p>
        </div>
        <span
          className={`admin-state ${candidate.eligible ? "state-approved" : "state-pending"}`}
        >
          {existing
            ? "PENDING_REVIEW · já existente"
            : candidate.eligible
              ? "Pronto para criar PENDING_REVIEW"
              : "Prova bloqueada"}
        </span>
      </header>

      <aside className="admin-private-warning">
        <strong>Nomes apenas para leitura</strong>
        <p>
          A designação da parte e a denominação da organização são transcrições
          das fontes. Não foram comparadas nem usadas para estabelecer
          identidade.
        </p>
      </aside>

      <section className="parliament-proof-grid" aria-label="Provas independentes">
        <dl>
          <div>
            <dt>Parte tal como consta do BASE</dt>
            <dd>{candidate.contract_party.source_name}</dd>
          </div>
          <div>
            <dt>Função contratual</dt>
            <dd>{roleLabels[candidate.contract_party.role]}</dd>
          </div>
          <div>
            <dt>Organização publicada</dt>
            <dd>{candidate.organisation.legal_name}</dd>
          </div>
          <div>
            <dt>Referência oficial não fiscal</dt>
            <dd>{candidate.organisation.registry_record_id}</dd>
          </div>
          <div>
            <dt>Método</dt>
            <dd>Identificador protegido exato, comparado no servidor</dd>
          </div>
          <div>
            <dt>Estado do candidato</dt>
            <dd>{candidate.decision}</dd>
          </div>
          <div>
            <dt>Efeito público</dt>
            <dd>Nenhuma parte, correspondência ou relação criada</dd>
          </div>
          <div>
            <dt>SHA-256 da prova combinada</dt>
            <dd>
              <code>{candidate.candidate_proof_sha256}</code>
            </dd>
          </div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Duas publicações ativas</strong>
          <span>Contrato BASE e organização com fontes independentes</span>
          <a
            className="button"
            href={candidate.contract_source.url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Abrir fonte oficial do contrato
          </a>
          <a
            className="button"
            href={candidate.organisation_source.url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Abrir fonte oficial da organização
          </a>
          <a
            href={candidate.organisation.official_url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Abrir ato oficial da organização
          </a>
        </div>
      </section>

      <div className="parliament-proposal-grid">
        <SourceProof
          heading="Prova do contrato BASE"
          proof={candidate.contract_source}
        />
        <SourceProof
          heading="Prova independente da organização"
          proof={candidate.organisation_source}
        />
      </div>

      {candidate.blockers.length ? (
        <section className="parliament-proposal-card" id={blockedId}>
          <p className="eyebrow">Prova insuficiente</p>
          <h3>O candidato não pode ser criado nesta fotografia</h3>
          <ul className="parliament-limitations">
            {candidate.blockers.map((blocker) => (
              <li key={blocker.code}>{blocker.detail}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {existing ? (
        <section className="parliament-proposal-card parliament-proposal-card--existing">
          <p className="eyebrow">Histórico privado preservado</p>
          <h3>Candidato já existente</h3>
          <p>
            {existing.decision} · criado por {existing.created_by_alias} em{" "}
            {formatDateTime(existing.created_at)}. Esta existência não confirma
            nem publica a correspondência.
          </p>
          <code>{existing.id}</code>
        </section>
      ) : (
        <form
          action={createBaseContractOrganisationMatchCandidate}
          className="parliament-proposal-card"
        >
          <input
            type="hidden"
            name="expected_public_contract_id"
            value={publicContract.id}
          />
          <input
            type="hidden"
            name="expected_contract_publication_snapshot_id"
            value={candidate.contract_publication_snapshot_id}
          />
          <input
            type="hidden"
            name="expected_contract_party_snapshot_id"
            value={candidate.contract_party_snapshot_id}
          />
          <input
            type="hidden"
            name="expected_organisation_id"
            value={candidate.organisation_id}
          />
          <input
            type="hidden"
            name="expected_organisation_publication_snapshot_id"
            value={candidate.organisation_publication_snapshot_id}
          />
          <input
            type="hidden"
            name="expected_candidate_proof_sha256"
            value={candidate.candidate_proof_sha256}
          />
          <p className="eyebrow">Registo privado append-only</p>
          <h3>Criar candidato PENDING_REVIEW</h3>
          <label>
            Fundamentação privada
            <textarea
              name="rationale"
              minLength={20}
              maxLength={1000}
              required
              placeholder="Registe como confirmou as duas fontes e fotografias, sem copiar identificadores protegidos."
            />
          </label>
          <Confirmation name="confirm_exact_protected_identifier">
            Confirmei que o servidor reconstruiu uma igualdade exata do
            identificador protegido.
          </Confirmation>
          <Confirmation name="confirm_two_active_publications">
            Confirmei que contrato e organização têm fotografias públicas atuais
            e ativas.
          </Confirmation>
          <Confirmation name="confirm_independent_official_sources">
            Confirmei as duas fontes oficiais independentes, os arquivos e os
            SHA-256.
          </Confirmation>
          <Confirmation name="confirm_private_pending_review_only">
            Confirmo que será criado apenas um candidato privado em
            PENDING_REVIEW.
          </Confirmation>
          <Confirmation name="confirm_no_name_or_fuzzy_matching">
            Confirmo que nenhum nome, sigla ou similaridade foi usado para a
            correspondência.
          </Confirmation>
          <Confirmation name="confirm_no_public_party_match_or_relationship">
            Confirmo que esta operação não cria parte pública, correspondência
            legada, nó, relação ou evento público.
          </Confirmation>
          <button
            className="button button--primary"
            type="submit"
            disabled={!candidate.eligible}
            aria-describedby={candidate.eligible ? undefined : blockedId}
          >
            Criar candidato privado
          </button>
        </form>
      )}
    </article>
  );
}

function SourceProof({
  heading,
  proof,
}: {
  heading: string;
  proof: BaseContractOrganisationMatchSourceProof;
}) {
  return (
    <section className="parliament-proposal-card">
      <h3>{heading}</h3>
      <dl className="admin-proof-inline">
        <div>
          <dt>Fonte</dt>
          <dd>{proof.title}</dd>
        </div>
        <div>
          <dt>Recolhida</dt>
          <dd>{formatDateTime(proof.retrieved_at)}</dd>
        </div>
        <div>
          <dt>SHA-256 da fonte</dt>
          <dd>
            <code>{proof.content_sha256}</code>
          </dd>
        </div>
        <div>
          <dt>SHA-256 do registo</dt>
          <dd>
            <code>{proof.source_record_sha256}</code>
          </dd>
        </div>
        <div>
          <dt>SHA-256 da atestação do arquivo</dt>
          <dd>
            <code>{proof.archive_attestation_sha256}</code>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function Confirmation({
  name,
  children,
}: {
  name: string;
  children: React.ReactNode;
}) {
  return (
    <label className="admin-confirmation">
      <input name={name} type="checkbox" required />
      <span>{children}</span>
    </label>
  );
}
