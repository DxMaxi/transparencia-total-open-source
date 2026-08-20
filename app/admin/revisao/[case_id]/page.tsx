import Link from "next/link";
import {
  approveEditorialCase,
  correctEditorialCase,
  publishParliamentCase,
  regenerateAiDreProposal,
  rejectEditorialCase,
  startEditorialReview,
  withdrawParliamentCase,
} from "../actions";
import { AiEditorialComparison } from "../ai-comparison";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
import {
  KIND_LABELS,
  PARLIAMENT_WITHDRAWAL_REASON_LABELS,
  STATE_LABELS,
  type AiDreSourceEvidence,
  type EditorialCaseDetail,
  type ParliamentEditorialPublicationPreview,
  type ParliamentEditorialWithdrawalPreview,
  type StaffSession,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "long",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

const ACTION_LABELS: Record<string, string> = {
  SUBMIT: "Proposta criada",
  START_REVIEW: "Revisão iniciada",
  APPROVE: "Aprovação privada",
  REJECT: "Proposta rejeitada",
  CORRECT: "Nova versão corrigida",
  PUBLISH: "Publicação",
  WITHDRAW: "Retirada",
};

function safeOfficialSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function successMessage(value: string | undefined): string {
  if (value === "published") {
    return "O âmbito parlamentar foi publicado e todas as provas foram acrescentadas ao histórico.";
  }
  if (value === "withdrawn") {
    return "O âmbito foi retirado sem apagar a publicação, a versão ou os hashes anteriores.";
  }
  if (value === "ai-created") {
    return "A proposta de IA foi acrescentada em privado e aguarda revisão humana.";
  }
  if (value === "ai-existing") {
    return "A proposta exata já existia; nenhuma nova chamada ao modelo foi efetuada.";
  }
  if (value === "ai-regenerated") {
    return "A nova proposta de IA foi acrescentada como versão imutável; a anterior permanece no histórico.";
  }
  return "A decisão foi acrescentada ao histórico imutável.";
}

function sourceTextOffset(value: string | undefined): number {
  if (!value || !/^\d{1,9}$/.test(value)) return 0;
  const parsed = Number.parseInt(value, 10);
  return Number.isSafeInteger(parsed) ? parsed : 0;
}

export default async function EditorialCasePage({
  params,
  searchParams,
}: {
  params: Promise<{ case_id: string }>;
  searchParams: Promise<{ erro?: string; sucesso?: string; source_offset?: string }>;
}) {
  const [{ case_id: caseId }, query] = await Promise.all([params, searchParams]);
  const { erro, sucesso } = query;
  const sourceOffset = sourceTextOffset(query.source_offset);
  const [item, { staff }] = await Promise.all([
    editorialFetch<EditorialCaseDetail>(`/cases/${encodeURIComponent(caseId)}`),
    getEditorialContext(),
  ]);
  const isParliamentPublicationCase =
    (item.kind === "PARLIAMENT_ACTIVITY" &&
      item.subject_type === "PARLIAMENT_ACTIVITY_SNAPSHOT") ||
    (item.kind === "PARLIAMENT_VOTE" && item.subject_type === "PARLIAMENT_VOTES_SNAPSHOT");
  const isAiDreCase =
    item.kind === "AI_EXPLANATION" && item.subject_type === "DRE_DOCUMENT_SNAPSHOT";
  const [parliamentPublication, parliamentWithdrawal, aiSourceEvidence] = await Promise.all([
    isParliamentPublicationCase && item.current_state === "APPROVED"
      ? editorialFetch<ParliamentEditorialPublicationPreview>(
          `/parliament/cases/${encodeURIComponent(caseId)}/publication`,
        )
      : Promise.resolve(null),
    isParliamentPublicationCase && item.current_state === "PUBLISHED"
      ? editorialFetch<ParliamentEditorialWithdrawalPreview>(
          `/parliament/cases/${encodeURIComponent(caseId)}/withdrawal`,
        )
      : Promise.resolve(null),
    isAiDreCase
      ? editorialFetch<AiDreSourceEvidence>(
          `/ai/cases/${encodeURIComponent(caseId)}/source?${new URLSearchParams({
            offset: sourceOffset.toString(),
            limit: "40000",
          }).toString()}`,
        )
      : Promise.resolve(null),
  ]);
  const currentVersion = item.versions.find((version) => version.is_current);
  if (!currentVersion) throw new Error("O processo não tem versão atual");
  const officialSourceUrl = safeOfficialSourceUrl(item.source.url);

  return (
    <div className="admin-page">
      <header className="admin-detail-heading">
        <div>
          <Link href="/admin/revisao">← Fila de revisão</Link>
          <p className="eyebrow">{KIND_LABELS[item.kind]}</p>
          <h1>{item.subject_id}</h1>
          <p>{item.subject_type}</p>
        </div>
        <div className="admin-detail-state">
          <span className={`admin-state state-${item.current_state.toLowerCase()}`}>
            {STATE_LABELS[item.current_state]}
          </span>
          <small>revisão {item.revision} · versão {currentVersion.version_number}</small>
        </div>
      </header>

      {erro ? (
        <p className="private-message private-message--error" role="alert">
          {erro}
        </p>
      ) : null}
      {sucesso ? (
        <p className="private-message private-message--success" role="status">
          {successMessage(sucesso)}
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Sem publicação automática</strong>
        <p>{item.publication_notice}</p>
      </aside>

      {aiSourceEvidence ? (
        <AiEditorialComparison
          evidence={aiSourceEvidence}
          normalizedData={currentVersion.normalized_data}
          normalizedSha256={currentVersion.normalized_sha256}
          origin={currentVersion.origin}
          createdByAlias={currentVersion.created_by_alias}
        />
      ) : (
      <section className="admin-compare-grid" aria-label="Comparação entre fonte e normalização">
        <article className="admin-proof-panel">
          <p className="eyebrow">Fonte original</p>
          <h2>{item.source.title}</h2>
          <dl>
            <div>
              <dt>Publicador</dt>
              <dd>{item.source.publisher}</dd>
            </div>
            <div>
              <dt>Identificador</dt>
              <dd>{item.source.official_identifier ?? "Dados indisponíveis na fonte"}</dd>
            </div>
            <div>
              <dt>Recolha</dt>
              <dd>{dateFormatter.format(new Date(item.source.retrieved_at))}</dd>
            </div>
            <div>
              <dt>SHA-256 do documento</dt>
              <dd>
                <code>{item.source.content_sha256}</code>
              </dd>
            </div>
          </dl>
          {officialSourceUrl ? (
            <a className="button" href={officialSourceUrl} target="_blank" rel="noreferrer noopener">
              Abrir fonte oficial
            </a>
          ) : (
            <p className="private-message private-message--error">URL oficial indisponível.</p>
          )}
          {item.source.archive ? (
            <div className="admin-attestation">
              <strong>Original arquivado e atestado</strong>
              <span>
                {item.source.archive.byte_size.toLocaleString("pt-PT")} bytes · {item.source.archive.storage_backend}
              </span>
              <code>{item.source.archive.attestation_sha256}</code>
            </div>
          ) : (
            <p className="private-message private-message--error">Arquivo atestado indisponível.</p>
          )}
        </article>

        <article className="admin-normalized-panel">
          <div>
            <p className="eyebrow">Versão normalizada atual</p>
            <h2>Dados propostos</h2>
            <span>por {currentVersion.created_by_alias}</span>
          </div>
          <pre>{JSON.stringify(currentVersion.normalized_data, null, 2)}</pre>
          <footer>
            <span>SHA-256 normalizado</span>
            <code>{currentVersion.normalized_sha256}</code>
          </footer>
        </article>
      </section>
      )}

      <EditorialActions
        item={item}
        aiSourceEvidence={aiSourceEvidence}
        normalizedData={currentVersion.normalized_data}
        parliamentPublication={parliamentPublication}
        parliamentWithdrawal={parliamentWithdrawal}
        staff={staff}
      />

      <section className="admin-history-section">
        <div className="admin-section-heading">
          <div>
            <p className="eyebrow">Rasto de auditoria</p>
            <h2>Decisões imutáveis</h2>
          </div>
          <span>{item.decisions.length} decisão(ões)</span>
        </div>
        <ol className="admin-history-list">
          {item.decisions.map((decision) => (
            <li key={decision.id}>
              <div className="admin-history-marker" aria-hidden="true" />
              <article>
                <header>
                  <strong>{ACTION_LABELS[decision.action] ?? decision.action}</strong>
                  <span>revisão {decision.case_revision}</span>
                </header>
                <p>{decision.rationale}</p>
                <dl>
                  <div>
                    <dt>Responsável</dt>
                    <dd>{decision.actor_alias}</dd>
                  </div>
                  <div>
                    <dt>Data</dt>
                    <dd>{dateFormatter.format(new Date(decision.created_at))}</dd>
                  </div>
                  <div>
                    <dt>Estado</dt>
                    <dd>{STATE_LABELS[decision.resulting_state]}</dd>
                  </div>
                  <div>
                    <dt>Fonte confirmada</dt>
                    <dd>{decision.source_confirmed ? "Sim" : "Não aplicável"}</dd>
                  </div>
                </dl>
                <code title={decision.decision_sha256}>{decision.decision_sha256}</code>
              </article>
            </li>
          ))}
        </ol>
      </section>

      {item.publication_events.length ? (
        <section className="admin-publication-history">
          <div className="admin-section-heading">
            <div>
              <p className="eyebrow">Porta pública</p>
              <h2>Eventos de publicação imutáveis</h2>
            </div>
            <span>{item.publication_events.length} evento(s)</span>
          </div>
          <ol className="admin-publication-event-list">
            {item.publication_events.map((event) => (
              <li key={event.id}>
                <strong>{event.action === "PUBLISH" ? "Publicado" : "Retirado"}</strong>
                <span>
                  {event.target_type} · {event.target_id}
                </span>
                <span>
                  {event.actor_alias} · {dateFormatter.format(new Date(event.created_at))}
                </span>
                <p>{event.rationale}</p>
                <code>{event.event_sha256}</code>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="admin-versions-section">
        <p className="eyebrow">Histórico de conteúdo</p>
        <h2>Todas as versões</h2>
        {item.versions.map((version) => (
          <details key={version.id} open={version.is_current}>
            <summary>
              Versão {version.version_number} {version.is_current ? "· atual" : ""} · origem {version.origin === "AI" ? "IA" : version.origin === "HUMAN" ? "humana" : "ingestão"} · {version.created_by_alias}
            </summary>
            <pre>{JSON.stringify(version.normalized_data, null, 2)}</pre>
            <code>{version.normalized_sha256}</code>
          </details>
        ))}
      </section>
    </div>
  );
}

function EditorialActions({
  item,
  aiSourceEvidence,
  normalizedData,
  parliamentPublication,
  parliamentWithdrawal,
  staff,
}: {
  item: EditorialCaseDetail;
  aiSourceEvidence: AiDreSourceEvidence | null;
  normalizedData: Record<string, unknown>;
  parliamentPublication: ParliamentEditorialPublicationPreview | null;
  parliamentWithdrawal: ParliamentEditorialWithdrawalPreview | null;
  staff: StaffSession;
}) {
  const sharedFields = (
    <>
      <input type="hidden" name="case_id" value={item.id} />
      <input type="hidden" name="expected_revision" value={item.revision} />
    </>
  );

  if (item.current_state === "PENDING") {
    return (
      <section className="admin-action-section">
        <div>
          <p className="eyebrow">Próximo passo</p>
          <h2>Iniciar revisão humana</h2>
          <p>Registe por que razão esta fonte e versão estão prontas para comparação.</p>
        </div>
        <form action={startEditorialReview}>
          {sharedFields}
          <label>
            Fundamentação
            <textarea name="rationale" minLength={20} maxLength={2000} required />
          </label>
          <button className="button button--primary" type="submit">
            Iniciar revisão
          </button>
        </form>
      </section>
    );
  }

  const canCorrect = ["IN_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN"].includes(
    item.current_state,
  );
  return (
    <section className="admin-actions-stack">
      {item.current_state === "IN_REVIEW" ? (
        <div className="admin-decision-grid">
          <form action={approveEditorialCase} className="admin-decision-card admin-decision-card--approve">
            {sharedFields}
            <h2>Aprovar para futura publicação</h2>
            <p>A aprovação continua privada e não altera o site público.</p>
            <label>
              Fundamentação
              <textarea name="rationale" minLength={20} maxLength={2000} required />
            </label>
            <label className="admin-confirmation">
              <input name="confirm_source_reviewed" type="checkbox" required />
              <span>Comparei a fonte oficial com os dados normalizados.</span>
            </label>
            <button className="button button--primary" type="submit">
              Aprovar em privado
            </button>
          </form>
          <form action={rejectEditorialCase} className="admin-decision-card admin-decision-card--reject">
            {sharedFields}
            <h2>Rejeitar proposta</h2>
            <p>A versão mantém-se no histórico e poderá ser corrigida.</p>
            <label>
              Fundamentação
              <textarea name="rationale" minLength={20} maxLength={2000} required />
            </label>
            <button className="button" type="submit">
              Rejeitar com fundamento
            </button>
          </form>
        </div>
      ) : null}

      {item.current_state === "APPROVED" && parliamentPublication ? (
        <ParliamentPublicationAction preview={parliamentPublication} staff={staff} />
      ) : null}

      {item.current_state === "PUBLISHED" && parliamentWithdrawal ? (
        <ParliamentWithdrawalAction preview={parliamentWithdrawal} staff={staff} />
      ) : null}

      {aiSourceEvidence && ["IN_REVIEW", "APPROVED", "REJECTED"].includes(item.current_state) ? (
        <AiRegenerationAction item={item} evidence={aiSourceEvidence} />
      ) : null}

      {canCorrect ? (
        <details className="admin-correction-panel">
          <summary>Acrescentar versão corrigida</summary>
          <form action={correctEditorialCase}>
            {sharedFields}
            <label>
              Dados normalizados corrigidos
              <textarea
                className="admin-json-editor"
                name="normalized_data"
                defaultValue={JSON.stringify(normalizedData, null, 2)}
                spellCheck={false}
                required
              />
            </label>
            <label>
              Razão da correção
              <textarea name="rationale" minLength={20} maxLength={2000} required />
            </label>
            <button className="button button--primary" type="submit">
              Guardar como nova versão por rever
            </button>
          </form>
        </details>
      ) : null}
    </section>
  );
}

function AiRegenerationAction({
  item,
  evidence,
}: {
  item: EditorialCaseDetail;
  evidence: AiDreSourceEvidence;
}) {
  return (
    <details className="admin-correction-panel ai-regeneration-panel">
      <summary>Pedir uma nova versão ao modelo</summary>
      <div className="ai-regeneration-warning">
        <strong>A versão atual não será substituída.</strong>
        <p>
          O pedido conta para o limite diário. O resultado será uma nova versão privada com origem
          IA, regressará a “Por rever” e conservará todas as decisões anteriores.
        </p>
      </div>
      <form action={regenerateAiDreProposal}>
        <input type="hidden" name="case_id" value={item.id} />
        <input type="hidden" name="expected_revision" value={item.revision} />
        <input
          type="hidden"
          name="expected_current_version_sha256"
          value={evidence.current_version_sha256}
        />
        <label>
          Motivo verificável para a nova geração
          <textarea name="rationale" minLength={20} maxLength={2000} required />
        </label>
        <label className="admin-confirmation">
          <input name="confirm_private_only" type="checkbox" required />
          <span>A nova proposta permanecerá privada e sem publicação automática.</span>
        </label>
        <label className="admin-confirmation">
          <input name="confirm_archived_source_only" type="checkbox" required />
          <span>Será usado apenas o mesmo snapshot DRE arquivado e atestado.</span>
        </label>
        <label className="admin-confirmation">
          <input name="confirm_ai_not_source" type="checkbox" required />
          <span>A IA não é fonte, não é revisora e pode responder que não é possível determinar.</span>
        </label>
        <label className="admin-confirmation">
          <input name="confirm_new_immutable_version" type="checkbox" required />
          <span>Confirmo que pretendo acrescentar uma nova versão sem apagar a atual.</span>
        </label>
        <button className="button button--primary" type="submit">
          Gerar e acrescentar nova versão
        </button>
      </form>
    </details>
  );
}

function ParliamentPublicationAction({
  preview,
  staff,
}: {
  preview: ParliamentEditorialPublicationPreview;
  staff: StaffSession;
}) {
  const countLabel =
    preview.scope === "activity"
      ? `${preview.manifest_counts.sessions} reuniões e ${preview.manifest_counts.initiatives} iniciativas`
      : `${preview.manifest_counts.votes} votações e ${preview.manifest_counts.vote_records} posições`;

  return (
    <section className="admin-publication-panel">
      <div className="admin-publication-summary">
        <div>
          <p className="eyebrow">Publicação específica por âmbito</p>
          <h2>Publicar apenas {preview.scope_label}</h2>
          <p>
            Esta ação torna público somente o âmbito <strong>{preview.scope}</strong> da fotografia
            confirmada. O outro âmbito mantém o seu próprio processo e estado.
          </p>
        </div>
        <dl>
          <div>
            <dt>Legislatura</dt>
            <dd>{preview.legislature}</dd>
          </div>
          <div>
            <dt>Cobertura</dt>
            <dd>{countLabel}</dd>
          </div>
          <div>
            <dt>Estado público atual</dt>
            <dd>
              {preview.public_projection.publishable === true
                ? "Já publicável pela V4"
                : "Ainda privado neste âmbito"}
            </dd>
          </div>
        </dl>
        <p className="admin-publication-rule">{preview.publication_rule}</p>
      </div>

      {preview.blockers.length ? (
        <div className="admin-publication-blockers" role="alert">
          <strong>Publicação bloqueada</strong>
          <ul>
            {preview.blockers.map((blocker) => (
              <li key={blocker.code}>{blocker.detail}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {staff.role === "ADMIN" ? (
        <form action={publishParliamentCase}>
          <input type="hidden" name="case_id" value={preview.case_id} />
          <input type="hidden" name="expected_revision" value={preview.revision} />
          <input type="hidden" name="confirmed_scope" value={preview.scope} />
          <input type="hidden" name="expected_snapshot_id" value={preview.target_id} />
          <input
            type="hidden"
            name="expected_source_sha256"
            value={preview.source.content_sha256}
          />
          <input
            type="hidden"
            name="expected_snapshot_sha256"
            value={preview.snapshot_sha256}
          />
          <input
            type="hidden"
            name="expected_editorial_sha256"
            value={preview.editorial_version.normalized_sha256}
          />
          <input
            type="hidden"
            name="expected_publication_proof_sha256"
            value={preview.publication_proof_sha256}
          />
          <div className="admin-publication-digests">
            <span>SHA-256 da fonte</span>
            <code>{preview.source.content_sha256}</code>
            <span>SHA-256 da fotografia normalizada</span>
            <code>{preview.snapshot_sha256}</code>
            <span>SHA-256 da versão editorial</span>
            <code>{preview.editorial_version.normalized_sha256}</code>
            <span>SHA-256 da prova de publicação</span>
            <code>{preview.publication_proof_sha256}</code>
          </div>
          <label>
            Fundamentação pública e auditável
            <textarea name="rationale" minLength={20} maxLength={2000} required />
          </label>
          <label className="admin-confirmation">
            <input name="confirm_source_reviewed" type="checkbox" required />
            <span>Voltei a comparar a fonte oficial, a data e os SHA-256 apresentados.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_individual_inference" type="checkbox" required />
            <span>Não atribuí posições coletivas ou sem identificador a políticos.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_publication" type="checkbox" required />
            <span>
              Confirmo a publicação exclusiva de <strong>{preview.scope_label}</strong> nesta
              fotografia.
            </span>
          </label>
          <button
            className="button button--primary"
            type="submit"
            disabled={!preview.eligible}
          >
            Publicar {preview.scope_label}
          </button>
        </form>
      ) : (
        <p className="private-message">
          A prova está visível para revisão, mas apenas um administrador com MFA pode confirmar a
          publicação.
        </p>
      )}
    </section>
  );
}

function ParliamentWithdrawalAction({
  preview,
  staff,
}: {
  preview: ParliamentEditorialWithdrawalPreview;
  staff: StaffSession;
}) {
  const publicEffectLabel = preview.public_effect.kind === "DATA_UNAVAILABLE"
    ? "Dados indisponíveis neste âmbito"
    : "Recuo para uma fotografia anterior ainda aprovada";

  return (
    <section className="admin-publication-panel admin-withdrawal-panel">
      <div className="admin-publication-summary">
        <div>
          <p className="eyebrow">Retirada específica e append-only</p>
          <h2>Retirar apenas {preview.scope_label}</h2>
          <p>
            Esta ação acrescenta uma revisão pública negativa, uma decisão <strong>WITHDRAW</strong>
            e um evento imutável. A publicação e a versão originais não são apagadas.
          </p>
        </div>
        <dl>
          <div>
            <dt>Legislatura</dt>
            <dd>{preview.legislature}</dd>
          </div>
          <div>
            <dt>Âmbito integral</dt>
            <dd>{preview.scope_label}</dd>
          </div>
          <div>
            <dt>Efeito calculado</dt>
            <dd>{publicEffectLabel}</dd>
          </div>
        </dl>
        <p className="admin-withdrawal-effect">
          <strong>{publicEffectLabel}.</strong> {preview.public_effect.message}
        </p>
        <p className="admin-publication-rule">{preview.withdrawal_rule}</p>
      </div>

      {preview.blockers.length ? (
        <div className="admin-publication-blockers" role="alert">
          <strong>Retirada bloqueada</strong>
          <ul>
            {preview.blockers.map((blocker) => (
              <li key={blocker.code}>{blocker.detail}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {staff.role === "ADMIN" ? (
        <form action={withdrawParliamentCase}>
          <input type="hidden" name="case_id" value={preview.case_id} />
          <input type="hidden" name="expected_revision" value={preview.revision} />
          <input type="hidden" name="confirmed_scope" value={preview.scope} />
          <input type="hidden" name="expected_snapshot_id" value={preview.target_id} />
          <input type="hidden" name="expected_source_sha256" value={preview.source_sha256} />
          <input type="hidden" name="expected_snapshot_sha256" value={preview.snapshot_sha256} />
          <input type="hidden" name="expected_editorial_sha256" value={preview.editorial_sha256} />
          <input
            type="hidden"
            name="expected_publication_proof_sha256"
            value={preview.publication_proof_sha256}
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
          <div className="admin-publication-digests">
            <span>SHA-256 da fonte publicada</span>
            <code>{preview.source_sha256}</code>
            <span>SHA-256 da fotografia publicada</span>
            <code>{preview.snapshot_sha256}</code>
            <span>SHA-256 da versão editorial</span>
            <code>{preview.editorial_sha256}</code>
            <span>SHA-256 da prova de publicação</span>
            <code>{preview.publication_proof_sha256}</code>
            <span>SHA-256 do efeito público calculado</span>
            <code>{preview.public_effect_sha256}</code>
          </div>
          <label>
            Categoria permitida pela governação
            <select name="reason_category" required defaultValue="">
              <option value="" disabled>Selecione um fundamento</option>
              {Object.entries(PARLIAMENT_WITHDRAWAL_REASON_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Fundamentação interna completa
            <textarea name="rationale" minLength={20} maxLength={1850} required />
            <small>Não será exposta pela API pública, mas ficará no histórico editorial.</small>
          </label>
          <label>
            Resumo público redigido
            <textarea name="public_rationale" minLength={20} maxLength={500} required />
            <small>
              Não inclua dados pessoais, credenciais, vulnerabilidades ou informação legalmente
              limitada. Este texto será mostrado no histórico público.
            </small>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_selective_removal" type="checkbox" required />
            <span>
              Confirmo que o fundamento pertence à lista pública e que não retiro dados por
              conveniência política, pressão externa ou seleção editorial.
            </span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_public_effect_reviewed" type="checkbox" required />
            <span>Revi o efeito público calculado e o respetivo SHA-256.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_withdrawal" type="checkbox" required />
            <span>
              Confirmo a retirada integral de <strong>{preview.scope_label}</strong>, preservando o
              histórico e sem alterar o outro âmbito.
            </span>
          </label>
          <button className="button button--danger" type="submit" disabled={!preview.eligible}>
            Retirar {preview.scope_label}
          </button>
        </form>
      ) : (
        <p className="private-message">
          A prova e o efeito estão visíveis para revisão, mas apenas um administrador com MFA pode
          confirmar a retirada.
        </p>
      )}
    </section>
  );
}
