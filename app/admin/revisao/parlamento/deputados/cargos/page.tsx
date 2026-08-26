import Link from "next/link";
import {
  createPoliticianOfficeProposal,
  publishPoliticianOffice,
} from "../../../actions";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type PoliticianOfficeEditorialCandidate,
  type PoliticianOfficeEditorialCandidateList,
  type PoliticianOfficePublicationPreview,
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

async function loadPublicationPreview(
  caseId: string,
): Promise<PoliticianOfficePublicationPreview | null> {
  try {
    return await editorialFetch<PoliticianOfficePublicationPreview>(
      `/parliament/office-cases/${encodeURIComponent(caseId)}/publication`,
    );
  } catch {
    return null;
  }
}

export default async function PoliticianOfficeEditorialPage({
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
  const catalogue = await editorialFetch<PoliticianOfficeEditorialCandidateList>(
    `/parliament/office-candidates?${params.toString()}`,
  );
  const { staff } = await getEditorialContext();
  const publicationPreviews = new Map<string, PoliticianOfficePublicationPreview>();
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
          <p className="eyebrow">V5.36–V5.37 · cargos parlamentares observados</p>
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

      {input.sucesso === "cargo-publicado" ? (
        <p className="private-message private-message--success" role="status">
          Cargo publicado com CarId, período, revisão própria e histórico append-only.
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

function OfficeCandidateCard({
  candidate,
  publicationPreview,
  isAdmin,
}: {
  candidate: PoliticianOfficeEditorialCandidate;
  publicationPreview: PoliticianOfficePublicationPreview | null;
  isAdmin: boolean;
}) {
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
        <>
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
          {candidate.existing_case.state === "APPROVED" ? (
            <OfficePublicationAction
              candidate={candidate}
              preview={publicationPreview}
              isAdmin={isAdmin}
            />
          ) : null}
        </>
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

function OfficePublicationAction({
  candidate,
  preview,
  isAdmin,
}: {
  candidate: PoliticianOfficeEditorialCandidate;
  preview: PoliticianOfficePublicationPreview | null;
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
      action={publishPoliticianOffice}
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
        <p className="eyebrow">V5.37 · porta pública específica</p>
        <h3>Publicar este cargo parlamentar</h3>
        <p>{preview.publication_rule}</p>
      </div>
      <dl>
        <div><dt>Cargos a criar</dt><dd>{preview.public_effect.offices_to_create}</dd></div>
        <div><dt>Revisões próprias</dt><dd>{preview.public_effect.office_reviews_to_append}</dd></div>
        <div><dt>Mandatos a criar</dt><dd>{preview.public_effect.mandates_to_create}</dd></div>
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
        <input name="confirm_human_office_interpretation" type="checkbox" required />
        <span>Confirmo humanamente o título e o período deste cargo.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_exact_official_ids_only" type="checkbox" required />
        <span>Confirmo as correspondências exclusivas pelos DepId e CarId oficiais.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_no_mandate_or_party_inference" type="checkbox" required />
        <span>Confirmo que não será criado mandato nem inferida filiação partidária.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_append_only_publication" type="checkbox" required />
        <span>Confirmo que correções e retiradas acrescentam histórico sem apagar esta versão.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_publication" type="checkbox" required />
        <span>Confirmo a publicação deste cargo e da respetiva prova.</span>
      </label>
      {!isAdmin ? <p>A publicação exige uma conta ADMIN com MFA.</p> : null}
      <button
        className="button button--primary"
        type="submit"
        disabled={!isAdmin || !preview.eligible || !preview.publication_proof_sha256}
      >
        Publicar cargo com prova
      </button>
      <p className="admin-form-help">
        A retirada append-only será acrescentada na V5.38 antes de qualquer ativação real em
        staging; esta ação nunca publica automaticamente.
      </p>
    </form>
  );
}
