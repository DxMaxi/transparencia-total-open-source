"use client";

import { FormEvent, useState } from "react";
import { CheckIcon, ShieldCheckIcon } from "@/components/icons";
import { CONTACT_EMAIL } from "@/lib/site";

type Receipt = {
  public_reference: string;
  statement_sha256: string;
  audit_sha256: string;
  submitted_at: string;
  notice: string;
};

export function RightOfReplyForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setReceipt(null);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
    if (!apiUrl) {
      setError("O canal de resposta está temporariamente indisponível. Consulte a página de contacto.");
      return;
    }
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = Object.fromEntries(form.entries());
    setPending(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/right-of-reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Não foi possível registar a submissão.");
      setReceipt(body as Receipt);
      formElement.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha inesperada no registo.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="reply-layout">
      <form className="right-reply-form card" method="post" onSubmit={submit}>
        <div className="reply-form-heading">
          <span className="eyebrow">Registo imutável</span>
          <h2>Anexar uma resposta ao facto original</h2>
          <p>
            O envio cria uma nova versão com data e SHA-256. Não apaga nem altera o registo contestado.
          </p>
        </div>

        <div className="reply-fields">
          <label>
            Tipo de registo
            <select name="target_type" required defaultValue="POLITICIAN_PROFILE">
              <option value="POLITICIAN_PROFILE">Perfil de titular de cargo público</option>
              <option value="PARLIAMENTARY_INITIATIVE">Iniciativa parlamentar</option>
              <option value="PARLIAMENTARY_VOTE">Votação parlamentar</option>
              <option value="GOVERNMENT_PROMISE">Compromisso do Governo</option>
              <option value="PUBLIC_CONTRACT">Contrato público</option>
              <option value="INTEREST_RELATIONSHIP">Ligação de interesses</option>
              <option value="STATEMENT_VOTE_COMPARISON">Discurso vs. voto</option>
              <option value="JUDICIAL_CASE">Processo judicial/ético</option>
              <option value="NEWS_ARTICLE">Notícia indexada</option>
            </select>
          </label>
          <label>
            Identificador público do registo
            <input name="target_id" required maxLength={128} placeholder="Ex.: BASE-12345" />
          </label>
          <label className="reply-field-wide">
            SHA-256 da versão contestada
            <input
              name="original_record_sha256"
              required
              minLength={64}
              maxLength={64}
              pattern="[0-9a-f]{64}"
              placeholder="64 caracteres hexadecimais"
              className="hash-input"
            />
          </label>
          <label>
            Nome público do respondente
            <input name="claimant_public_name" required minLength={2} maxLength={200} />
          </label>
          <label>
            Qualidade em que responde
            <input name="claimant_role" required minLength={2} maxLength={200} placeholder="Ex.: representante legal" />
          </label>
          <label className="reply-field-wide">
            Declaração de resposta
            <textarea name="statement_text" required minLength={20} maxLength={10000} rows={8} />
            <small>Não inclua contactos, NIF, morada ou outros dados pessoais não necessários.</small>
          </label>
          <label className="reply-field-wide">
            Ligação HTTPS para declaração pública oficial (opcional)
            <input name="official_response_url" type="url" inputMode="url" placeholder="https://…" />
          </label>
        </div>

        <label className="reply-confirmation">
          <input type="checkbox" required />
          <span>
            Confirmo que a resposta se refere ao registo indicado, que tenho legitimidade
            para a apresentar e que li a <a href="/privacidade">política de privacidade</a>.
          </span>
        </label>
        <button className="button button--primary" type="submit" disabled={pending}>
          {pending ? "A registar…" : "Registar resposta auditável"}
        </button>
        {error && <p className="form-message form-message--error" role="alert">{error}</p>}
        {receipt && (
          <div className="reply-receipt" role="status">
            <CheckIcon />
            <div>
              <strong>Recebido: {receipt.public_reference}</strong>
              <span>SHA-256 da declaração: {receipt.statement_sha256}</span>
              <span>SHA-256 do recibo: {receipt.audit_sha256}</span>
              <p>{receipt.notice}</p>
              {CONTACT_EMAIL ? (
                <p>
                  Para permitir contacto durante a verificação, envie a referência acima para
                  <a href={`mailto:${CONTACT_EMAIL}`}> {CONTACT_EMAIL}</a>. O formulário não recolhe
                  o seu email.
                </p>
              ) : (
                <p>
                  Guarde esta referência. O formulário não recolhe o seu email e o canal
                  institucional será indicado na página de contacto quando estiver operacional.
                </p>
              )}
            </div>
          </div>
        )}
      </form>

      <aside className="reply-process card">
        <ShieldCheckIcon />
        <span className="eyebrow">Garantias do processo</span>
        <h2>Direito de resposta sem apagar história</h2>
        <ol>
          <li><b>1</b><span><strong>Receção</strong> Timestamp e hash do conteúdo.</span></li>
          <li><b>2</b><span><strong>Verificação</strong> Identidade, mandato e prova documental.</span></li>
          <li><b>3</b><span><strong>Publicação ligada</strong> Resposta visível junto ao registo original.</span></li>
          <li><b>4</b><span><strong>Nova versão</strong> Retificações futuras acrescentam histórico.</span></li>
        </ol>
        <p>
          A receção não confirma o mérito da resposta. Rejeições e decisões editoriais ficam igualmente registadas para auditoria interna.
        </p>
        {CONTACT_EMAIL ? (
          <p>
            Se não tiver o identificador ou o SHA-256 do registo, contacte
            <a href={`mailto:${CONTACT_EMAIL}`}> {CONTACT_EMAIL}</a> e indique a página em causa.
          </p>
        ) : (
          <p>
            Se não tiver o identificador ou o SHA-256, consulte a página de{" "}
            <a href="/contacto">contacto</a>. O email institucional ainda está em configuração.
          </p>
        )}
      </aside>
    </div>
  );
}
