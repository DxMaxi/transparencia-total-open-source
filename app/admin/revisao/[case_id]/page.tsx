import Link from "next/link";
import {
  approveEditorialCase,
  correctEditorialCase,
  rejectEditorialCase,
  startEditorialReview,
} from "../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  KIND_LABELS,
  STATE_LABELS,
  type EditorialCaseDetail,
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

export default async function EditorialCasePage({
  params,
  searchParams,
}: {
  params: Promise<{ case_id: string }>;
  searchParams: Promise<{ erro?: string; sucesso?: string }>;
}) {
  const { case_id: caseId } = await params;
  const { erro, sucesso } = await searchParams;
  const item = await editorialFetch<EditorialCaseDetail>(`/cases/${encodeURIComponent(caseId)}`);
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
          A decisão foi acrescentada ao histórico imutável.
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Sem publicação automática</strong>
        <p>{item.publication_notice}</p>
      </aside>

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

      <EditorialActions item={item} normalizedData={currentVersion.normalized_data} />

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

      <section className="admin-versions-section">
        <p className="eyebrow">Histórico de conteúdo</p>
        <h2>Todas as versões</h2>
        {item.versions.map((version) => (
          <details key={version.id} open={version.is_current}>
            <summary>
              Versão {version.version_number} {version.is_current ? "· atual" : ""} · {version.created_by_alias}
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
  normalizedData,
}: {
  item: EditorialCaseDetail;
  normalizedData: Record<string, unknown>;
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

  const canCorrect = ["IN_REVIEW", "APPROVED", "REJECTED"].includes(item.current_state);
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
