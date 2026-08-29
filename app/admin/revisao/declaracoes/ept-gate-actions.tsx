import {
  publishEptPublicInterest,
  recordEptExactIdentityLink,
  recordEptLegalAssessment,
  withdrawEptPublicInterest,
} from "../actions";
import {
  PARLIAMENT_WITHDRAWAL_REASON_LABELS,
  type EptPublicInterestGate,
  type EptPublicInterestPublicationPreview,
  type EptPublicInterestWithdrawalPreview,
} from "@/lib/editorial-types";

const digestPattern = "[0-9a-f]{64}";

function GateEvidenceFields({ gate }: { gate: EptPublicInterestGate }) {
  return (
    <>
      <input type="hidden" name="expected_case_id" value={gate.case_id} />
      <input type="hidden" name="expected_revision" value={gate.case_revision} />
      <input type="hidden" name="expected_version_id" value={gate.version_id} />
      <input type="hidden" name="expected_version_sha256" value={gate.version_sha256} />
      <input type="hidden" name="expected_observation_id" value={gate.observation_id} />
      <input type="hidden" name="expected_source_sha256" value={gate.source.content_sha256} />
      <input
        type="hidden"
        name="expected_source_record_sha256"
        value={gate.source_record_sha256}
      />
    </>
  );
}

function Confirmation({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <label className="admin-confirmation">
      <input name={name} type="checkbox" required />
      <span>{children}</span>
    </label>
  );
}

export function EptGateActions({
  gate,
  publication,
  withdrawal,
  isAdmin,
}: {
  gate: EptPublicInterestGate | null;
  publication: EptPublicInterestPublicationPreview | null;
  withdrawal: EptPublicInterestWithdrawalPreview | null;
  isAdmin: boolean;
}) {
  if (!gate) {
    return (
      <section className="parliament-proposal-card">
        <p>A porta EPT não pôde ser reconstruída. Nenhuma ação pública está disponível.</p>
      </section>
    );
  }

  return (
    <section className="ept-gate-stack" aria-label="Porta jurídica e de identidade EPT">
      <div className="parliament-proposal-card">
        <p className="eyebrow">V5.47 · verificação documental</p>
        <h3>Porta específica EPT</h3>
        <p>{gate.legal_notice}</p>
        <dl className="admin-summary-grid">
          <div>
            <dt>Avaliação jurídica</dt>
            <dd>
              {gate.legal_assessment
                ? gate.legal_assessment.outcome === "PERMITS_PUBLIC_INTEREST_METADATA_ONLY"
                  ? "Registada para metadados mínimos"
                  : "Registada sem autorização de publicação"
                : "Dados indisponíveis"}
            </dd>
          </div>
          <div>
            <dt>Identidade exata</dt>
            <dd>{gate.identity_link ? "Ligada por HMAC e segunda fonte" : "Dados indisponíveis"}</dd>
          </div>
          <div>
            <dt>Correspondência por nome</dt>
            <dd>Nunca permitida</dd>
          </div>
          <div>
            <dt>Publicação automática</dt>
            <dd>Desativada</dd>
          </div>
        </dl>
        {gate.blockers.length ? (
          <ul className="parliament-limitations">
            {gate.blockers.map((blocker) => (
              <li key={`${blocker.code}-${blocker.detail}`}>{blocker.detail}</li>
            ))}
          </ul>
        ) : null}
      </div>

      {gate.case_state === "APPROVED" ? (
        <>
          <LegalAssessmentForm gate={gate} isAdmin={isAdmin} />
          {!gate.identity_link ? <IdentityLinkForm gate={gate} isAdmin={isAdmin} /> : null}
          {publication ? <PublicationForm preview={publication} isAdmin={isAdmin} /> : null}
        </>
      ) : null}

      {gate.case_state === "PUBLISHED" && withdrawal ? (
        <WithdrawalForm preview={withdrawal} isAdmin={isAdmin} />
      ) : null}
    </section>
  );
}

