import Link from "next/link";
import {
  createPoliticianMandateProposal,
  publishPoliticianMandate,
} from "../../../actions";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type PoliticianMandateEditorialCandidate,
  type PoliticianMandateEditorialCandidateList,
  type PoliticianMandatePublicationPreview,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeZone: "Europe/Lisbon",
});

function boundedOffset(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "0", 10);
  return Number.isSafeInteger(parsed) && parsed >= 0 && parsed <= 10_000 ? parsed : 0;
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
  return `/admin/revisao/parlamento/deputados/mandatos?${params.toString()}`;
}

function formatDate(value: string | null): string {
  return value ? dateFormatter.format(new Date(value)) : "dados indisponíveis";
}

async function loadPublicationPreview(
  caseId: string,
): Promise<PoliticianMandatePublicationPreview | null> {
  try {
    return await editorialFetch<PoliticianMandatePublicationPreview>(
      `/parliament/mandate-cases/${encodeURIComponent(caseId)}/publication`,
    );
  } catch {
    return null;
  }
}

export default async function PoliticianMandateEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{
    legislature?: string;
    q?: string;
    offset?: string;
    erro?: string;
    sucesso?: string;
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
  const catalogue = await editorialFetch<PoliticianMandateEditorialCandidateList>(
    `/parliament/mandate-candidates?${params.toString()}`,
  );
  const { staff } = await getEditorialContext();
  const publicationPreviews = new Map<string, PoliticianMandatePublicationPreview>();
  await Promise.all(
    catalogue.items.map(async (candidate) => {
      if (candidate.existing_case?.state === "APPROVED" && candidate.proposal_eligible) {
        const preview = await loadPublicationPreview(candidate.existing_case.id);
        if (preview) publicationPreviews.set(candidate.existing_case.id, preview);
      }
    }),
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.33 · mandatos por intervalo oficial</p>
          <h1>Preparar mandatos para revisão humana</h1>
          <p>
            Cada linha é uma situação observada na fonte parlamentar. Mesmo com datas, permanece
            apenas um candidato privado até um revisor confirmar o significado do período.
          </p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao/parlamento/deputados">Voltar aos perfis</Link>
          <Link href="/admin/revisao/parlamento">Voltar às fotografias</Link>
        </div>
      </header>

      {input.erro ? (
        <p className="private-message private-message--error" role="alert">
          {input.erro}
        </p>
      ) : null}

      {input.sucesso === "mandato-publicado" ? (
        <p className="private-message private-message--success" role="status">
          Mandato publicado com revisão própria e histórico append-only.
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Uma data observada não é uma conclusão jurídica</strong>
        <p>
          O sistema exige DepId, identidade já publicada, círculo com identificador oficial, fonte
          arquivada e um intervalo coerente. Não preenche datas, partidos ou cargos em falta.
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
            placeholder="Nome observado ou DepId exato"
          />
        </label>
        <button className="button" type="submit">Consultar</button>
        <Link href="/admin/revisao/parlamento/deputados/mandatos">Limpar</Link>
      </form>

      <p className="admin-form-help" aria-live="polite">
        {catalogue.total.toLocaleString("pt-PT")} intervalo(s) nesta consulta. {catalogue.search_rule}
      </p>

      {catalogue.items.length ? (
        <section className="parliament-snapshot-list" aria-label="Candidatos privados a mandato">
          {catalogue.items.map((candidate) => (
            <MandateCandidateCard
              candidate={candidate}
              key={`${candidate.observation_id}-${candidate.source_period_sha256}`}
              isAdmin={staff.role === "ADMIN"}
              publicationPreview={
                candidate.existing_case
                  ? (publicationPreviews.get(candidate.existing_case.id) ?? null)
                  : null
              }
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem intervalos oficiais para estes filtros.</strong>
          <p>A ausência permanece dados indisponíveis e não prova ausência de mandato.</p>
        </section>
      )}

      <nav className="admin-heading-actions" aria-label="Paginação dos candidatos a mandato">
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

function MandateCandidateCard({
  candidate,
  publicationPreview,
  isAdmin,
}: {
  candidate: PoliticianMandateEditorialCandidate;
  publicationPreview: PoliticianMandatePublicationPreview | null;
  isAdmin: boolean;
}) {
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
          {candidate.proposal_eligible ? "Pronto para revisão" : "Candidato bloqueado"}
        </span>
      </header>

      <section className="parliament-proof-grid" aria-label="Prova do intervalo oficial">
        <dl>
          <div><dt>DepId oficial</dt><dd><code>{candidate.official_deputy_id}</code></dd></div>
          <div><dt>Situação declarada</dt><dd>{candidate.source_period.description}</dd></div>
          <div><dt>Início observado</dt><dd>{formatDate(candidate.source_period.starts_at)}</dd></div>
          <div><dt>Fim observado</dt><dd>{formatDate(candidate.source_period.ends_at)}</dd></div>
          <div><dt>Círculo</dt><dd>{candidate.constituency.label ?? "Dados indisponíveis"}</dd></div>
          <div>
            <dt>Identidade publicada</dt>
            <dd>{candidate.identity_publication_ready ? "Confirmada" : "Dados indisponíveis"}</dd>
          </div>
          <div><dt>SHA-256 do intervalo</dt><dd><code>{candidate.source_period_sha256}</code></dd></div>
          <div><dt>SHA-256 da fonte</dt><dd><code>{candidate.source.content_sha256}</code></dd></div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Arquivo oficial atestado</strong>
          <span>{candidate.archive.byte_size.toLocaleString("pt-PT")} bytes</span>
          <a
            className="button"
            href={candidate.source.url}
            target="_blank"
            rel="noreferrer noopener"
          >
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
        <>
          <section className="parliament-proposal-card parliament-proposal-card--existing">
            <p className="eyebrow">Mandato</p>
            <h3>Processo já existente</h3>
            <p>
              {STATE_LABELS[candidate.existing_case.state]} · revisão {candidate.existing_case.revision}
            </p>
            <Link className="button" href={`/admin/revisao/${candidate.existing_case.id}`}>
              Abrir processo
            </Link>
          </section>
          {candidate.existing_case.state === "APPROVED" ? (
            <MandatePublicationAction
              candidate={candidate}
              preview={publicationPreview}
              isAdmin={isAdmin}
            />
          ) : null}
        </>
      ) : (
        <form action={createPoliticianMandateProposal} className="parliament-proposal-card">
          <input type="hidden" name="observation_id" value={candidate.observation_id} />
          <input type="hidden" name="source_period_sha256" value={candidate.source_period_sha256} />
          <input type="hidden" name="legislature" value={candidate.legislature} />
          <p className="eyebrow">Mandato datado</p>
          <h3>Criar proposta PENDING</h3>
          <p>A proposta continua privada e não cria qualquer linha na cronologia pública.</p>
          <label className="admin-confirmation">
            <input name="confirm_private_only" type="checkbox" required />
            <span>Confirmo que esta proposta permanece privada.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_exact_official_id_only" type="checkbox" required />
            <span>Confirmo que a identidade usa apenas o DepId oficial exato.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_period_semantics_require_human_review" type="checkbox" required />
            <span>Confirmo que as datas exigem interpretação e revisão humana próprias.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_party_inference" type="checkbox" required />
            <span>Confirmo que não será inferida filiação por nome ou sigla.</span>
          </label>
          <button
            className="button button--primary"
            type="submit"
            disabled={!candidate.proposal_eligible}
          >
            Enviar intervalo para revisão privada
          </button>
        </form>
      )}
    </article>
  );
}

function MandatePublicationAction({
  candidate,
  preview,
  isAdmin,
}: {
  candidate: PoliticianMandateEditorialCandidate;
  preview: PoliticianMandatePublicationPreview | null;
  isAdmin: boolean;
}) {
  if (!preview) {
    return (
      <section className="parliament-proposal-card">
        <strong>Prova de publicação indisponível.</strong>
        <p>O processo continua aprovado e privado; nenhuma ação pública é apresentada.</p>
      </section>
    );
  }
  return (
    <form
      action={publishPoliticianMandate}
      className="parliament-proposal-card parliament-publication-card"
    >
      <input type="hidden" name="legislature" value={candidate.legislature} />
      <input type="hidden" name="expected_case_id" value={preview.case_id} />
      <input type="hidden" name="expected_version_id" value={preview.version_id} />
      <input type="hidden" name="expected_version_sha256" value={preview.version_sha256} />
      <input type="hidden" name="expected_source_sha256" value={preview.source.content_sha256} />
      <input
        type="hidden"
        name="expected_period_sha256"
        value={preview.source_period_sha256}
      />
      <input
        type="hidden"
        name="expected_publication_proof_sha256"
        value={preview.publication_proof_sha256 ?? ""}
      />
      <div>
        <p className="eyebrow">V5.34 · porta pública específica</p>
        <h3>Publicar um mandato revisto</h3>
        <p>{preview.publication_rule}</p>
      </div>
      <dl>
        <div><dt>Mandatos a criar</dt><dd>{preview.public_effect.mandates_to_create}</dd></div>
        <div><dt>Revisões MANDATE</dt><dd>{preview.public_effect.mandate_reviews_to_append}</dd></div>
        <div><dt>Pessoas a criar</dt><dd>{preview.public_effect.people_to_create}</dd></div>
        <div><dt>Ligações partidárias</dt><dd>{preview.public_effect.party_links_to_create}</dd></div>
      </dl>
      {preview.blockers.length ? (
        <ul className="parliament-limitations">
          {preview.blockers.map((blocker) => <li key={blocker.code}>{blocker.detail}</li>)}
        </ul>
      ) : null}
      <label>
        Fundamentação editorial privada
        <textarea name="rationale" minLength={20} maxLength={1850} required />
      </label>
      <label>
        Fundamentação pública factual
        <textarea name="public_rationale" minLength={20} maxLength={500} required />
      </label>
      <label className="admin-confirmation">
        <input name="confirm_source_reviewed" type="checkbox" required />
        <span>Voltei a comparar a fonte oficial, o arquivo e os SHA-256.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_human_period_interpretation" type="checkbox" required />
        <span>Confirmo humanamente que este intervalo representa o mandato indicado.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_exact_official_id_only" type="checkbox" required />
        <span>Confirmo a correspondência exclusiva pelo DepId oficial exato.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_no_party_inference" type="checkbox" required />
        <span>Confirmo que nenhuma filiação partidária será inferida.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_append_only_publication" type="checkbox" required />
        <span>Confirmo que correções e retiradas acrescentam histórico, sem apagar esta versão.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_publication" type="checkbox" required />
        <span>Confirmo a publicação deste mandato e da sua prova.</span>
      </label>
      {!isAdmin ? <p>A publicação exige uma conta ADMIN com MFA.</p> : null}
      <button
        className="button button--primary"
        type="submit"
        disabled={!isAdmin || !preview.eligible || !preview.publication_proof_sha256}
      >
        Publicar mandato com prova
      </button>
      <p className="admin-form-help">
        A ativação em ambiente real continua bloqueada até a V5.35 provar a retirada imutável.
      </p>
    </form>
  );
}
