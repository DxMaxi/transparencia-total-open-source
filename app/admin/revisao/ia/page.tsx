import Link from "next/link";
import { createAiDreProposal } from "../actions";
import { editorialFetch } from "@/lib/editorial-api";
import {
  STATE_LABELS,
  type AiDreSnapshotCandidate,
  type AiDreSnapshotList,
} from "@/lib/editorial-types";

const dateFormatter = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

function safeOfficialSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export default async function AiEditorialPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; erro?: string }>;
}) {
  const query = await searchParams;
  const search = query.q?.trim().slice(0, 100) ?? "";
  const params = new URLSearchParams({ limit: "20" });
  if (search.length >= 2) params.set("q", search);
  const catalogue = await editorialFetch<AiDreSnapshotList>(
    `/ai/dre-snapshots?${params.toString()}`,
  );

  return (
    <div className="admin-page ai-editorial-page">
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">V5.14 · circuito responsável de IA</p>
          <h1>Propostas a partir do DRE</h1>
          <p>
            Escolha um documento oficial já recolhido e atestado. O modelo cria apenas uma
            proposta privada para comparação humana; não aprova nem publica conteúdo.
          </p>
        </div>
        <Link href="/admin/revisao">Voltar à fila</Link>
      </header>

      {query.erro ? (
        <p className="private-message private-message--error" role="alert">
          {query.erro}
        </p>
      ) : null}

      <section className="ai-provider-card" aria-label="Configuração auditável do modelo">
        <div>
          <p className="eyebrow">Execução privada</p>
          <h2>{catalogue.provider.enabled ? "Gerador disponível" : "Gerador desativado"}</h2>
          <p>{catalogue.generation_rule}</p>
        </div>
        <dl>
          <div>
            <dt>Fornecedor e modelo</dt>
            <dd>{catalogue.provider.enabled ? `${catalogue.provider.name} · ${catalogue.provider.model}` : "Dados indisponíveis"}</dd>
          </div>
          <div>
            <dt>Prompt versionado</dt>
            <dd>{catalogue.provider.prompt_version}</dd>
          </div>
          <div>
            <dt>Tentativas hoje</dt>
            <dd>
              {catalogue.attempts_today} de {catalogue.daily_limit} · {catalogue.remaining_today} restantes
            </dd>
          </div>
          <div>
            <dt>Armazenamento pelo pedido</dt>
            <dd>{catalogue.provider.store ? "Ativo" : "Desativado"}</dd>
          </div>
        </dl>
        <code>{catalogue.provider.prompt_sha256}</code>
      </section>

      <aside className="admin-private-warning">
        <strong>IA não é fonte</strong>
        <p>
          Só o texto público do DRE é enviado. Uma ausência de prova deve produzir “não é possível
          determinar”; cada afirmação terá de ser conferida na etapa seguinte.
        </p>
      </aside>

      <form className="admin-filter-bar ai-snapshot-filter" method="get">
        <label>
          Título ou identificador oficial
          <input
            name="q"
            defaultValue={search}
            minLength={2}
            maxLength={100}
            placeholder="Ex.: Lei n.º ou orçamento"
          />
        </label>
        <button className="button" type="submit">
          Pesquisar no arquivo DRE
        </button>
        {search ? <Link href="/admin/revisao/ia">Limpar</Link> : null}
      </form>

      {catalogue.excluded_invalid_snapshots ? (
        <p className="private-message private-message--error" role="status">
          {catalogue.excluded_invalid_snapshots} snapshot(s) foram ocultados porque a prova
          criptográfica não pôde ser confirmada.
        </p>
      ) : null}

      {catalogue.items.length ? (
        <section className="ai-snapshot-list" aria-label="Documentos DRE disponíveis para proposta">
          {catalogue.items.map((snapshot) => (
            <AiSnapshotCard
              key={snapshot.snapshot_id}
              snapshot={snapshot}
              providerEnabled={catalogue.provider.enabled}
              remainingToday={catalogue.remaining_today}
            />
          ))}
        </section>
      ) : (
        <section className="admin-empty-state">
          <strong>Não existem snapshots DRE atestados para esta consulta.</strong>
          <p>A ausência é mostrada como dados indisponíveis e não é completada por IA.</p>
        </section>
      )}
    </div>
  );
}

