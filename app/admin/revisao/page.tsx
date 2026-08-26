import Link from "next/link";
import { editorialFetch } from "@/lib/editorial-api";
import {
  EDITORIAL_KINDS,
  EDITORIAL_STATES,
  KIND_LABELS,
  STATE_LABELS,
  type EditorialCaseList,
  type EditorialKind,
  type EditorialState,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

function selectedValue<T extends readonly string[]>(value: string | undefined, values: T) {
  return value && values.includes(value) ? value : undefined;
}

export default async function EditorialQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ state?: string; kind?: string; cursor?: string }>;
}) {
  const query = await searchParams;
  const state = selectedValue(query.state, EDITORIAL_STATES) as EditorialState | undefined;
  const kind = selectedValue(query.kind, EDITORIAL_KINDS) as EditorialKind | undefined;
  const params = new URLSearchParams({ limit: "25" });
  if (state) params.set("state", state);
  if (kind) params.set("kind", kind);
  if (query.cursor) params.set("cursor", query.cursor);
  const queue = await editorialFetch<EditorialCaseList>(`/cases?${params.toString()}`);

  return (
    <div className="admin-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">Circuito editorial V5</p>
          <h1>Fila de revisão</h1>
          <p>Consulte a prova oficial, compare a versão normalizada e registe cada decisão.</p>
        </div>
        <div className="admin-heading-actions">
          <Link className="button button--primary" href="/admin/revisao/ia">
            Propostas DRE por IA
          </Link>
          <Link className="button button--primary" href="/admin/revisao/parlamento">
            Importar fotografia parlamentar
          </Link>
          <Link className="button" href="/admin/revisao/parlamento/deputados">
            Rever observações de deputados
          </Link>
          <Link className="button" href="/admin/revisao/parlamento/deputados/cargos">
            Rever cargos parlamentares
          </Link>
          <Link className="button" href="/admin/revisao/novo">
            Criar processo manual
          </Link>
        </div>
      </header>

      <section className="admin-count-grid" aria-label="Resumo por estado">
        {EDITORIAL_STATES.slice(0, 4).map((item) => (
          <Link
            className={`admin-count-card state-${item.toLowerCase()}`}
            href={`/admin/revisao?state=${item}`}
            key={item}
          >
            <span>{STATE_LABELS[item]}</span>
            <strong>{queue.counts[item]}</strong>
          </Link>
        ))}
      </section>

      <form className="admin-filter-bar" method="get">
        <label>
          Estado
          <select name="state" defaultValue={state ?? ""}>
            <option value="">Todos</option>
            {EDITORIAL_STATES.map((item) => (
              <option value={item} key={item}>
                {STATE_LABELS[item]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tipo
          <select name="kind" defaultValue={kind ?? ""}>
            <option value="">Todos</option>
            {EDITORIAL_KINDS.map((item) => (
              <option value={item} key={item}>
                {KIND_LABELS[item]}
              </option>
            ))}
          </select>
        </label>
        <button className="button" type="submit">
          Aplicar filtros
        </button>
        <Link href="/admin/revisao">Limpar</Link>
      </form>

      {queue.items.length ? (
        <section className="admin-case-list" aria-label="Processos editoriais">
          {queue.items.map((item) => (
            <article className="admin-case-card" key={item.id}>
              <div className="admin-case-card__status">
                <span className={`admin-state state-${item.current_state.toLowerCase()}`}>
                  {STATE_LABELS[item.current_state]}
                </span>
                <span>versão {item.version_number}</span>
              </div>
              <div>
                <small>{KIND_LABELS[item.kind]}</small>
                <h2>{item.subject_id}</h2>
                <p>{item.source.title}</p>
              </div>
              <dl className="admin-proof-inline">
                <div>
                  <dt>Recolhida</dt>
                  <dd>{dateFormatter.format(new Date(item.source.retrieved_at))}</dd>
                </div>
                <div>
                  <dt>SHA-256</dt>
                  <dd title={item.source.content_sha256}>{item.source.content_sha256.slice(0, 16)}…</dd>
                </div>
                <div>
                  <dt>Última decisão</dt>
                  <dd>{dateFormatter.format(new Date(item.updated_at))}</dd>
                </div>
              </dl>
              <Link className="admin-case-card__open" href={`/admin/revisao/${item.id}`}>
                Abrir revisão
              </Link>
            </article>
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem processos com estes filtros.</strong>
          <p>As recolhas não são transformadas automaticamente em publicações.</p>
        </section>
      )}

      {queue.next_cursor ? (
        <div className="admin-pagination">
          <Link
            href={`/admin/revisao?${new URLSearchParams({
              ...(state ? { state } : {}),
              ...(kind ? { kind } : {}),
              cursor: queue.next_cursor,
            }).toString()}`}
          >
            Ver processos anteriores
          </Link>
        </div>
      ) : null}
    </div>
  );
}