function LegalAssessmentForm({
  gate,
  isAdmin,
}: {
  gate: EptPublicInterestGate;
  isAdmin: boolean;
}) {
  return (
    <details className="parliament-proposal-card">
      <summary>
        {gate.legal_assessment ? "Registar avaliação jurídica posterior" : "Registar avaliação jurídica"}
      </summary>
      <form action={recordEptLegalAssessment} className="admin-form-grid">
        <GateEvidenceFields gate={gate} />
        <p className="admin-form-help">
          Este formulário não cria um parecer. Regista apenas a prova de um documento já produzido
          por um avaliador humano independente e guardado de forma cifrada.
        </p>
        <label>
          Conclusão documentada
          <select name="outcome" required defaultValue="REQUIRES_CHANGES">
            <option value="PERMITS_PUBLIC_INTEREST_METADATA_ONLY">
              Permite apenas metadados do registo público de interesses
            </option>
            <option value="DOES_NOT_PERMIT_PUBLICATION">Não permite publicação</option>
            <option value="REQUIRES_CHANGES">Exige alterações ou prova adicional</option>
          </select>
        </label>
        <label>
          SHA-256 do documento jurídico
          <input name="assessment_document_sha256" pattern={digestPattern} required />
        </label>
        <label>
          Arquivo cifrado
          <select name="assessment_document_storage_backend" required defaultValue="BACKBLAZE_B2_ENCRYPTED">
            <option value="BACKBLAZE_B2_ENCRYPTED">Backblaze B2 cifrado</option>
            <option value="OTHER_ENCRYPTED_PRIVATE">Outro arquivo privado cifrado</option>
          </select>
        </label>
        <label>
          Chave privada do objeto no arquivo
          <input
            name="assessment_document_storage_key"
            type="password"
            autoComplete="off"
            maxLength={500}
            required
          />
        </label>
        <label>
          Tamanho do documento em bytes
          <input name="assessment_document_byte_size" type="number" min={1} max={50_000_000} required />
        </label>
        <label>
          Formato arquivado
          <select name="assessment_document_mime_type" required defaultValue="application/pdf">
            <option value="application/pdf">PDF</option>
            <option value="application/octet-stream">Ficheiro cifrado binário</option>
          </select>
        </label>
        <label>
          Referência SHA-256 pseudonimizada do avaliador
          <input name="assessor_reference_sha256" pattern={digestPattern} required />
        </label>
        <label>
          SHA-256 da prova de qualificação
          <input name="qualification_evidence_sha256" pattern={digestPattern} required />
        </label>
        <label>
          SHA-256 da verificação de conflitos
          <input name="conflict_check_sha256" pattern={digestPattern} required />
        </label>
        <label>
          Data e hora da avaliação
          <input name="assessed_at" type="datetime-local" required />
        </label>
        <label>
          Válida até, se aplicável
          <input name="valid_until" type="datetime-local" />
        </label>
        <label className="admin-field-wide">
          Fundamentação privada do registo
          <textarea name="recording_rationale" minLength={20} maxLength={1000} required />
        </label>
        <Confirmation name="confirm_external_human_assessment">
          A avaliação foi realmente produzida por uma pessoa externa ao sistema.
        </Confirmation>
        <Confirmation name="confirm_independent_assessor">
          Confirmei a independência do avaliador.
        </Confirmation>
        <Confirmation name="confirm_qualification_and_conflicts_checked">
          Confirmei qualificações e eventuais conflitos de interesses.
        </Confirmation>
        <Confirmation name="confirm_public_interest_metadata_only">
          O âmbito limita-se aos metadados do registo público de interesses.
        </Confirmation>
        <Confirmation name="confirm_document_encrypted_and_private">
          O documento integral está num arquivo privado cifrado.
        </Confirmation>
        <Confirmation name="confirm_system_did_not_issue_legal_opinion">
          O sistema não emitiu nem substituiu a avaliação jurídica.
        </Confirmation>
        <button className="button button--primary" type="submit" disabled={!isAdmin}>
          Registar prova jurídica imutável
        </button>
        {!isAdmin ? <p className="admin-form-help">Apenas ADMIN com MFA pode executar esta ação.</p> : null}
      </form>
    </details>
  );
}