function AiSnapshotCard({
  snapshot,
  providerEnabled,
  remainingToday,
}: {
  snapshot: AiDreSnapshotCandidate;
  providerEnabled: boolean;
  remainingToday: number;
}) {
  const officialUrl = safeOfficialSourceUrl(snapshot.source_url);
  return (
    <article className="ai-snapshot-card">
      <header>
        <div>
          <p className="eyebrow">{snapshot.official_identifier ?? "Identificador indisponível"}</p>
          <h2>{snapshot.title}</h2>
          <p>
            Publicado {snapshot.published_at ? dateFormatter.format(new Date(snapshot.published_at)) : "em data indisponível"}
            {" · "}recolhido {dateFormatter.format(new Date(snapshot.retrieved_at))}
          </p>
        </div>
        {snapshot.existing_case ? (
          <span className={`admin-state state-${snapshot.existing_case.state.toLowerCase()}`}>
            {STATE_LABELS[snapshot.existing_case.state]}
          </span>
        ) : (
          <span className="admin-state state-pending">Sem proposta</span>
        )}
      </header>

      <section className="ai-snapshot-proof" aria-label="Prova oficial e atestação">
        <dl>
          <div>
            <dt>Texto normalizado</dt>
            <dd>{snapshot.source_characters.toLocaleString("pt-PT")} caracteres</dd>
          </div>
          <div>
            <dt>Extrator</dt>
            <dd>{snapshot.parser_version}</dd>
          </div>
          <div>
            <dt>SHA-256 da fonte</dt>
            <dd><code>{snapshot.source_content_sha256}</code></dd>
          </div>
          <div>
            <dt>SHA-256 do texto</dt>
            <dd><code>{snapshot.normalised_text_sha256}</code></dd>
          </div>
          <div>
            <dt>Atestação de arquivo</dt>
            <dd><code>{snapshot.archive.attestation_sha256}</code></dd>
          </div>
        </dl>
        <div className="ai-snapshot-archive">
          <strong>Original arquivado</strong>
          <span>
            {snapshot.archive.byte_size.toLocaleString("pt-PT")} bytes · {snapshot.archive.storage_backend}
          </span>
          <span>{dateFormatter.format(new Date(snapshot.archive.archived_at))}</span>
          {officialUrl ? (
            <a className="button" href={officialUrl} target="_blank" rel="noreferrer noopener">
              Abrir no DRE
            </a>
          ) : (
            <span>URL oficial indisponível</span>
          )}
        </div>
      </section>

      {snapshot.existing_case ? (
        <div className="ai-existing-proposal">
          <div>
            <strong>Já existe uma proposta para este modelo e prompt.</strong>
            <span>
              Versão {snapshot.existing_case.version_number} · atualizada em {dateFormatter.format(new Date(snapshot.existing_case.updated_at))}
            </span>
          </div>
          <Link className="button button--primary" href={`/admin/revisao/${snapshot.existing_case.id}`}>
            Abrir comparação
          </Link>
        </div>
      ) : (
        <form action={createAiDreProposal} className="ai-generation-form">
          <input type="hidden" name="snapshot_id" value={snapshot.snapshot_id} />
          <fieldset>
            <legend>Confirmações antes do pedido externo</legend>
            <label className="admin-confirmation">
              <input name="confirm_private_only" type="checkbox" required />
              <span>A proposta ficará privada e em estado por rever.</span>
            </label>
            <label className="admin-confirmation">
              <input name="confirm_archived_source_only" type="checkbox" required />
              <span>Confirmo o envio exclusivo deste texto público DRE já arquivado.</span>
            </label>
            <label className="admin-confirmation">
              <input name="confirm_ai_not_source" type="checkbox" required />
              <span>A IA não é fonte, não decide factos e pode abster-se.</span>
            </label>
          </fieldset>
          <button
            className="button button--primary"
            type="submit"
            disabled={!snapshot.generation_eligible || !providerEnabled || remainingToday === 0}
          >
            Gerar proposta privada
          </button>
        </form>
      )}
    </article>
  );
}
