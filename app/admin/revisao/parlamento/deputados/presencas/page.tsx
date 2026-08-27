import Link from "next/link";
import {
  createPoliticianAttendanceProposal,
  publishPoliticianAttendance,
  withdrawPoliticianAttendance,
} from "../../../actions";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
import {
  PARLIAMENT_WITHDRAWAL_REASON_LABELS,
  type PoliticianAttendanceWithdrawalPreview,
  PoliticianAttendanceEditorialCandidate,
  PoliticianAttendanceEditorialCandidateList,
  PoliticianAttendancePublicationPreview,
} from "@/lib/editorial-types";

const withdrawalReasonEntries = Object.entries(PARLIAMENT_WITHDRAWAL_REASON_LABELS);

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "long",
  timeZone: "Europe/Lisbon",
});

function boundedOffset(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "0", 10);
  return Number.isSafeInteger(parsed) && parsed >= 0 && parsed <= 10_000 ? parsed : 0;
}

function pageHref(legislature: string, offset: number): string {
  const params = new URLSearchParams({ legislature, offset: String(offset) });
  return `/admin/revisao/parlamento/deputados/presencas?${params.toString()}`;
}

function meetingDate(value: string): string {
  return dateFormatter.format(new Date(`${value}T12:00:00Z`));
}

function safeOfficialSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

async function loadPublicationPreview(
  caseId: string,
): Promise<PoliticianAttendancePublicationPreview | null> {
  try {
    return await editorialFetch<PoliticianAttendancePublicationPreview>(
      `/parliament/attendance-cases/${encodeURIComponent(caseId)}/publication`,
    );
  } catch {
    return null;
  }
}

async function loadWithdrawalPreview(
  caseId: string,
): Promise<PoliticianAttendanceWithdrawalPreview | null> {
  try {
    return await editorialFetch<PoliticianAttendanceWithdrawalPreview>(
      `/parliament/attendance-cases/${encodeURIComponent(caseId)}/withdrawal`,
    );
  } catch {
    return null;
  }
}