function IdentityLinkForm({
  gate,
  isAdmin,
}: {
  gate: EptPublicInterestGate;
  isAdmin: boolean;
}) {
  return (
    <details className="parliament-proposal-card">
      <summary>Ligar identidade oficial exata</summary>
      <form action={recordEptExactIdentityLink} className="admin-form-grid">
        <GateEvidenceFields gate={gate} />
        <p className="admin-form-help">
          O identificador é transformado imediatamente em HMAC no backend. Não é guardado, devolvido
          ou usado para procurar nomes semelhantes.
        </p>
        <label>
          Identificador oficial do titular na EPT
          <input
            name="official_subject_identifier"
            type="password"
            autoComplete="off"
            maxLength={200}
            required
          />
        </label>
        <label>
          ID interno da pessoa já revista
          <input name="person_id" maxLength={200} required />
        </label>
        <label>
          Identificador oficial da pessoa
          <input name="expected_person_source_id" maxLength={200} required />
        </label>
        <label>
          ID da segunda fonte oficial
          <input name="identity_evidence_document_id" maxLength={200} required />
        </label>
        <label>
          SHA-256 da segunda fonte
          <input name="expected_identity_evidence_sha256" pattern={digestPattern} required />
        </label>
        <label className="admin-field-wide">
          Fundamentação privada da associação
          <textarea name="recording_rationale" minLength={20} maxLength={1000} required />
        </label>
        <Confirmation name="confirm_exact_official_identifier">
          Usei o identificador oficial exato da fonte, não o nome.
        </Confirmation>
        <Confirmation name="confirm_second_official_source_reviewed">
          A segunda fonte oficial está arquivada e foi revista.
        </Confirmation>
        <Confirmation name="confirm_no_name_or_fuzzy_matching">
          Não usei correspondência por nome, semelhança ou aproximação.
        </Confirmation>
        <Confirmation name="confirm_identifier_will_only_persist_as_hmac">
          O identificador original só pode persistir como HMAC.
        </Confirmation>
        <Confirmation name="confirm_same_person">
          Confirmei que os identificadores oficiais pertencem à mesma pessoa.
        </Confirmation>
        <button className="button button--primary" type="submit" disabled={!isAdmin}>
          Registar ligação exata e privada
        </button>
        {!isAdmin ? <p className="admin-form-help">Apenas ADMIN com MFA pode executar esta ação.</p> : null}
      </form>
    </details>
  );
}

function PublicationForm({
  preview,
  isAdmin,
}: {
  preview: EptPublicInterestPublicationPreview;
  isAdmin: boolean;
}) {
  const legal = preview.legal_assessment;
  const identity = preview.identity_link;
  const ready = Boolean(
    preview.eligible
      && preview.publication_proof_sha256
      && preview.legal_assessment_proof_sha256
      && legal
      && identity,
  );
  if (!ready || !legal || !identity || !preview.publication_proof_sha256
      || !preview.legal_assessment_proof_sha256) {
    return (
      <div className="parliament-proposal-card">
        <h3>Publicação bloqueada</h3>
        <ul className="parliament-limitations">
          {preview.blockers.map((blocker) => <li key={blocker.code}>{blocker.detail}</li>)}
        </ul>
      </div>
    );
  }
  return (
    <form action={publishEptPublicInterest} className="parliament-proposal-card admin-form-grid">
      <GateEvidenceFields gate={preview} />
      <input type="hidden" name="expected_declaration_id" value={preview.declaration_id} />
      <input type="hidden" name="expected_person_id" value={identity.person_id} />
      <input type="hidden" name="expected_identity_link_id" value={identity.id} />
      <input
        type="hidden"
        name="expected_identity_proof_sha256"
        value={identity.link_proof_sha256}
      />
      <input type="hidden" name="expected_legal_assessment_id" value={legal.id} />
      <input type="hidden" name="expected_legal_document_sha256" value={legal.document_sha256} />
      <input
        type="hidden"
        name="expected_legal_assessment_proof_sha256"
        value={preview.legal_assessment_proof_sha256}
      />
      <input
        type="hidden"
        name="expected_publication_proof_sha256"
        value={preview.publication_proof_sha256}
      />
      <h3>Publicar metadados mínimos</h3>
      <p>{preview.publication_rule}</p>
      <label className="admin-field-wide">
        Fundamentação interna
        <textarea name="rationale" minLength={20} maxLength={1850} required />
      </label>
      <label className="admin-field-wide">
        Fundamentação pública
        <textarea name="public_rationale" minLength={20} maxLength={500} required />
      </label>
      <Confirmation name="confirm_source_and_archive_reviewed">Revi a fonte e o arquivo.</Confirmation>
      <Confirmation name="confirm_exact_identity_link_reviewed">Revi a ligação exata.</Confirmation>
      <Confirmation name="confirm_independent_legal_assessment_reviewed">
        Revi a avaliação jurídica humana e o respetivo SHA-256.
      </Confirmation>
      <Confirmation name="confirm_public_interest_metadata_only">
        Só serão publicados metadados mínimos do registo de interesses.
      </Confirmation>
      <Confirmation name="confirm_no_income_asset_or_protected_identifier">
        Não serão publicados rendimentos, património ou identificadores protegidos.
      </Confirmation>
      <Confirmation name="confirm_append_only_publication">A publicação acrescenta histórico.</Confirmation>
      <Confirmation name="confirm_publication">Confirmo esta publicação pública.</Confirmation>
      <button className="button button--primary" type="submit" disabled={!isAdmin}>
        Publicar metadados EPT
      </button>
    </form>
  );
}

