import Link from "next/link";
import {
  publishPoliticianProfileSnapshot,
  withdrawPoliticianProfileSnapshot,
} from "../../../actions";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
import {
  PARLIAMENT_WITHDRAWAL_REASON_LABELS,
  type PoliticianProfileSnapshotWithdrawalPreview,
  type ParliamentWithdrawalReason,
} from "@/lib/editorial-types";
import type {
  PoliticianProfilePublicationReadiness,
  PoliticianProfilePublicationReadinessList,
  PoliticianProfileSnapshotPublicationPreview,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

const withdrawalReasonEntries = Object.entries(PARLIAMENT_WITHDRAWAL_REASON_LABELS) as Array<
  [ParliamentWithdrawalReason, string]
>;

function safeOfficialSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

export default async function PoliticianProfilePublicationReadinessPage({
  searchParams,
}: {
  searchParams: Promise<{ legislature?: string; erro?: string; sucesso?: string }>;
}) {
  const input = await searchParams;
  const legislature = (input.legislature?.trim() || "XVII").slice(0, 20);
  const params = new URLSearchParams({ legislature, limit: "10" });
  const catalogue = await editorialFetch<PoliticianProfilePublicationReadinessList>(
    `/parliament/deputy-snapshots/publication-readiness?${params.toString()}`,
  );
  const { staff } = await getEditorialContext();
  const publicationPreviews = new Map<string, PoliticianProfileSnapshotPublicationPreview>();
  const withdrawalPreviews = new Map<string, PoliticianProfileSnapshotWithdrawalPreview>();
  await Promise.all(
    catalogue.items.map(async (snapshot) => {
      if (snapshot.eligible) {
        const preview = await editorialFetch<PoliticianProfileSnapshotPublicationPreview>(
          `/parliament/deputy-snapshots/${encodeURIComponent(snapshot.snapshot_id)}/publication`,
        );
        publicationPreviews.set(snapshot.snapshot_id, preview);
      } else if (
        snapshot.editorial_counts.PUBLISHED === snapshot.manifest_counts.deputies &&
        snapshot.manifest_counts.deputies > 0
      ) {
        const preview = await editorialFetch<PoliticianProfileSnapshotWithdrawalPreview>(
          `/parliament/deputy-snapshots/${encodeURIComponent(snapshot.snapshot_id)}/withdrawal`,
        );
        withdrawalPreviews.set(snapshot.snapshot_id, preview);
      }
    }),
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.29–V5.31 · fotografia completa</p>
          <h1>Prontidão privada dos perfis políticos</h1>
          <p>
            A inspeção inicial volta a provar a fonte, o arquivo, o manifesto e todas as aprovações
            da mesma fotografia sem escrever dados. Uma publicação só pode começar numa ação ADMIN
            separada, explícita e protegida por MFA.
          </p>
        </div>
        <Link href="/admin/revisao/parlamento/deputados">Rever observações</Link>
      </header>

      {input.erro ? (
        <p className="private-message private-message--error" role="alert">
          {input.erro}
        </p>
      ) : null}
      {input.sucesso === "fotografia-publicada" ? (
        <p className="private-message" role="status">
          A fotografia foi publicada numa única transação e o histórico foi preservado.
        </p>
      ) : null}
      {input.sucesso === "fotografia-retirada" ? (
        <p className="private-message" role="status">
          A fotografia foi retirada em bloco; pessoas, fontes, versões e histórico permanecem.
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Uma fotografia parcial nunca aparece como uma lista completa</strong>
        <p>
          Basta faltar um processo, uma aprovação, um hash ou uma atestação para toda a fotografia
          continuar bloqueada. Uma correção genérica também é recusada se deixar de coincidir com a
          reconstrução determinística da fonte.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Legislatura
          <input name="legislature" defaultValue={legislature} maxLength={20} required />
        </label>
        <button className="button" type="submit">
          Inspecionar fotografias
        </button>
      </form>

      <p className="admin-form-help">{catalogue.readiness_rule}</p>

      {catalogue.items.length ? (
        <section className="parliament-snapshot-list" aria-label="Prontidão das fotografias">
          {catalogue.items.map((snapshot) => (
            <ReadinessCard
              isAdmin={staff.role === "ADMIN"}
              key={snapshot.snapshot_id}
              preview={publicationPreviews.get(snapshot.snapshot_id) ?? null}
              snapshot={snapshot}
              withdrawalPreview={withdrawalPreviews.get(snapshot.snapshot_id) ?? null}
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem fotografias privadas para esta legislatura.</strong>
          <p>A ausência permanece dados indisponíveis; não prova omissão nem incumprimento.</p>
        </section>
      )}
    </div>
  );
}

function ReadinessCard({
  snapshot,
  preview,
  withdrawalPreview,
  isAdmin,
}: {
  snapshot: PoliticianProfilePublicationReadiness;
  preview: PoliticianProfileSnapshotPublicationPreview | null;
  withdrawalPreview: PoliticianProfileSnapshotWithdrawalPreview | null;
  isAdmin: boolean;
}) {
  const officialUrl = safeOfficialSourceUrl(snapshot.source.url);
  const reviewed = snapshot.editorial_counts.APPROVED;
  const total = snapshot.manifest_counts.deputies;
  const isPublished = total > 0 && snapshot.editorial_counts.PUBLISHED === total;
  const isWithdrawn = total > 0 && snapshot.editorial_counts.WITHDRAWN === total;
  const stateClass = snapshot.eligible || isPublished ? "state-approved" : "state-rejected";
  const stateLabel = snapshot.eligible
    ? "Fotografia pronta"
    : isPublished
      ? "Fotografia publicada"
      : isWithdrawn
        ? "Fotografia retirada"
        : "Fotografia bloqueada";
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">Legislatura {snapshot.legislature}</p>
          <h2>Fotografia de {dateFormatter.format(new Date(snapshot.collected_at))}</h2>
          {isPublished ? (
            <p>{total.toLocaleString("pt-PT")} perfis estão publicados como uma fotografia única.</p>
          ) : isWithdrawn ? (
            <p>A fotografia saiu da consulta ativa, mas toda a prova permanece no histórico.</p>
          ) : (
            <p>
              {reviewed.toLocaleString("pt-PT")} de {total.toLocaleString("pt-PT")} perfis têm
              aprovação privada da versão exata.
            </p>
          )}
        </div>
        <span className={`admin-state ${stateClass}`}>{stateLabel}</span>
      </header>

      <section className="parliament-proof-grid" aria-label="Prova da fotografia de perfis">
        <dl>
          <div>
            <dt>Deputados no manifesto</dt>
            <dd>{snapshot.manifest_counts.deputies.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Observações materializadas</dt>
            <dd>{snapshot.materialised_counts.deputies.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Processos em falta</dt>
            <dd>{snapshot.editorial_counts.MISSING.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Aprovações privadas</dt>
            <dd>{reviewed.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Pessoas já ligadas por DepId exato</dt>
            <dd>{snapshot.identity_projection.exact_existing_people.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Novas identidades ainda necessárias</dt>
            <dd>{snapshot.identity_projection.new_people_required.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>SHA-256 da fonte</dt>
            <dd>
              <code>{snapshot.source.content_sha256}</code>
            </dd>
          </div>
          <div>
            <dt>SHA-256 normalizado</dt>
            <dd>
              <code>{snapshot.normalised_sha256}</code>
            </dd>
          </div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>{snapshot.archive_attested ? "Arquivo exato atestado" : "Arquivo em falta"}</strong>
          <span>{snapshot.parser_version}</span>
          <span>Recolhida {dateFormatter.format(new Date(snapshot.source.retrieved_at))}</span>
          {officialUrl ? (
            <a className="button" href={officialUrl} target="_blank" rel="noreferrer noopener">
              Abrir fonte oficial
            </a>
          ) : (
            <span>URL oficial indisponível</span>
          )}
          <Link
            className="button"
            href={`/admin/revisao/parlamento/deputados?legislature=${encodeURIComponent(snapshot.legislature)}`}
          >
            Rever perfis desta legislatura
          </Link>
        </div>
      </section>

      {isPublished ? (
        <WithdrawalAction
          isAdmin={isAdmin}
          legislature={snapshot.legislature}
          preview={withdrawalPreview}
        />
      ) : isWithdrawn ? (
        <section className="parliament-proposal-card">
          <p className="eyebrow">Histórico preservado</p>
          <h3>Esta versão não pode ser reativada</h3>
          <p>
            Uma republicação exige uma nova fotografia oficial arquivada, novos processos e nova
            revisão humana. A versão retirada nunca volta silenciosamente à consulta pública.
          </p>
        </section>
      ) : snapshot.blockers.length ? (
        <section className="parliament-proposal-card">
          <p className="eyebrow">Bloqueios atuais</p>
          <h3>A fotografia continua exclusivamente privada</h3>
          <ul className="parliament-limitations">
            {snapshot.blockers.map((blocker) => (
              <li key={blocker.code}>
                <strong>{blocker.count.toLocaleString("pt-PT")}×</strong> {blocker.detail}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <PublicationAction
          isAdmin={isAdmin}
          legislature={snapshot.legislature}
          preview={preview}
        />
      )}

      <p className="admin-form-help">{snapshot.publication_rule}</p>
    </article>
  );
}

function PublicationAction({
  preview,
  legislature,
  isAdmin,
}: {
  preview: PoliticianProfileSnapshotPublicationPreview | null;
  legislature: string;
  isAdmin: boolean;
}) {
  if (!preview) {
    return (
      <section className="parliament-proposal-card">
        <strong>Prova de publicação indisponível.</strong>
        <p>A fotografia permanece privada e nenhuma ação é apresentada.</p>
      </section>
    );
  }
  return (
    <section className="admin-publication-panel">
      <div className="admin-publication-summary">
        <div>
          <p className="eyebrow">V5.30 · publicação integral</p>
          <h3>Todos os perfis coincidem com a fotografia oficial</h3>
          <p>
            A transação reutiliza apenas identidades com o mesmo DepId, cria as restantes e
            acrescenta observações, revisões e histórico. Não cria mandatos nem filiações.
          </p>
        </div>
        <dl>
          <div>
            <dt>Pessoas novas</dt>
            <dd>{preview.public_effect.people_to_create.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Pessoas exatas reutilizadas</dt>
            <dd>
              {preview.public_effect.people_to_reuse_by_exact_depid.toLocaleString("pt-PT")}
            </dd>
          </div>
          <div>
            <dt>Mandatos ou filiações criados</dt>
            <dd>0</dd>
          </div>
        </dl>
        <div className="admin-publication-digests">
          <span>SHA-256 da prontidão</span>
          <code>{preview.readiness_proof_sha256}</code>
          <span>SHA-256 da prova de publicação</span>
          <code>{preview.publication_proof_sha256}</code>
        </div>
      </div>

      {isAdmin && preview.eligible && preview.readiness_proof_sha256 && preview.publication_proof_sha256 ? (
        <form action={publishPoliticianProfileSnapshot}>
          <input type="hidden" name="legislature" value={legislature} />
          <input type="hidden" name="expected_snapshot_id" value={preview.snapshot_id} />
          <input
            type="hidden"
            name="expected_source_sha256"
            value={preview.source.content_sha256}
          />
          <input
            type="hidden"
            name="expected_snapshot_sha256"
            value={preview.normalised_sha256}
          />
          <input
            type="hidden"
            name="expected_readiness_proof_sha256"
            value={preview.readiness_proof_sha256}
          />
          <input
            type="hidden"
            name="expected_publication_proof_sha256"
            value={preview.publication_proof_sha256}
          />
          <input
            type="hidden"
            name="expected_deputy_count"
            value={preview.manifest_counts.deputies}
          />
          <label>
            Fundamentação interna completa
            <textarea name="rationale" minLength={20} maxLength={1850} required />
            <small>Fica no histórico editorial privado.</small>
          </label>
          <label>
            Fundamentação pública resumida
            <textarea name="public_rationale" minLength={20} maxLength={500} required />
          </label>
          <label className="admin-confirmation">
            <input name="confirm_source_reviewed" type="checkbox" required />
            <span>Voltei a comparar URL, data, arquivo e SHA-256 da fonte oficial.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_complete_snapshot" type="checkbox" required />
            <span>Confirmo a fotografia inteira, não uma seleção de perfis.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_exact_official_id_only" type="checkbox" required />
            <span>As identidades são ligadas apenas pelo DepId oficial exato.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_mandate_inference" type="checkbox" required />
            <span>Nenhuma observação será convertida em início, fim ou continuidade de mandato.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_party_inference" type="checkbox" required />
            <span>Nenhuma sigla ou nome de grupo será convertido automaticamente em filiação.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_publication" type="checkbox" required />
            <span>Confirmo a publicação transacional de todos os perfis desta fotografia.</span>
          </label>
          <button className="button button--primary" type="submit">
            Publicar a fotografia completa
          </button>
        </form>
      ) : (
        <p className="private-message">
          A prova está visível, mas apenas um administrador com MFA pode publicar a fotografia.
        </p>
      )}
      <p className="admin-publication-rule">{preview.publication_rule}</p>
    </section>
  );
}

function WithdrawalAction({
  preview,
  legislature,
  isAdmin,
}: {
  preview: PoliticianProfileSnapshotWithdrawalPreview | null;
  legislature: string;
  isAdmin: boolean;
}) {
  if (!preview) {
    return (
      <section className="parliament-proposal-card">
        <strong>Prova de retirada indisponível.</strong>
        <p>A fotografia permanece publicada e nenhuma ação de retirada é apresentada.</p>
      </section>
    );
  }
  const fallbackUrl =
    preview.public_effect.kind === "FALLBACK_TO_PREVIOUS_SNAPSHOT"
      ? safeOfficialSourceUrl(preview.public_effect.source_url)
      : null;
  return (
    <section className="admin-publication-panel admin-withdrawal-panel">
      <div className="admin-publication-summary">
        <div>
          <p className="eyebrow">V5.31 · retirada integral</p>
          <h3>A fotografia publicada foi novamente provada em bloco</h3>
          <p>
            A retirada acrescenta uma decisão por perfil e uma decisão para a fotografia. Não apaga
            pessoas, observações, fontes, versões ou a prova da publicação original.
          </p>
        </div>
        <dl>
          <div>
            <dt>Perfis abrangidos</dt>
            <dd>{preview.published_profile_count.toLocaleString("pt-PT")}</dd>
          </div>
          <div>
            <dt>Pessoas, observações ou versões apagadas</dt>
            <dd>0</dd>
          </div>
        </dl>
        <div className="admin-withdrawal-effect">
          <strong>Efeito público calculado</strong>
          <p>{preview.public_effect.message}</p>
          {preview.public_effect.kind === "FALLBACK_TO_PREVIOUS_SNAPSHOT" ? (
            <p>
              A fotografia anterior contém {preview.public_effect.profile_count.toLocaleString("pt-PT")} perfis
              e foi verificada em {dateFormatter.format(new Date(preview.public_effect.verified_at))}.
              {fallbackUrl ? (
                <>
                  {" "}
                  <a href={fallbackUrl} target="_blank" rel="noreferrer noopener">
                    Abrir fonte oficial anterior
                  </a>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
        <div className="admin-publication-digests">
          <span>SHA-256 da publicação original</span>
          <code>{preview.publication_proof_sha256}</code>
          <span>SHA-256 da prova integral de retirada</span>
          <code>{preview.withdrawal_proof_sha256 ?? "Prova indisponível"}</code>
          <span>SHA-256 do efeito público</span>
          <code>{preview.public_effect_sha256}</code>
        </div>
      </div>

      {preview.blockers.length ? (
        <div className="admin-publication-blockers" role="alert">
          <strong>A retirada está bloqueada</strong>
          <ul>
            {preview.blockers.map((blocker) => (
              <li key={blocker.code}>
                {blocker.count.toLocaleString("pt-PT")}× {blocker.detail}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {isAdmin && preview.eligible && preview.withdrawal_proof_sha256 ? (
        <form action={withdrawPoliticianProfileSnapshot}>
          <input type="hidden" name="legislature" value={legislature} />
          <input type="hidden" name="expected_snapshot_id" value={preview.snapshot_id} />
          <input
            type="hidden"
            name="expected_source_sha256"
            value={preview.source.content_sha256}
          />
          <input
            type="hidden"
            name="expected_snapshot_sha256"
            value={preview.normalised_sha256}
          />
          <input
            type="hidden"
            name="expected_publication_proof_sha256"
            value={preview.publication_proof_sha256}
          />
          <input
            type="hidden"
            name="expected_withdrawal_proof_sha256"
            value={preview.withdrawal_proof_sha256}
          />
          <input
            type="hidden"
            name="expected_public_effect_sha256"
            value={preview.public_effect_sha256}
          />
          <input
            type="hidden"
            name="expected_deputy_count"
            value={preview.manifest_counts.deputies}
          />
          <label>
            Categoria factual da retirada
            <select name="reason_category" required defaultValue="">
              <option value="" disabled>
                Selecionar categoria
              </option>
              {withdrawalReasonEntries.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Fundamentação interna completa
            <textarea name="rationale" minLength={20} maxLength={1850} required />
            <small>Não é apresentada automaticamente ao público.</small>
          </label>
          <label>
            Fundamentação pública resumida
            <textarea name="public_rationale" minLength={20} maxLength={500} required />
          </label>
          <label className="admin-confirmation">
            <input name="confirm_complete_snapshot" type="checkbox" required />
            <span>Confirmo que a decisão abrange a fotografia completa.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_no_selective_removal" type="checkbox" required />
            <span>Nenhuma pessoa foi escolhida ou omitida individualmente.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_public_effect_reviewed" type="checkbox" required />
            <span>Revi o recuo calculado ou a indicação de dados indisponíveis.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_people_and_history_preserved" type="checkbox" required />
            <span>Confirmo que pessoas, fontes, versões e histórico serão preservados.</span>
          </label>
          <label className="admin-confirmation">
            <input name="confirm_withdrawal" type="checkbox" required />
            <span>Confirmo a retirada integral desta fotografia publicada.</span>
          </label>
          <button className="button button--danger" type="submit">
            Retirar a fotografia completa
          </button>
        </form>
      ) : preview.blockers.length === 0 ? (
        <p className="private-message">
          A prova está visível, mas apenas um administrador com MFA pode retirar a fotografia.
        </p>
      ) : null}
      <p className="admin-publication-rule">{preview.withdrawal_rule}</p>
    </section>
  );
}
