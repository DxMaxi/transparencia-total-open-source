import Link from "next/link";
import { createEditorialCase } from "../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  EDITORIAL_KINDS,
  KIND_LABELS,
  type EditorialSourceCandidate,
} from "@/lib/editorial-types";

const initialJson = JSON.stringify(
  {
    titulo: "",
    factos: [],
    dados_indisponiveis: [],
    notas_de_normalizacao: [],
  },
  null,
  2,
);

export default async function NewEditorialCasePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; erro?: string }>;
}) {
  const { q, erro } = await searchParams;
  const normalizedQuery = q?.trim().slice(0, 100);
  const sourceParams = new URLSearchParams({ limit: "20" });
  if (normalizedQuery && normalizedQuery.length >= 2) {
    sourceParams.set("q", normalizedQuery);
  }
  const sources = await editorialFetch<EditorialSourceCandidate[]>(
    `/sources?${sourceParams.toString()}`,
  );

  return (
    <div className="admin-page admin-form-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">Nova proposta</p>
          <h1>Criar processo privado</h1>
          <p>A fonte tem de estar arquivada e atestada antes de existir uma proposta editorial.</p>
        </div>
        <Link href="/admin/revisao">Voltar à fila</Link>
      </header>

      {erro ? (
        <p className="private-message private-message--error" role="alert">
          {erro}
        </p>
      ) : null}

      <section className="admin-source-search">
        <h2>1. Encontrar a fonte recolhida</h2>
        <form method="get">
          <label htmlFor="source-search">Título, identificador oficial ou URL</label>
          <div>
            <input
              id="source-search"
              name="q"
              type="search"
              defaultValue={normalizedQuery ?? ""}
              minLength={2}
              maxLength={100}
            />
            <button className="button" type="submit">
              Procurar
            </button>
          </div>
        </form>
      </section>

      <form action={createEditorialCase} className="admin-editorial-form">
        <fieldset>
          <legend>Fonte oficial com prova</legend>
          <div className="admin-source-options">
            {sources.map((source, index) => (
              <label className="admin-source-option" key={source.id}>
                <input
                  type="radio"
                  name="source_document_id"
                  value={source.id}
                  required
                  defaultChecked={index === 0}
                />
                <span>
                  <strong>{source.title}</strong>
                  <small>
                    {source.publisher} · {source.official_identifier ?? "sem identificador oficial"}
                  </small>
                  <code title={source.content_sha256}>{source.content_sha256.slice(0, 24)}…</code>
                  <em>
                    Arquivo atestado · {source.editorial_case_count} processo(s) já associado(s)
                  </em>
                </span>
              </label>
            ))}
          </div>
          {!sources.length ? (
            <p className="admin-empty-inline">
              Nenhuma fonte arquivada corresponde à pesquisa. A ingestão tem de acontecer antes da
              revisão.
            </p>
          ) : null}
        </fieldset>

        <fieldset disabled={!sources.length}>
          <legend>2. Identificar a proposta</legend>
          <div className="admin-form-grid">
            <label>
              Tipo de conteúdo
              <select name="kind" defaultValue="PARLIAMENT_ACTIVITY" required>
                {EDITORIAL_KINDS.map((kind) => (
                  <option value={kind} key={kind}>
                    {KIND_LABELS[kind]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Tipo técnico do assunto
              <input
                name="subject_type"
                defaultValue="PARLIAMENT_SNAPSHOT"
                pattern="[A-Z][A-Z0-9_]{1,63}"
                maxLength={64}
                required
              />
            </label>
            <label className="admin-field-wide">
              Identificador inequívoco do assunto
              <input name="subject_id" maxLength={200} required />
              <small>Use apenas um identificador oficial ou interno inequívoco. Nunca aproxime nomes.</small>
            </label>
          </div>
        </fieldset>

        <fieldset disabled={!sources.length}>
          <legend>3. Dados normalizados privados</legend>
          <label>
            Objeto JSON
            <textarea
              className="admin-json-editor"
              name="normalized_data"
              defaultValue={initialJson}
              spellCheck={false}
              required
            />
          </label>
          <p className="admin-form-help">
            NIF/NIPC em claro são recusados. Um identificador fiscal só pode existir como HMAC
            SHA-256 com o pepper privado do backend. Se a fonte não tiver um dado, registe-o como
            “dados indisponíveis”.
          </p>
        </fieldset>

        <label className="admin-confirmation">
          <input name="confirm_private_only" type="checkbox" required />
          <span>
            Confirmo que esta ação cria apenas uma proposta privada e não autoriza publicação.
          </span>
        </label>
        <button className="button button--primary" type="submit" disabled={!sources.length}>
          Criar processo por rever
        </button>
      </form>
    </div>
  );
}
