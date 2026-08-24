import Link from "next/link";
import { publishPoliticianProfileSnapshot } from "../../../actions";
import { editorialFetch, getEditorialContext } from "@/lib/editorial-api";
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
  await Promise.all(
    catalogue.items.map(async (snapshot) => {
      if (!snapshot.eligible) return;
      const preview = await editorialFetch<PoliticianProfileSnapshotPublicationPreview>(
        `/parliament/deputy-snapshots/${encodeURIComponent(snapshot.snapshot_id)}/publication`,
      );
      publicationPreviews.set(snapshot.snapshot_id, preview);
    }),
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.29–V5.30 · fotografia completa</p>
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
  isAdmin,
}: {
  snapshot: PoliticianProfilePublicationReadiness;
  preview: PoliticianProfileSnapshotPublicationPreview | null;
  isAdmin: boolean;
}) {
  const officialUrl = safeOfficialSourceUrl(snapshot.source.url);
  const reviewed = snapshot.editorial_counts.APPROVED;
  const total = snapshot.manifest_counts.deputies;
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">Legislatura {snapshot.legislature}</p>
          <h2>Fotografia de {dateFormatter.format(new Date(snapshot.collected_at))}</h2>
          <p>
            {reviewed.toLocaleString("pt-PT")} de {total.toLocaleString("pt-PT")} perfis têm
            aprovação privada da versão exata.
          </p>
        </div>
        <span className={`admin-state ${snapshot.eligible ? "state-approved" : "state-rejected"}`}>
          {snapshot.eligible ? "Fotografia pronta" : "Fotografia bloqueada"}
        </span>
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

      {snapshot.blockers.length ? (
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
