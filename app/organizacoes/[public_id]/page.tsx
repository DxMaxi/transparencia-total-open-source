import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { RightOfReplyForm } from "@/components/right-of-reply-form";
import {
  loadPublicOrganisation,
  loadPublicOrganisationHistory,
  ORGANISATION_KIND_LABELS,
  type PublicOrganisationHistoryResult,
  type PublicOrganisationReply,
} from "@/lib/public-organisations";

export const dynamic = "force-dynamic";

const dates = new Intl.DateTimeFormat("pt-PT", {
  dateStyle: "long",
  timeStyle: "short",
  timeZone: "Europe/Lisbon",
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ public_id: string }>;
}): Promise<Metadata> {
  const { public_id } = await params;
  return {
    title: `Organização ${public_id.slice(-8)}`,
    description: "Fotografia pública auditável de uma organização.",
    robots: { index: false, follow: true },
  };
}

export default async function OrganisationDetailPage({
  params,
}: {
  params: Promise<{ public_id: string }>;
}) {
  const { public_id } = await params;
  const [active, history] = await Promise.all([
    loadPublicOrganisation(public_id),
    loadPublicOrganisationHistory(public_id),
  ]);

  if (active.status === "not_found" && history.status === "not_found") {
    notFound();
  }

  if (active.status !== "ok") {
    const withdrawn = active.status === "not_found" && history.status === "ok";
    return (
      <main className="page-shell shell organisation-detail">
        <Link href="/organizacoes">← Organizações</Link>
        <section className="admin-empty-state" role="status">
          <strong>
            {withdrawn
              ? "Organização retirada da consulta ativa."
              : "Consulta temporariamente indisponível."}
          </strong>
          <p>
            {withdrawn
              ? "A prova, as decisões, os hashes e os direitos de resposta anteriores permanecem abaixo; os campos retirados não são republicados."
              : "Não apresentamos dados antigos ou não oficiais como substituição."}
          </p>
        </section>
        {history.status === "ok" ? (
          <>
            <PublishedReplies replies={history.data.replies} />
            <History history={history.data} />
          </>
        ) : null}
      </main>
    );
  }

  const replies =
    history.status === "ok" ? history.data.replies : active.data.replies;

  return (
    <main className="page-shell shell organisation-detail">
      <Link href="/organizacoes">← Organizações</Link>
      <header className="page-heading">
        <span className="eyebrow">Fotografia publicada e revista</span>
        <h1>{active.data.legal_name}</h1>
        <p>{active.data.coverage_notice}</p>
      </header>
      <div className="organisation-detail-grid">
        <section className="card organisation-proof">
          <h2>Prova pública</h2>
          <dl>
            <div>
              <dt>Categoria</dt>
              <dd>{ORGANISATION_KIND_LABELS[active.data.kind]}</dd>
            </div>
            <div>
              <dt>Referência oficial não fiscal</dt>
              <dd>{active.data.registry_record_id}</dd>
            </div>
            <div>
              <dt>Publicada</dt>
              <dd>{dates.format(new Date(active.data.published_at))}</dd>
            </div>
            <div>
              <dt>Fonte</dt>
              <dd>
                <a
                  href={active.data.source.url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {active.data.source.title}
                </a>
              </dd>
            </div>
            <div>
              <dt>Recolhida</dt>
              <dd>{dates.format(new Date(active.data.source.retrieved_at))}</dd>
            </div>
            <div>
              <dt>SHA-256 da fonte</dt>
              <dd>
                <code>{active.data.source.content_sha256}</code>
              </dd>
            </div>
            <div>
              <dt>SHA-256 do registo</dt>
              <dd>
                <code>{active.data.source_record_sha256}</code>
              </dd>
            </div>
            <div>
              <dt>SHA-256 da fotografia</dt>
              <dd>
                <code>{active.data.public_record_sha256}</code>
              </dd>
            </div>
          </dl>
        </section>
        <aside className="card organisation-limits">
          <h2>O que esta ficha não conclui</h2>
          <ul>
            <li>Não liga automaticamente esta organização a contratos.</li>
            <li>Não identifica titulares ou beneficiários.</li>
            <li>Não prova conflito, favorecimento ou irregularidade.</li>
            <li>Não usa semelhança de nomes.</li>
          </ul>
        </aside>
      </div>
      <PublishedReplies replies={replies} />
      {history.status === "ok" ? <History history={history.data} /> : null}
      <section className="organisation-reply">
        <h2>Responder a esta fotografia</h2>
        <p>
          A resposta é anexada; nunca substitui nem apaga o registo original.
        </p>
        <RightOfReplyForm
          initialTarget={{
            type: "ORGANISATION",
            id: active.data.id,
            sha256: active.data.public_record_sha256,
          }}
        />
      </section>
    </main>
  );
}

function PublishedReplies({ replies }: { replies: PublicOrganisationReply[] }) {
  if (!replies.length) return null;
  return (
    <section className="organisation-replies">
      <h2>Direitos de resposta publicados</h2>
      {replies.map((reply) => (
        <article className="card" key={reply.public_reference}>
          <strong>
            {reply.claimant_public_name} · {reply.claimant_role}
          </strong>
          <p>{reply.statement_text}</p>
          {reply.official_response_url ? (
            <a
              href={reply.official_response_url}
              target="_blank"
              rel="noreferrer noopener"
            >
              Consultar resposta oficial associada
            </a>
          ) : null}
          <span>Fotografia respondida</span>
          <code>{reply.original_record_sha256}</code>
          <span>SHA-256 da resposta</span>
          <code>{reply.statement_sha256}</code>
        </article>
      ))}
    </section>
  );
}

function History({ history }: { history: PublicOrganisationHistoryResult }) {
  return (
    <section className="organisation-history">
      <h2>Histórico imutável</h2>
      <p>{history.coverage_notice}</p>
      <ol>
        {history.items.map((item, index) => (
          <li
            className="card"
            key={`${item.occurred_at}-${item.action}-${index}`}
          >
            <strong>
              {item.action === "PUBLISH" ? "Publicação" : "Retirada"}
            </strong>
            <span>
              {dates.format(new Date(item.occurred_at))} · {item.actor_alias}
            </span>
            <p>{item.public_rationale}</p>
            <code>{item.public_record_sha256}</code>
          </li>
        ))}
      </ol>
    </section>
  );
}
