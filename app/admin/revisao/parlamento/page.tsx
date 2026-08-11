import Link from "next/link";
import { createParliamentProposal } from "../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type ParliamentEditorialScope,
  type ParliamentEditorialSnapshot,
  type ParliamentSnapshotDifference,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

const countLabels = {
  sessions: "Reuniões observadas",
  initiatives: "Iniciativas",
  votes: "Votações",
  vote_records: "Posições registadas",
} as const;

function safeOfficialSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export default async function ParliamentEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{ legislature?: string; erro?: string }>;
}) {
  const query = await searchParams;
  const legislature = (query.legislature?.trim() || "XVII").slice(0, 20);
  const params = new URLSearchParams({ legislature, limit: "10" });
  const snapshots = await editorialFetch<ParliamentEditorialSnapshot[]>(
    `/parliament/snapshots?${params.toString()}`,
  );

  return (
    <div className="admin-page parliament-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.2 · adaptador parlamentar</p>
          <h1>Fotografias para revisão</h1>
          <p>
            Compare snapshots oficiais e crie propostas privadas separadas para atividade e
            votações. A ingestão nunca publica dados.
          </p>
        </div>
        <Link href="/admin/revisao">Voltar à fila</Link>
      </header>

      {query.erro ? (
        <p className="private-message private-message--error" role="alert">
          {query.erro}
        </p>
      ) : null}

      <aside className="admin-private-warning">
        <strong>Correspondência exata</strong>
        <p>
          As diferenças usam apenas identificadores oficiais. Posições coletivas ou sem
          identificador inequívoco nunca são atribuídas a políticos.
        </p>
      </aside>

      <form className="admin-filter-bar parliament-filter" method="get">
        <label>
          Legislatura
          <input name="legislature" defaultValue={legislature} maxLength={20} required />
        </label>
        <button className="button" type="submit">
          Consultar fotografias
        </button>
      </form>

      {snapshots.length ? (
        <section className="parliament-snapshot-list" aria-label="Fotografias parlamentares">
          {snapshots.map((snapshot) => (
            <SnapshotCard snapshot={snapshot} key={snapshot.snapshot_id} />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem fotografias atestadas nesta legislatura.</strong>
          <p>A ausência é mostrada como dados indisponíveis e não como incumprimento.</p>
        </section>
      )}
    </div>
  );
}

function SnapshotCard({ snapshot }: { snapshot: ParliamentEditorialSnapshot }) {
  const officialUrl = safeOfficialSourceUrl(snapshot.source.url);
  return (
    <article className="parliament-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">Legislatura {snapshot.legislature}</p>
          <h2>{snapshot.source.title}</h2>
          <p>
            Recolhida em {dateFormatter.format(new Date(snapshot.collected_at))} · parser{" "}
            {snapshot.parser_version}
          </p>
        </div>
        <span
          className={`admin-state ${snapshot.manifest_matches ? "state-approved" : "state-rejected"}`}
        >
          {snapshot.manifest_matches ? "Manifesto confirmado" : "Proposta bloqueada"}
        </span>
      </header>

      <section className="parliament-proof-grid" aria-label="Prova da fotografia">
        <dl>
          <div>
            <dt>Snapshot</dt>
            <dd>{snapshot.snapshot_id}</dd>
          </div>
          <div>
            <dt>Fonte recolhida em</dt>
            <dd>{dateFormatter.format(new Date(snapshot.source.retrieved_at))}</dd>
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
          <div>
            <dt>Atestação de arquivo</dt>
            <dd>
              <code>{snapshot.archive.attestation_sha256}</code>
            </dd>
          </div>
        </dl>
        <div className="parliament-proof-actions">
          <strong>Original preservado</strong>
          <span>
            {snapshot.archive.byte_size.toLocaleString("pt-PT")} bytes ·{" "}
            {snapshot.archive.storage_backend}
          </span>
          <span>
            Arquivo atestado em {dateFormatter.format(new Date(snapshot.archive.archived_at))}
          </span>
          {officialUrl ? (
            <a className="button" href={officialUrl} target="_blank" rel="noreferrer noopener">
              Abrir fonte oficial
            </a>
          ) : (
            <span>URL oficial indisponível</span>
          )}
        </div>
      </section>

      <dl
        className="parliament-count-grid"
        aria-label="Contagens materializadas e contagens do manifesto"
      >
        {Object.entries(countLabels).map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>
              {snapshot.materialised_counts[key as keyof typeof countLabels].toLocaleString("pt-PT")}
            </dd>
            <small>
              Manifesto: {snapshot.manifest_counts[key as keyof typeof countLabels].toLocaleString("pt-PT")}
            </small>
          </div>
        ))}
      </dl>

      <section className="parliament-review-grid">
        <div>
          <p className="eyebrow">Diferenças exatas</p>
          <h3>
            {snapshot.previous_snapshot
              ? `Face a ${dateFormatter.format(new Date(snapshot.previous_snapshot.collected_at))}`
              : "Sem fotografia anterior comparável"}
          </h3>
          {snapshot.differences.status === "COMPARED_BY_EXACT_SOURCE_ID" ? (
            <dl className="parliament-diff-list">
              <DiffRow label="Reuniões" value={snapshot.differences.sessions} />
              <DiffRow label="Iniciativas" value={snapshot.differences.initiatives} />
              <DiffRow label="Votações e posições" value={snapshot.differences.votes} />
            </dl>
          ) : (
            <p className="admin-form-help">
              Não é possível determinar alterações sem uma fotografia anterior atestada.
            </p>
          )}
        </div>

        <div>
          <p className="eyebrow">Cobertura das votações</p>
          <h3>Sem completar lacunas por inferência</h3>
          <dl className="parliament-coverage-list">
            <div>
              <dt>Votações nominais declaradas</dt>
              <dd>{snapshot.coverage.nominal_votes.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Posições ligadas a pessoa por ID</dt>
              <dd>{snapshot.coverage.linked_person_records.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Posições de pessoa sem ID</dt>
              <dd>{snapshot.coverage.unlinked_person_records.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Posições coletivas ligadas a partido por ID</dt>
              <dd>{snapshot.coverage.linked_party_records.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Posições coletivas de partido sem ID</dt>
              <dd>{snapshot.coverage.unlinked_party_records.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Atores UNKNOWN</dt>
              <dd>{snapshot.coverage.unknown_actor_records.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Sentidos UNKNOWN</dt>
              <dd>{snapshot.coverage.unknown_choice_records.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Votações sem posições</dt>
              <dd>{snapshot.coverage.votes_without_records.toLocaleString("pt-PT")}</dd>
            </div>
            <div>
              <dt>Ligações de ator inconsistentes</dt>
              <dd>{snapshot.coverage.inconsistent_actor_links.toLocaleString("pt-PT")}</dd>
            </div>
          </dl>
        </div>
      </section>

      <details className="parliament-limitations">
        <summary>Limitações e regras preservadas</summary>
        <ul>
          {snapshot.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </details>

      <section className="parliament-proposal-grid" aria-label="Criar propostas privadas">
        <ScopeAction snapshot={snapshot} scope="activity" />
        <ScopeAction snapshot={snapshot} scope="votes" />
      </section>
    </article>
  );
}

function DiffRow({
  label,
  value,
}: {
  label: string;
  value: ParliamentSnapshotDifference | null;
}) {
  if (!value) return null;
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        +{value.added} · −{value.removed} · {value.changed} alterado(s) · {value.unchanged}{" "}
        sem alteração
      </dd>
    </div>
  );
}

function ScopeAction({
  snapshot,
  scope,
}: {
  snapshot: ParliamentEditorialSnapshot;
  scope: ParliamentEditorialScope;
}) {
  const existing = snapshot.editorial_cases[scope];
  const label = scope === "activity" ? "atividade parlamentar" : "votações";
  if (existing) {
    return (
      <article className="parliament-proposal-card parliament-proposal-card--existing">
        <p className="eyebrow">{label}</p>
        <h3>Processo já existente</h3>
        <p>
          {STATE_LABELS[existing.state]} · revisão {existing.revision} · origem {existing.origin}
        </p>
        <Link className="button" href={`/admin/revisao/${existing.id}`}>
          Abrir processo
        </Link>
      </article>
    );
  }

  return (
    <form action={createParliamentProposal} className="parliament-proposal-card">
      <input type="hidden" name="snapshot_id" value={snapshot.snapshot_id} />
      <input type="hidden" name="legislature" value={snapshot.legislature} />
      <input type="hidden" name="scope" value={scope} />
      <p className="eyebrow">{label}</p>
      <h3>Criar proposta por rever</h3>
      <p>O servidor reconstrói os dados a partir desta fotografia; o formulário não os altera.</p>
      <label className="admin-confirmation">
        <input name="confirm_private_only" type="checkbox" required />
        <span>Confirmo que esta proposta permanece privada.</span>
      </label>
      <label className="admin-confirmation">
        <input name="confirm_no_individual_inference" type="checkbox" required />
        <span>Confirmo que posições coletivas não são votos individuais.</span>
      </label>
      <button
        className="button button--primary"
        type="submit"
        disabled={!snapshot.proposal_eligible}
      >
        Enviar {label} para a fila
      </button>
    </form>
  );
}