function WithdrawalForm({
  preview,
  isAdmin,
}: {
  preview: EptPublicInterestWithdrawalPreview;
  isAdmin: boolean;
}) {
  return (
    <form action={withdrawEptPublicInterest} className="parliament-proposal-card admin-form-grid admin-withdrawal-panel">
      <input type="hidden" name="expected_case_id" value={preview.case_id} />
      <input type="hidden" name="expected_revision" value={preview.case_revision} />
      <input type="hidden" name="expected_version_id" value={preview.version_id} />
      <input type="hidden" name="expected_version_sha256" value={preview.version_sha256} />
      <input type="hidden" name="expected_declaration_id" value={preview.declaration_id} />
      <input type="hidden" name="expected_source_sha256" value={preview.source_sha256} />
      <input type="hidden" name="expected_publication_proof_sha256" value={preview.publication_proof_sha256} />
      <input type="hidden" name="expected_withdrawal_proof_sha256" value={preview.withdrawal_proof_sha256} />
      <input type="hidden" name="expected_public_review_id" value={preview.public_review_id} />
      <input type="hidden" name="expected_publication_audit_event_id" value={preview.publication_audit_event_id} />
      <input type="hidden" name="expected_publication_event_id" value={preview.publication_event_id} />
      <input type="hidden" name="expected_publication_event_sha256" value={preview.publication_event_sha256} />
      <input type="hidden" name="expected_public_effect_sha256" value={preview.public_effect_sha256} />
      <h3>Retirar da consulta ativa</h3>
      <p>{preview.public_effect.message}</p>
      <label>
        Motivo verificável
        <select name="reason_category" required>
          {Object.entries(PARLIAMENT_WITHDRAWAL_REASON_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label className="admin-field-wide">
        Fundamentação interna
        <textarea name="rationale" minLength={20} maxLength={1850} required />
      </label>
      <label className="admin-field-wide">
        Fundamentação pública
        <textarea name="public_rationale" minLength={20} maxLength={500} required />
      </label>
      <Confirmation name="confirm_source_and_publication_reviewed">Revi a fonte e a publicação.</Confirmation>
      <Confirmation name="confirm_public_effect_reviewed">Revi o efeito público da retirada.</Confirmation>
      <Confirmation name="confirm_declaration_and_history_preserved">
        A linha, a fonte e o histórico permanecem.
      </Confirmation>
      <Confirmation name="confirm_identity_and_legal_records_preserved">
        A ligação protegida e a avaliação jurídica não serão apagadas.
      </Confirmation>
      <Confirmation name="confirm_withdrawal">Confirmo esta retirada pública.</Confirmation>
      <button className="button button--danger" type="submit" disabled={!isAdmin || !preview.eligible}>
        Retirar metadados EPT
      </button>
    </form>
  );
}
