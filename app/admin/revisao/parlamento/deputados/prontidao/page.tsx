import Link from "next/link";
import { editorialFetch } from "@/lib/editorial-api";
import type {
  PoliticianProfilePublicationReadiness,
  PoliticianProfilePublicationReadinessList,
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
  searchParams: Promise<{ legislature?: string }>;
}) {
  const input = await searchParams;
  const legislature = (input.legislature?.trim() || "XVII").slice(0, 20);
  const params = new URLSearchParams({ legislature, limit: "10" });
  const catalogue = await editorialFetch<PoliticianProfilePublicationReadinessList>(
    `/parliament/deputy-snapshots/publication-readiness?${params.toString()}`,
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.29 · porta de fotografia completa</p>
          <h1>Prontidão privada dos perfis políticos</h1>
          <p>
            Esta página volta a provar a fonte, o arquivo, o manifesto e todas as aprovações da
            mesma fotografia. Não cria pessoas, mandatos, revisões públicas ou publicações.
          </p>
        </div>
        <Link href="/admin/revisao/parlamento/deputados">Rever observações</Link>
      </header>

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
            <ReadinessCard key={snapshot.snapshot_id} snapshot={snapshot} />
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

function ReadinessCard({ snapshot }: { snapshot: PoliticianProfilePublicationReadiness }) {
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
        <section className="parliament-proposal-card parliament-proposal-card--existing">
          <p className="eyebrow">Prova de prontidão</p>
          <h3>Todos os perfis coincidem com a fotografia oficial</h3>
          <p>
            <code>{snapshot.readiness_proof_sha256}</code>
          </p>
          <p>
            Ainda não existe aqui uma ação de publicação. A próxima porta terá de repetir esta
            prova numa transação ADMIN com MFA e conservar revisão e auditoria imutáveis.
          </p>
        </section>
      )}

      <p className="admin-form-help">{snapshot.publication_rule}</p>
    </article>
  );
}