export default async function PoliticianAttendanceEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{
    legislature?: string;
    offset?: string;
    erro?: string;
    sucesso?: string;
  }>;
}) {
  const input = await searchParams;
  const legislature = (input.legislature?.trim() || "XVII").slice(0, 20);
  const offset = boundedOffset(input.offset);
  const limit = 10;
  const params = new URLSearchParams({
    legislature,
    limit: String(limit),
    offset: String(offset),
  });
  const [catalogue, { staff }] = await Promise.all([
    editorialFetch<PoliticianAttendanceEditorialCandidateList>(
      `/parliament/attendance-candidates?${params.toString()}`,
    ),
    getEditorialContext(),
  ]);
  const publicationPreviews = new Map<string, PoliticianAttendancePublicationPreview>();
  const withdrawalPreviews = new Map<string, PoliticianAttendanceWithdrawalPreview>();
  await Promise.all(
    catalogue.items.map(async (candidate) => {
      if (candidate.existing_case?.state === "APPROVED") {
        const preview = await loadPublicationPreview(candidate.existing_case.id);
        if (preview) publicationPreviews.set(candidate.existing_case.id, preview);
      } else if (candidate.existing_case?.state === "PUBLISHED") {
        const preview = await loadWithdrawalPreview(candidate.existing_case.id);
        if (preview) withdrawalPreviews.set(candidate.existing_case.id, preview);
      }
    }),
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.41 · presenças por reunião oficial</p>
          <h1>Rever a fotografia completa de cada reunião</h1>
          <p>
            Cada proposta contém todos os registos que a Assembleia publicou para a reunião. A
            revisão é privada e nunca publica, omite ou associa um deputado isoladamente.
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
      {input.sucesso ? (
        <p className="private-message private-message--success" role="status">
          {input.sucesso === "reuniao-retirada"
            ? "A reunião saiu da consulta ativa; sessão, presenças e histórico foram preservados."
            : "A reunião integral e a respetiva prova foram publicadas sem criar pessoas, mandatos ou filiações."}
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Presença não mede mérito; falta não prova incumprimento</strong>
        <p>
          O estado é reproduzido da fonte oficial para uma reunião concreta. Não conclui se houve
          trabalho parlamentar noutro contexto, não atribui culpa e não usa nomes para ligar
          identidades. Só o BID oficial exato pode sustentar uma ligação futura.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Legislatura
          <input name="legislature" defaultValue={legislature} maxLength={20} required />
        </label>
        <button className="button" type="submit">Consultar</button>
        <Link href="/admin/revisao/parlamento/deputados/presencas">Limpar</Link>
      </form>

      <p className="admin-form-help" aria-live="polite">
        {catalogue.total.toLocaleString("pt-PT")} reunião(ões) privada(s). {catalogue.selection_rule}
      </p>

      {catalogue.items.length ? (
        <section className="parliament-snapshot-list" aria-label="Reuniões privadas de presenças">
          {catalogue.items.map((candidate) => (
            <AttendanceCandidateCard
              candidate={candidate}
              isAdmin={staff.role === "ADMIN"}
              key={candidate.snapshot_id}
              publicationPreview={
                candidate.existing_case
                  ? publicationPreviews.get(candidate.existing_case.id) ?? null
                  : null
              }
              withdrawalPreview={
                candidate.existing_case
                  ? withdrawalPreviews.get(candidate.existing_case.id) ?? null
                  : null
              }
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <h2>Dados indisponíveis</h2>
          <p>
            Ainda não existe uma reunião desta legislatura recolhida, arquivada, atestada e
            normalizada na área privada.
          </p>
        </section>
      )}

      <nav className="admin-pagination" aria-label="Paginação das reuniões">
        {offset > 0 ? (
          <Link href={pageHref(legislature, Math.max(0, offset - limit))}>Anterior</Link>
        ) : (
          <span>Anterior</span>
        )}
        <span>Página {Math.floor(offset / limit) + 1}</span>
        {catalogue.next_offset !== null ? (
          <Link href={pageHref(legislature, catalogue.next_offset)}>Seguinte</Link>
        ) : (
          <span>Seguinte</span>
        )}
      </nav>
    </div>
  );
}

function AttendanceCandidateCard({
  candidate,
  publicationPreview,
  withdrawalPreview,
  isAdmin,
}: {
  candidate: PoliticianAttendanceEditorialCandidate;
  publicationPreview: PoliticianAttendancePublicationPreview | null;
  withdrawalPreview: PoliticianAttendanceWithdrawalPreview | null;
  isAdmin: boolean;
}) {
  const counts = candidate.materialised_counts;
  const reconciliation = candidate.identity_reconciliation;
  const officialUrl = safeOfficialSourceUrl(candidate.source.url);

  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">Reunião {candidate.session_number ?? "sem número publicado"}</p>
          <h2>{candidate.meeting_type} · {meetingDate(candidate.meeting_date)}</h2>
          <p>Legislatura {candidate.legislature} · BID da reunião {candidate.official_meeting_id}</p>
        </div>
        <span
          className={
            candidate.publication_ready
              ? "status-badge status-badge--fulfilled"
              : "status-badge status-badge--in_progress"
          }
        >
          {candidate.publication_ready ? "Prova pública completa" : "Só revisão privada"}
        </span>
      </header>

      <dl className="parliament-count-grid">
        <div><dt>Registos</dt><dd>{counts.records}</dd></div>
        <div><dt>Presenças</dt><dd>{counts.present}</dd></div>
        <div><dt>Faltas justificadas</dt><dd>{counts.justified_absence}</dd></div>
        <div><dt>Outras faltas</dt><dd>{counts.unjustified_absence}</dd></div>
        <div><dt>Estados desconhecidos</dt><dd>{counts.unknown}</dd></div>
        <div><dt>Identidades exatas e revistas</dt><dd>{reconciliation.reviewed_identities}/{counts.records}</dd></div>
        <div><dt>Mandatos exatos e revistos</dt><dd>{reconciliation.reviewed_covering_mandates}/{counts.records}</dd></div>
      </dl>

      <section className="parliament-proof-grid" aria-label="Fonte e prova da reunião">
        <dl>
          <div><dt>Fonte</dt><dd>Assembleia da República</dd></div>
          <div><dt>Recolha</dt><dd>{candidate.source.retrieved_at}</dd></div>
          <div><dt>SHA-256 do documento</dt><dd><code>{candidate.source.content_sha256}</code></dd></div>
          <div><dt>Atestação do arquivo</dt><dd><code>{candidate.archive.attestation_sha256}</code></dd></div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Documento oficial preservado</strong>
          <span>O URL e os hashes serão repetidos antes de qualquer decisão.</span>
          {officialUrl ? (
            <a className="button" href={officialUrl} rel="noreferrer" target="_blank">
              Abrir reunião oficial
            </a>
          ) : (
            <span>URL oficial indisponível</span>
          )}
        </div>
      </section>

      {candidate.warnings.length ? (
        <ul className="parliament-limitations">
          {candidate.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      ) : null}

      {candidate.publication_blockers.length ? (
        <details className="parliament-limitations" open>
          <summary>Uma futura publicação permanece bloqueada</summary>
          <ul>
            {candidate.publication_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
          </ul>
        </details>
      ) : null}

      {candidate.existing_case ? (
        <>
          <div className="parliament-proposal-card parliament-proposal-card--existing">
            <strong>Processo editorial já existente</strong>
            <p>Estado: {candidate.existing_case.state} · revisão {candidate.existing_case.revision}</p>
            <Link href={`/admin/revisao/${candidate.existing_case.id}`}>Abrir processo</Link>
          </div>
          {candidate.existing_case.state === "APPROVED" ? (
            <AttendancePublicationAction
              candidate={candidate}
              isAdmin={isAdmin}
              preview={publicationPreview}
            />
          ) : null}
          {candidate.existing_case.state === "PUBLISHED" ? (
            <AttendanceWithdrawalAction
              candidate={candidate}
              isAdmin={isAdmin}
              preview={withdrawalPreview}
            />
          ) : null}
        </>
      ) : candidate.proposal_eligible ? (
        <AttendanceProposalForm candidate={candidate} />
      ) : (
        <div className="parliament-proposal-card">
          <strong>Proposta indisponível</strong>
          <ul className="parliament-limitations">
            {candidate.blocked_reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </div>
      )}
    </article>
  );
}

function AttendancePublicationAction({
  candidate,
  preview,
  isAdmin,
}: {
  candidate: PoliticianAttendanceEditorialCandidate;
  preview: PoliticianAttendancePublicationPreview | null;
  isAdmin: boolean;
}) {
  if (!preview) {
    return (
      <section className="parliament-proposal-card">
        <strong>Prova de publicação indisponível.</strong>
        <p>A reunião continua aprovada e privada; nenhuma publicação é apresentada sem prova.</p>
      </section>
    );
  }
  return (
    <form
      action={publishPoliticianAttendance}
      className="parliament-proposal-card parliament-publication-card"
    >
      <input type="hidden" name="legislature" value={candidate.legislature} />
      <input type="hidden" name="expected_case_id" value={preview.case_id} />
      <input type="hidden" name="expected_version_id" value={preview.version_id} />
      <input type="hidden" name="expected_version_sha256" value={preview.version_sha256} />
      <input type="hidden" name="expected_source_sha256" value={preview.source.content_sha256} />
      <input type="hidden" name="expected_snapshot_sha256" value={preview.snapshot_sha256} />
      <input
        type="hidden"
        name="expected_mapping_sha256"
        value={preview.mapping_sha256 ?? ""}
      />
      <input
        type="hidden"
        name="expected_publication_proof_sha256"
        value={preview.publication_proof_sha256 ?? ""}
      />
      <input
        type="hidden"
        name="expected_record_count"
        value={preview.public_effect.attendance_records_to_create}
      />
      <div>
        <p className="eyebrow">Porta pública por reunião integral</p>
        <h3>Publicar todas as presenças desta reunião</h3>
        <p>{preview.publication_rule}</p>
      </div>
      <dl>
        <div><dt>Sessões a criar</dt><dd>{preview.public_effect.sessions_to_create}</dd></div>
        <div><dt>Linhas de presença</dt><dd>{preview.public_effect.attendance_records_to_create}</dd></div>
        <div><dt>Pessoas a criar</dt><dd>{preview.public_effect.people_to_create}</dd></div>
        <div><dt>Mandatos a criar</dt><dd>{preview.public_effect.mandates_to_create}</dd></div>
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
        <span>Voltei a comparar a fonte, o arquivo e todos os SHA-256.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_complete_meeting" type="checkbox" required />
        <span>Confirmo que a fotografia inclui a reunião completa, sem seleção individual.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_exact_official_ids_and_mandates_only" type="checkbox" required />
        <span>Confirmo cada BID exato e exatamente um mandato revisto para a data.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_all_statuses_reviewed" type="checkbox" required />
        <span>Comparei humanamente todos os estados e confirmei zero UNKNOWN.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_absence_is_not_noncompliance" type="checkbox" required />
        <span>Confirmo que uma falta não será apresentada como culpa ou incumprimento.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_append_only_publication" type="checkbox" required />
        <span>Confirmo que correções e retiradas só acrescentam histórico.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_publication" type="checkbox" required />
        <span>Confirmo a publicação desta reunião integral e da sua prova.</span>
      </label>
      {!isAdmin ? <p>A publicação exige uma conta ADMIN com MFA.</p> : null}
      <button
        className="button button--primary"
        type="submit"
        disabled={!isAdmin || !preview.eligible || !preview.publication_proof_sha256}
      >
        Publicar reunião completa com prova
      </button>
      <p className="admin-form-help">
        A operação não cria pessoas, mandatos ou filiações e será revertida por inteiro perante
        qualquer divergência.
      </p>
    </form>
  );
}

function AttendanceWithdrawalAction({
  candidate,
  preview,
  isAdmin,
}: {
  candidate: PoliticianAttendanceEditorialCandidate;
  preview: PoliticianAttendanceWithdrawalPreview | null;
  isAdmin: boolean;
}) {
  if (!preview) {
    return (
      <section className="parliament-proposal-card">
        <strong>Prova de retirada indisponível.</strong>
        <p>A reunião permanece publicada; nenhuma retirada avança sem prova integral.</p>
      </section>
    );
  }

  return (
    <form
      action={withdrawPoliticianAttendance}
      className="parliament-proposal-card parliament-publication-card admin-withdrawal-panel"
    >
      <input type="hidden" name="legislature" value={candidate.legislature} />
      <input type="hidden" name="expected_case_id" value={preview.case_id} />
      <input type="hidden" name="expected_revision" value={preview.case_revision} />
      <input type="hidden" name="expected_version_id" value={preview.version_id} />
      <input type="hidden" name="expected_version_sha256" value={preview.version_sha256} />
      <input type="hidden" name="expected_snapshot_id" value={preview.snapshot_id} />
      <input type="hidden" name="expected_source_sha256" value={preview.source.content_sha256} />
      <input type="hidden" name="expected_snapshot_sha256" value={preview.snapshot_sha256} />
      <input type="hidden" name="expected_mapping_sha256" value={preview.mapping_sha256 ?? ""} />
      <input
        type="hidden"
        name="expected_publication_proof_sha256"
        value={preview.publication_proof_sha256 ?? ""}
      />
      <input
        type="hidden"
        name="expected_withdrawal_proof_sha256"
        value={preview.withdrawal_proof_sha256 ?? ""}
      />
      <input type="hidden" name="expected_public_review_id" value={preview.public_review_id} />
      <input
        type="hidden"
        name="expected_publication_audit_event_id"
        value={preview.publication_audit_event_id}
      />
      <input
        type="hidden"
        name="expected_publication_event_id"
        value={preview.publication_event_id}
      />
      <input
        type="hidden"
        name="expected_publication_event_sha256"
        value={preview.publication_event_sha256}
      />
      <input
        type="hidden"
        name="expected_public_effect_sha256"
        value={preview.public_effect_sha256}
      />
      <input type="hidden" name="expected_record_count" value={preview.record_count} />

      <div>
        <p className="eyebrow">V5.41 · retirada imutável da reunião integral</p>
        <h3>Retirar toda a reunião da consulta ativa</h3>
        <p>{preview.withdrawal_rule}</p>
      </div>
      <dl>
        <div><dt>Sessões a eliminar</dt><dd>{preview.sessions_to_delete}</dd></div>
        <div><dt>Presenças a eliminar</dt><dd>{preview.attendance_records_to_delete}</dd></div>
        <div><dt>Linhas preservadas</dt><dd>{preview.public_effect.attendance_records_preserved}</dd></div>
        <div>
          <dt>Outras reuniões públicas na legislatura</dt>
          <dd>{preview.public_effect.remaining_public_attendance_meetings_in_legislature}</dd>
        </div>
      </dl>
      <p>{preview.public_effect.message}</p>
      <div className="admin-proof-callout">
        <strong>SHA-256 da prova de retirada</strong>
        <code>{preview.withdrawal_proof_sha256 ?? "dados indisponíveis"}</code>
        <strong>SHA-256 do efeito público</strong>
        <code>{preview.public_effect_sha256}</code>
      </div>
      {preview.blockers.length ? (
        <ul className="parliament-limitations">
          {preview.blockers.map((blocker) => <li key={blocker.code}>{blocker.detail}</li>)}
        </ul>
      ) : null}
      <label>
        Categoria permitida pela governação
        <select name="reason_category" required defaultValue="">
          <option value="" disabled>Selecione um fundamento</option>
          {withdrawalReasonEntries.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Fundamentação editorial privada
        <textarea name="rationale" minLength={20} maxLength={1850} required />
      </label>
      <label>
        Fundamentação pública factual
        <textarea name="public_rationale" minLength={20} maxLength={500} required />
      </label>
      <label className="admin-confirmation">
        <input name="confirm_source_and_publication_reviewed" type="checkbox" required />
        <span>Revi a fonte, a reunião, a publicação original e todos os SHA-256.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_complete_meeting" type="checkbox" required />
        <span>Confirmo que a retirada abrange a reunião inteira, sem escolher deputados.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_public_effect_reviewed" type="checkbox" required />
        <span>Revi o efeito que ficará visível ao público depois da retirada.</span>
      </label>
      <label className="admin-confirmation">
        <input
          name="confirm_session_records_and_history_preserved"
          type="checkbox"
          required
        />
        <span>Confirmo que sessão, presenças, fonte, versão e histórico permanecem.</span>
      </label>
      <label className="admin-confirmation">
        <input
          name="confirm_no_selective_person_or_mandate_change"
          type="checkbox"
          required
        />
        <span>Confirmo que pessoas, mandatos e filiações não serão alterados.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_absence_is_not_noncompliance" type="checkbox" required />
        <span>Confirmo que uma falta não é apresentada como culpa ou incumprimento.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_withdrawal" type="checkbox" required />
        <span>Confirmo a retirada integral desta reunião da consulta ativa.</span>
      </label>
      {!isAdmin ? <p>A retirada exige uma conta ADMIN com MFA.</p> : null}
      <button
        className="button button--danger"
        type="submit"
        disabled={!isAdmin || !preview.eligible || !preview.withdrawal_proof_sha256}
      >
        Retirar reunião e preservar todo o histórico
      </button>
    </form>
  );
}

function AttendanceProposalForm({
  candidate,
}: {
  candidate: PoliticianAttendanceEditorialCandidate;
}) {
  return (
    <form action={createPoliticianAttendanceProposal} className="parliament-proposal-card">
      <input type="hidden" name="snapshot_id" value={candidate.snapshot_id} />
      <input type="hidden" name="legislature" value={candidate.legislature} />
      <div>
        <p className="eyebrow">Proposta privada</p>
        <h3>Enviar a reunião completa para revisão</h3>
        <p>A ação cria um processo PENDING; cria zero presenças ou sessões públicas.</p>
      </div>
      <label className="admin-confirmation">
        <input name="confirm_private_only" type="checkbox" required />
        <span>Confirmo que a proposta permanece privada até nova operação explícita.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_complete_meeting" type="checkbox" required />
        <span>Comparei a reunião completa e as suas contagens com a fonte.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_exact_official_ids_only" type="checkbox" required />
        <span>Confirmo o uso exclusivo de BID oficiais exatos.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_no_name_matching" type="checkbox" required />
        <span>Confirmo que não existe correspondência por nome, aproximada ou manual.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_absence_is_not_noncompliance" type="checkbox" required />
        <span>Confirmo que uma falta não é convertida automaticamente em incumprimento.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_no_selective_processing" type="checkbox" required />
        <span>Confirmo que nenhum deputado será omitido ou processado isoladamente.</span>
      </label>
      <button className="button button--primary" type="submit">
        Criar processo privado da reunião
      </button>
    </form>
  );
}
