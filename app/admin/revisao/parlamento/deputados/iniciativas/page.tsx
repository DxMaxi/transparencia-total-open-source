import Link from "next/link";
import type { ReactNode } from "react";
import {
  createPoliticianInitiativeAuthorshipProposal,
  publishPoliticianInitiativeAuthorship,
} from "../../../actions";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type PoliticianInitiativeAuthorshipEditorialCandidate,
  type PoliticianInitiativeAuthorshipEditorialCandidateList,
  type PoliticianInitiativeAuthorshipPublicationPreview,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeZone: "Europe/Lisbon",
});

function boundedOffset(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "0", 10);
  return Number.isSafeInteger(parsed) && parsed >= 0 && parsed <= 10_000 ? parsed : 0;
}

function safeOfficialSourceUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    const officialHost =
      url.hostname === "parlamento.pt" || url.hostname.endsWith(".parlamento.pt");
    return url.protocol === "https:" && officialHost ? url.toString() : null;
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
  return `/admin/revisao/parlamento/deputados/iniciativas?${params.toString()}`;
}

async function loadPublicationPreview(
  caseId: string,
): Promise<PoliticianInitiativeAuthorshipPublicationPreview | null> {
  try {
    return await editorialFetch<PoliticianInitiativeAuthorshipPublicationPreview>(
      `/parliament/initiative-authorship-cases/${encodeURIComponent(caseId)}/publication`,
    );
  } catch {
    return null;
  }
}

export default async function PoliticianInitiativeAuthorshipEditorialPage({
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
  const catalogue = await editorialFetch<PoliticianInitiativeAuthorshipEditorialCandidateList>(
    `/parliament/initiative-authorship-candidates?${params.toString()}`,
  );
  const { staff } = await getEditorialContext();
  const publicationPreviews = new Map<
    string,
    PoliticianInitiativeAuthorshipPublicationPreview
  >();
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
          <p className="eyebrow">V5.42–V5.43 · autoria por prova oficial</p>
          <h1>Autoria individual de iniciativas</h1>
          <p>
            Compare a iniciativa, o autor declarado e o arquivo original. Enviar para revisão cria
            apenas um processo privado PENDING: não publica a ligação e não altera o perfil.
          </p>
        </div>
        <div className="admin-heading-actions">
          <Link href="/admin/revisao/parlamento/deputados">Voltar às fichas de deputados</Link>
          <Link href="/admin/revisao/parlamento/deputados/presencas">
            Rever presenças por reunião
          </Link>
          <Link href="/admin/revisao">Voltar à fila</Link>
        </div>
      </header>

      {input.erro ? (
        <p className="private-message private-message--error" role="alert">
          {input.erro}
        </p>
      ) : null}
      {input.sucesso === "autoria-publicada" ? (
        <p className="private-message private-message--success" role="status">
          A autoria exata foi publicada com duas fontes revistas e histórico imutável.
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>IniId + idCadastro exatos; nomes e siglas nunca ligam identidades</strong>
        <p>
          A autoria é o que a fonte declara para esta iniciativa. Não demonstra sentido de voto,
          apoio posterior, mérito, posição coletiva do partido ou qualquer consequência política.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Legislatura
          <input name="legislature" defaultValue={legislature} maxLength={20} required />
        </label>
        <label>
          Filtrar relações observadas
          <input
            name="q"
            defaultValue={query}
            minLength={2}
            maxLength={100}
            placeholder="Número, título, IniId, nome observado ou idCadastro"
          />
        </label>
        <button className="button" type="submit">
          Consultar
        </button>
        <Link href="/admin/revisao/parlamento/deputados/iniciativas">Limpar</Link>
      </form>

      <p className="admin-form-help" aria-live="polite">
        {catalogue.total.toLocaleString("pt-PT")} relação(ões) privadas nesta consulta. {catalogue.search_rule}
      </p>

      {catalogue.items.length ? (
        <section className="parliament-snapshot-list" aria-label="Autorias oficiais observadas">
          {catalogue.items.map((candidate) => (
            <CandidateCard
              candidate={candidate}
              publicationPreview={
                candidate.existing_case
                  ? publicationPreviews.get(candidate.existing_case.id) ?? null
                  : null
              }
              isAdmin={staff.role === "ADMIN"}
              key={candidate.observation_id}
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem relações atestadas para estes filtros.</strong>
          <p>Dados indisponíveis não significam ausência de autoria nem incumprimento.</p>
        </section>
      )}

      <nav className="admin-heading-actions" aria-label="Paginação das autorias">
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

function CandidateCard({
  candidate,
  publicationPreview,
  isAdmin,
}: {
  candidate: PoliticianInitiativeAuthorshipEditorialCandidate;
  publicationPreview: PoliticianInitiativeAuthorshipPublicationPreview | null;
  isAdmin: boolean;
}) {
  const sourceUrl = safeOfficialSourceUrl(candidate.source.url);
  const initiativeUrl = safeOfficialSourceUrl(candidate.initiative.official_url);
  const identityLabel = candidate.identity_reconciliation.exact_identity
    ? candidate.identity_reconciliation.reviewed_identity
      ? "Identidade exata e revista"
      : "Identidade exata por rever"
    : "Identidade pública indisponível";
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">
            {candidate.initiative.type ?? "Tipo: dados indisponíveis"} · legislatura {candidate.legislature}
          </p>
          <h2>{candidate.initiative.title ?? "Título: dados indisponíveis"}</h2>
          <p>{candidate.initiative.number ?? `IniId ${candidate.initiative_source_id}`}</p>
        </div>
        <span
          className={`admin-state ${candidate.proposal_eligible ? "state-approved" : "state-rejected"}`}
        >
          {candidate.proposal_eligible ? "Prova confirmada" : "Proposta bloqueada"}
        </span>
      </header>

      <section className="parliament-proof-grid" aria-label="Relação e prova oficial">
        <dl>
          <div>
            <dt>Autor declarado</dt>
            <dd>{candidate.parliamentary_name}</dd>
          </div>
          <div>
            <dt>Relação literal</dt>
            <dd>Autor</dd>
          </div>
          <div>
            <dt>IniId oficial</dt>
            <dd><code>{candidate.initiative_source_id}</code></dd>
          </div>
          <div>
            <dt>idCadastro oficial</dt>
            <dd><code>{candidate.official_deputy_id}</code></dd>
          </div>
          <div>
            <dt>Grupo na fonte</dt>
            <dd>{candidate.parliamentary_group_label ?? "Dados indisponíveis"}</dd>
          </div>
          <div>
            <dt>Reconciliação</dt>
            <dd>{identityLabel}</dd>
          </div>
          <div>
            <dt>Recolhida</dt>
            <dd>{dateFormatter.format(new Date(candidate.source.retrieved_at))}</dd>
          </div>
          <div>
            <dt>SHA-256 da relação</dt>
            <dd><code>{candidate.source_record_sha256}</code></dd>
          </div>
          <div>
            <dt>SHA-256 da fonte</dt>
            <dd><code>{candidate.source.content_sha256}</code></dd>
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
          {initiativeUrl ? (
            <a className="button" href={initiativeUrl} target="_blank" rel="noreferrer noopener">
              Abrir iniciativa oficial
            </a>
          ) : null}
          {sourceUrl ? (
            <a className="button" href={sourceUrl} target="_blank" rel="noreferrer noopener">
              Abrir ficheiro oficial
            </a>
          ) : (
            <span>URL oficial indisponível</span>
          )}
        </div>
      </section>

      <details className="parliament-limitations">
        <summary>Limitações, bloqueios e cobertura</summary>
        <ul>
          {candidate.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          {candidate.blocked_reasons.map((reason) => <li key={reason}>{reason}</li>)}
          {candidate.publication_blockers.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      </details>

      {candidate.existing_case ? (
        <>
          <section className="parliament-proposal-card parliament-proposal-card--existing">
            <p className="eyebrow">Autoria individual</p>
            <h3>Processo já existente</h3>
            <p>
              {STATE_LABELS[candidate.existing_case.state]} · revisão {candidate.existing_case.revision}
            </p>
            <Link className="button" href={`/admin/revisao/${candidate.existing_case.id}`}>
              Abrir processo
            </Link>
          </section>
          {candidate.existing_case.state === "APPROVED" ? (
            <AuthorshipPublicationAction
              candidate={candidate}
              preview={publicationPreview}
              isAdmin={isAdmin}
            />
          ) : null}
        </>
      ) : (
        <form
          action={createPoliticianInitiativeAuthorshipProposal}
          className="parliament-proposal-card"
        >
          <input type="hidden" name="observation_id" value={candidate.observation_id} />
          <input
            type="hidden"
            name="source_record_sha256"
            value={candidate.source_record_sha256}
          />
          <input type="hidden" name="legislature" value={candidate.legislature} />
          <p className="eyebrow">Autoria individual</p>
          <h3>Criar proposta PENDING</h3>
          <p>O servidor volta a construir a proposta a partir da relação e do arquivo atestado.</p>
          <Confirmation name="confirm_private_only">
            Confirmo que esta proposta permanece privada.
          </Confirmation>
          <Confirmation name="confirm_exact_initiative_id">
            Confirmo que a iniciativa é ligada apenas pelo IniId oficial exato.
          </Confirmation>
          <Confirmation name="confirm_exact_official_deputy_id">
            Confirmo que a identidade depende apenas do idCadastro oficial exato.
          </Confirmation>
          <Confirmation name="confirm_official_author_relation">
            Confirmo que a relação apresentada é literalmente autoria declarada pela fonte.
          </Confirmation>
          <Confirmation name="confirm_no_name_or_party_matching">
            Confirmo que nome e sigla partidária não servem para correspondência.
          </Confirmation>
          <Confirmation name="confirm_no_collective_position_inference">
            Confirmo que autoria não prova voto, apoio ou posição coletiva do partido.
          </Confirmation>
          <button
            className="button button--primary"
            type="submit"
            disabled={!candidate.proposal_eligible}
          >
            Enviar autoria para a fila privada
          </button>
        </form>
      )}
    </article>
  );
}

function AuthorshipPublicationAction({
  candidate,
  preview,
  isAdmin,
}: {
  candidate: PoliticianInitiativeAuthorshipEditorialCandidate;
  preview: PoliticianInitiativeAuthorshipPublicationPreview | null;
  isAdmin: boolean;
}) {
  if (!preview || !preview.initiative) {
    return (
      <section className="parliament-proposal-card">
        <strong>Prova de publicação indisponível.</strong>
        <p>
          O processo continua aprovado e privado. Pode faltar a identidade revista ou uma
          fotografia pública que contenha exatamente este IniId.
        </p>
      </section>
    );
  }
  return (
    <form
      action={publishPoliticianInitiativeAuthorship}
      className="parliament-proposal-card parliament-publication-card"
    >
      <input type="hidden" name="legislature" value={candidate.legislature} />
      <input type="hidden" name="expected_case_id" value={preview.case_id} />
      <input type="hidden" name="expected_version_id" value={preview.version_id} />
      <input type="hidden" name="expected_version_sha256" value={preview.version_sha256} />
      <input type="hidden" name="expected_source_sha256" value={preview.source.content_sha256} />
      <input
        type="hidden"
        name="expected_source_record_sha256"
        value={preview.source_record_sha256}
      />
      <input
        type="hidden"
        name="expected_activity_snapshot_sha256"
        value={preview.initiative.activity_snapshot_sha256}
      />
      <input
        type="hidden"
        name="expected_publication_proof_sha256"
        value={preview.publication_proof_sha256 ?? ""}
      />
      <div>
        <p className="eyebrow">V5.43 · porta pública específica</p>
        <h3>Publicar autoria individual</h3>
        <p>{preview.publication_rule}</p>
      </div>
      <dl>
        <div><dt>Autorias a criar</dt><dd>{preview.public_effect.authorships_to_create}</dd></div>
        <div><dt>Pessoas a criar</dt><dd>{preview.public_effect.people_to_create}</dd></div>
        <div><dt>Iniciativas a criar</dt><dd>{preview.public_effect.initiatives_to_create}</dd></div>
        <div><dt>Ligações partidárias</dt><dd>{preview.public_effect.party_links_to_create}</dd></div>
      </dl>
      <div className="admin-proof-callout">
        <strong>Iniciativa pública revista</strong>
        <span>{preview.initiative.number} · {preview.initiative.title}</span>
        <code>{preview.initiative.activity_snapshot_sha256}</code>
        <strong>SHA-256 da prova de publicação</strong>
        <code>{preview.publication_proof_sha256 ?? "dados indisponíveis"}</code>
      </div>
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
      <Confirmation name="confirm_source_reviewed">
        Voltei a comparar as fontes de autoria e da iniciativa pública, os arquivos e os hashes.
      </Confirmation>
      <Confirmation name="confirm_exact_official_ids_only">
        Confirmo o uso exclusivo do IniId e do idCadastro oficiais exatos.
      </Confirmation>
      <Confirmation name="confirm_official_author_relation">
        Confirmo que a fonte declara literalmente esta pessoa como AUTHOR.
      </Confirmation>
      <Confirmation name="confirm_public_initiative_reviewed">
        Confirmo que a iniciativa pertence a uma fotografia pública revista.
      </Confirmation>
      <Confirmation name="confirm_no_name_or_party_matching">
        Confirmo que nome e sigla partidária não criaram nenhuma correspondência.
      </Confirmation>
      <Confirmation name="confirm_no_collective_position_inference">
        Confirmo que autoria não prova voto, apoio ou posição coletiva do partido.
      </Confirmation>
      <Confirmation name="confirm_append_only_publication">
        Confirmo que correções e retiradas acrescentarão histórico sem apagar esta prova.
      </Confirmation>
      <Confirmation name="confirm_publication">
        Confirmo a publicação desta autoria e destes SHA-256 exatos.
      </Confirmation>
      {!isAdmin ? <p>A publicação exige uma conta ADMIN com MFA.</p> : null}
      <button
        className="button button--primary"
        type="submit"
        disabled={!isAdmin || !preview.eligible || !preview.publication_proof_sha256}
      >
        Publicar autoria com prova
      </button>
    </form>
  );
}

function Confirmation({ name, children }: { name: string; children: ReactNode }) {
  return (
    <label className="admin-confirmation">
      <input name={name} type="checkbox" required />
      <span>{children}</span>
    </label>
  );
}
