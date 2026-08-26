"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { EditorialApiError, editorialFetch } from "@/lib/editorial-api";
import {
  type AiDreProposalResult,
  type AiEditorialPublicationResult,
  type AiEditorialWithdrawalResult,
  PARLIAMENT_WITHDRAWAL_REASON_LABELS,
  type EditorialCaseDetail,
  type ParliamentEditorialPublicationResult,
  type ParliamentEditorialProposalResult,
  type ParliamentEditorialScope,
  type ParliamentEditorialWithdrawalResult,
  type ParliamentWithdrawalReason,
  type PoliticianOfficeEditorialProposalResult,
  type PoliticianOfficePublicationResult,
  type PoliticianOfficeWithdrawalResult,
  type PoliticianMandateEditorialProposalResult,
  type PoliticianMandatePublicationResult,
  type PoliticianMandateWithdrawalResult,
  type PoliticianProfileEditorialProposalResult,
  type PoliticianProfileSnapshotPublicationResult,
  type PoliticianProfileSnapshotWithdrawalResult,
} from "@/lib/editorial-types";

function requiredText(formData: FormData, name: string): string {
  const value = formData.get(name);
  if (typeof value !== "string" || !value.trim()) throw new Error("Campo obrigatório em falta");
  return value.trim();
}

function caseId(formData: FormData): string {
  const value = requiredText(formData, "case_id");
  if (!/^[A-Za-z0-9_-]{1,200}$/.test(value)) throw new Error("Processo inválido");
  return value;
}

function expectedRevision(formData: FormData): number {
  const value = Number.parseInt(requiredText(formData, "expected_revision"), 10);
  if (!Number.isSafeInteger(value) || value < 1) throw new Error("Revisão inválida");
  return value;
}

function normalizedObject(formData: FormData): Record<string, unknown> {
  const raw = requiredText(formData, "normalized_data");
  const parsed: unknown = JSON.parse(raw);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Os dados normalizados têm de ser um objeto JSON");
  }
  return parsed as Record<string, unknown>;
}

function actionError(error: unknown): string {
  if (error instanceof EditorialApiError || error instanceof Error) return error.message.slice(0, 180);
  return "A operação não foi concluída";
}

function failureDestination(path: string, message: string): string {
  const params = new URLSearchParams({ erro: message });
  return `${path}?${params.toString()}`;
}

function parliamentScope(
  formData: FormData,
  name: "scope" | "confirmed_scope" = "scope",
): ParliamentEditorialScope {
  const scope = requiredText(formData, name);
  if (scope !== "activity" && scope !== "votes") throw new Error("Âmbito parlamentar inválido");
  return scope;
}

function sha256(formData: FormData, name: string): string {
  const value = requiredText(formData, name);
  if (!/^[0-9a-f]{64}$/.test(value)) throw new Error("Prova SHA-256 inválida");
  return value;
}

function evidenceId(formData: FormData, name: string): string {
  const value = requiredText(formData, name);
  if (!/^[A-Za-z0-9_-]{1,200}$/.test(value)) throw new Error("Prova relacional inválida");
  return value;
}

function aiPublicId(formData: FormData): string {
  const value = requiredText(formData, "expected_public_id");
  if (!/^dre-[0-9a-f]{64}$/.test(value)) throw new Error("Identificador público de IA inválido");
  return value;
}

export async function createEditorialCase(formData: FormData) {
  let created: EditorialCaseDetail | null = null;
  let failure: string | null = null;
  try {
    if (formData.get("confirm_private_only") !== "on") {
      throw new Error("Confirme que o processo permanece privado");
    }
    created = await editorialFetch<EditorialCaseDetail>("/cases", {
      method: "POST",
      body: JSON.stringify({
        kind: requiredText(formData, "kind"),
        subject_type: requiredText(formData, "subject_type").toUpperCase(),
        subject_id: requiredText(formData, "subject_id"),
        source_document_id: requiredText(formData, "source_document_id"),
        normalized_data: normalizedObject(formData),
        confirm_private_only: true,
      }),
    });
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination("/admin/revisao/novo", failure));
  revalidatePath("/admin/revisao");
  redirect(`/admin/revisao/${created!.id}?sucesso=criado`);
}

export async function createParliamentProposal(formData: FormData) {
  const snapshotId = requiredText(formData, "snapshot_id");
  if (!/^[A-Za-z0-9_-]{1,200}$/.test(snapshotId)) {
    throw new Error("Fotografia parlamentar inválida");
  }
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let created: ParliamentEditorialProposalResult | null = null;
  let failure: string | null = null;
  try {
    if (formData.get("confirm_private_only") !== "on") {
      throw new Error("Confirme que a proposta permanece privada");
    }
    if (formData.get("confirm_no_individual_inference") !== "on") {
      throw new Error("Confirme que não serão inferidos votos individuais");
    }
    created = await editorialFetch<ParliamentEditorialProposalResult>(
      "/parliament/proposals",
      {
        method: "POST",
        body: JSON.stringify({
          snapshot_id: snapshotId,
          scope: parliamentScope(formData),
          confirm_private_only: true,
          confirm_no_individual_inference: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`/admin/revisao/parlamento?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/parlamento");
  redirect(
    `/admin/revisao/${created!.case.id}?sucesso=${created!.created ? "importado" : "existente"}`,
  );
}

export async function createPoliticianProfileProposal(formData: FormData) {
  const observationId = evidenceId(formData, "observation_id");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let created: PoliticianProfileEditorialProposalResult | null = null;
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_private_only", "Confirme que a proposta permanece privada"],
      ["confirm_exact_official_id_only", "Confirme o uso exclusivo do DepId oficial"],
      ["confirm_no_mandate_inference", "Confirme que a observação não prova um mandato"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    created = await editorialFetch<PoliticianProfileEditorialProposalResult>(
      "/parliament/deputy-proposals",
      {
        method: "POST",
        body: JSON.stringify({
          observation_id: observationId,
          confirm_private_only: true,
          confirm_exact_official_id_only: true,
          confirm_no_mandate_inference: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`/admin/revisao/parlamento/deputados?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/parlamento/deputados");
  redirect(
    `/admin/revisao/${created!.case.id}?sucesso=${created!.created ? "perfil-importado" : "perfil-existente"}`,
  );
}

export async function createPoliticianMandateProposal(formData: FormData) {
  const observationId = evidenceId(formData, "observation_id");
  const sourcePeriodSha256 = sha256(formData, "source_period_sha256");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let created: PoliticianMandateEditorialProposalResult | null = null;
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_private_only", "Confirme que a proposta permanece privada"],
      ["confirm_exact_official_id_only", "Confirme o uso exclusivo do DepId oficial"],
      [
        "confirm_period_semantics_require_human_review",
        "Confirme que o significado do intervalo exige revisão humana",
      ],
      ["confirm_no_party_inference", "Confirme que não será inferida filiação partidária"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    created = await editorialFetch<PoliticianMandateEditorialProposalResult>(
      "/parliament/mandate-proposals",
      {
        method: "POST",
        body: JSON.stringify({
          observation_id: observationId,
          source_period_sha256: sourcePeriodSha256,
          confirm_private_only: true,
          confirm_exact_official_id_only: true,
          confirm_period_semantics_require_human_review: true,
          confirm_no_party_inference: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`/admin/revisao/parlamento/deputados/mandatos?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/parlamento/deputados/mandatos");
  redirect(
    `/admin/revisao/${created!.case.id}?sucesso=${created!.created ? "mandato-importado" : "mandato-existente"}`,
  );
}

export async function createPoliticianOfficeProposal(formData: FormData) {
  const observationId = evidenceId(formData, "observation_id");
  const sourcePeriodSha256 = sha256(formData, "source_period_sha256");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let created: PoliticianOfficeEditorialProposalResult | null = null;
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_private_only", "Confirme que a proposta permanece privada"],
      ["confirm_exact_official_ids_only", "Confirme o uso exclusivo de DepId e CarId oficiais"],
      [
        "confirm_observed_period_requires_human_review",
        "Confirme que o intervalo observado exige revisão humana",
      ],
      [
        "confirm_no_mandate_or_party_inference",
        "Confirme que não será inferido mandato ou filiação partidária",
      ],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    created = await editorialFetch<PoliticianOfficeEditorialProposalResult>(
      "/parliament/office-proposals",
      {
        method: "POST",
        body: JSON.stringify({
          observation_id: observationId,
          source_period_sha256: sourcePeriodSha256,
          confirm_private_only: true,
          confirm_exact_official_ids_only: true,
          confirm_observed_period_requires_human_review: true,
          confirm_no_mandate_or_party_inference: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`/admin/revisao/parlamento/deputados/cargos?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/parlamento/deputados/cargos");
  redirect(
    `/admin/revisao/${created!.case.id}?sucesso=${created!.created ? "cargo-importado" : "cargo-existente"}`,
  );
}

export async function publishPoliticianOffice(formData: FormData) {
  const caseReference = evidenceId(formData, "expected_case_id");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_source_reviewed", "Confirme a nova revisão da fonte oficial"],
      [
        "confirm_human_office_interpretation",
        "Confirme a interpretação humana do cargo e do respetivo período",
      ],
      ["confirm_exact_official_ids_only", "Confirme o uso exclusivo de DepId e CarId"],
      [
        "confirm_no_mandate_or_party_inference",
        "Confirme que não será inferido mandato ou filiação partidária",
      ],
      ["confirm_append_only_publication", "Confirme a preservação integral do histórico"],
      ["confirm_publication", "Confirme a publicação deste cargo"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    await editorialFetch<PoliticianOfficePublicationResult>(
      `/parliament/office-cases/${encodeURIComponent(caseReference)}/publication`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_case_id: caseReference,
          expected_version_id: evidenceId(formData, "expected_version_id"),
          expected_version_sha256: sha256(formData, "expected_version_sha256"),
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_period_sha256: sha256(formData, "expected_period_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          confirm_source_reviewed: true,
          confirm_human_office_interpretation: true,
          confirm_exact_official_ids_only: true,
          confirm_no_mandate_or_party_inference: true,
          confirm_append_only_publication: true,
          confirm_publication: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  const destination = "/admin/revisao/parlamento/deputados/cargos";
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`${destination}?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath(destination);
  revalidatePath("/politicos");
  revalidatePath("/");
  const params = new URLSearchParams({ legislature, sucesso: "cargo-publicado" });
  redirect(`${destination}?${params.toString()}`);
}

export async function withdrawPoliticianOffice(formData: FormData) {
  const caseReference = evidenceId(formData, "expected_case_id");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      [
        "confirm_source_and_publication_reviewed",
        "Confirme a revisão da fonte e da publicação original",
      ],
      ["confirm_exact_office", "Confirme o cargo exato a retirar"],
      ["confirm_public_effect_reviewed", "Confirme que reviu o efeito público"],
      [
        "confirm_office_and_history_preserved",
        "Confirme que o cargo e o histórico permanecem",
      ],
      [
        "confirm_no_selective_identity_or_mandate_change",
        "Confirme que identidades, mandatos e outros cargos não serão alterados",
      ],
      ["confirm_withdrawal", "Confirme a retirada deste cargo da consulta ativa"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    const reasonCategory = requiredText(formData, "reason_category");
    if (!(reasonCategory in PARLIAMENT_WITHDRAWAL_REASON_LABELS)) {
      throw new Error("Categoria de retirada inválida");
    }
    await editorialFetch<PoliticianOfficeWithdrawalResult>(
      `/parliament/office-cases/${encodeURIComponent(caseReference)}/withdrawal`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_case_id: caseReference,
          expected_revision: expectedRevision(formData),
          expected_version_id: evidenceId(formData, "expected_version_id"),
          expected_version_sha256: sha256(formData, "expected_version_sha256"),
          expected_office_id: evidenceId(formData, "expected_office_id"),
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_period_sha256: sha256(formData, "expected_period_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          expected_withdrawal_proof_sha256: sha256(
            formData,
            "expected_withdrawal_proof_sha256",
          ),
          expected_public_review_id: evidenceId(formData, "expected_public_review_id"),
          expected_publication_audit_event_id: evidenceId(
            formData,
            "expected_publication_audit_event_id",
          ),
          expected_publication_event_id: evidenceId(
            formData,
            "expected_publication_event_id",
          ),
          expected_publication_event_sha256: sha256(
            formData,
            "expected_publication_event_sha256",
          ),
          expected_public_effect_sha256: sha256(
            formData,
            "expected_public_effect_sha256",
          ),
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          reason_category: reasonCategory as ParliamentWithdrawalReason,
          confirm_source_and_publication_reviewed: true,
          confirm_exact_office: true,
          confirm_public_effect_reviewed: true,
          confirm_office_and_history_preserved: true,
          confirm_no_selective_identity_or_mandate_change: true,
          confirm_withdrawal: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  const destination = "/admin/revisao/parlamento/deputados/cargos";
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`${destination}?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath(destination);
  revalidatePath("/politicos");
  revalidatePath("/sitemap.xml");
  revalidatePath("/");
  const params = new URLSearchParams({ legislature, sucesso: "cargo-retirado" });
  redirect(`${destination}?${params.toString()}`);
}

export async function publishPoliticianMandate(formData: FormData) {
  const caseReference = evidenceId(formData, "expected_case_id");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_source_reviewed", "Confirme a nova revisão da fonte oficial"],
      [
        "confirm_human_period_interpretation",
        "Confirme a interpretação humana do intervalo oficial",
      ],
      ["confirm_exact_official_id_only", "Confirme o uso exclusivo do DepId oficial"],
      ["confirm_no_party_inference", "Confirme que não será inferida filiação partidária"],
      ["confirm_append_only_publication", "Confirme a preservação integral do histórico"],
      ["confirm_publication", "Confirme a publicação deste mandato"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    await editorialFetch<PoliticianMandatePublicationResult>(
      `/parliament/mandate-cases/${encodeURIComponent(caseReference)}/publication`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_case_id: caseReference,
          expected_version_id: evidenceId(formData, "expected_version_id"),
          expected_version_sha256: sha256(formData, "expected_version_sha256"),
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_period_sha256: sha256(formData, "expected_period_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          confirm_source_reviewed: true,
          confirm_human_period_interpretation: true,
          confirm_exact_official_id_only: true,
          confirm_no_party_inference: true,
          confirm_append_only_publication: true,
          confirm_publication: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  const destination = "/admin/revisao/parlamento/deputados/mandatos";
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`${destination}?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath(destination);
  revalidatePath("/politicos");
  revalidatePath("/");
  const params = new URLSearchParams({ legislature, sucesso: "mandato-publicado" });
  redirect(`${destination}?${params.toString()}`);
}

export async function withdrawPoliticianMandate(formData: FormData) {
  const caseReference = evidenceId(formData, "expected_case_id");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      [
        "confirm_source_and_publication_reviewed",
        "Confirme a revisão da fonte e da publicação original",
      ],
      ["confirm_exact_mandate", "Confirme o mandato exato a retirar"],
      ["confirm_public_effect_reviewed", "Confirme que reviu o efeito público"],
      [
        "confirm_mandate_and_history_preserved",
        "Confirme que o mandato e o histórico permanecem",
      ],
      [
        "confirm_no_selective_identity_change",
        "Confirme que a identidade e outros mandatos não serão alterados",
      ],
      ["confirm_withdrawal", "Confirme a retirada deste mandato da consulta ativa"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    const reasonCategory = requiredText(formData, "reason_category");
    if (!(reasonCategory in PARLIAMENT_WITHDRAWAL_REASON_LABELS)) {
      throw new Error("Categoria de retirada inválida");
    }
    await editorialFetch<PoliticianMandateWithdrawalResult>(
      `/parliament/mandate-cases/${encodeURIComponent(caseReference)}/withdrawal`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_case_id: caseReference,
          expected_revision: expectedRevision(formData),
          expected_version_id: evidenceId(formData, "expected_version_id"),
          expected_version_sha256: sha256(formData, "expected_version_sha256"),
          expected_mandate_id: evidenceId(formData, "expected_mandate_id"),
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_period_sha256: sha256(formData, "expected_period_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          expected_withdrawal_proof_sha256: sha256(
            formData,
            "expected_withdrawal_proof_sha256",
          ),
          expected_public_review_id: evidenceId(formData, "expected_public_review_id"),
          expected_publication_audit_event_id: evidenceId(
            formData,
            "expected_publication_audit_event_id",
          ),
          expected_publication_event_id: evidenceId(
            formData,
            "expected_publication_event_id",
          ),
          expected_publication_event_sha256: sha256(
            formData,
            "expected_publication_event_sha256",
          ),
          expected_public_effect_sha256: sha256(
            formData,
            "expected_public_effect_sha256",
          ),
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          reason_category: reasonCategory as ParliamentWithdrawalReason,
          confirm_source_and_publication_reviewed: true,
          confirm_exact_mandate: true,
          confirm_public_effect_reviewed: true,
          confirm_mandate_and_history_preserved: true,
          confirm_no_selective_identity_change: true,
          confirm_withdrawal: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  const destination = "/admin/revisao/parlamento/deputados/mandatos";
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`${destination}?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath(destination);
  revalidatePath("/politicos");
  revalidatePath("/sitemap.xml");
  revalidatePath("/");
  const params = new URLSearchParams({ legislature, sucesso: "mandato-retirado" });
  redirect(`${destination}?${params.toString()}`);
}

export async function publishPoliticianProfileSnapshot(formData: FormData) {
  const snapshotId = evidenceId(formData, "expected_snapshot_id");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_source_reviewed", "Confirme a nova revisão da fonte oficial"],
      ["confirm_complete_snapshot", "Confirme a fotografia completa"],
      ["confirm_exact_official_id_only", "Confirme o uso exclusivo do DepId oficial"],
      ["confirm_no_mandate_inference", "Confirme que não será criado qualquer mandato"],
      ["confirm_no_party_inference", "Confirme que nenhuma sigla será convertida em filiação"],
      ["confirm_publication", "Confirme a publicação integral dos perfis"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    const expectedDeputyCount = Number.parseInt(
      requiredText(formData, "expected_deputy_count"),
      10,
    );
    if (!Number.isSafeInteger(expectedDeputyCount) || expectedDeputyCount < 1 || expectedDeputyCount > 500) {
      throw new Error("Contagem de deputados inválida");
    }
    await editorialFetch<PoliticianProfileSnapshotPublicationResult>(
      `/parliament/deputy-snapshots/${encodeURIComponent(snapshotId)}/publication`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_snapshot_id: snapshotId,
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_snapshot_sha256: sha256(formData, "expected_snapshot_sha256"),
          expected_readiness_proof_sha256: sha256(
            formData,
            "expected_readiness_proof_sha256",
          ),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          expected_deputy_count: expectedDeputyCount,
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          confirm_source_reviewed: true,
          confirm_complete_snapshot: true,
          confirm_exact_official_id_only: true,
          confirm_no_mandate_inference: true,
          confirm_no_party_inference: true,
          confirm_publication: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  const destination = "/admin/revisao/parlamento/deputados/prontidao";
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`${destination}?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/parlamento/deputados");
  revalidatePath(destination);
  revalidatePath("/politicos");
  revalidatePath("/");
  const params = new URLSearchParams({ legislature, sucesso: "fotografia-publicada" });
  redirect(`${destination}?${params.toString()}`);
}

export async function withdrawPoliticianProfileSnapshot(formData: FormData) {
  const snapshotId = evidenceId(formData, "expected_snapshot_id");
  const legislature = requiredText(formData, "legislature").slice(0, 20);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_complete_snapshot", "Confirme a fotografia completa"],
      ["confirm_no_selective_removal", "Confirme que a retirada não é seletiva"],
      ["confirm_public_effect_reviewed", "Confirme que reviu o efeito público"],
      ["confirm_people_and_history_preserved", "Confirme a preservação das pessoas e do histórico"],
      ["confirm_withdrawal", "Confirme a retirada integral dos perfis"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    const reasonCategory = requiredText(formData, "reason_category");
    if (!(reasonCategory in PARLIAMENT_WITHDRAWAL_REASON_LABELS)) {
      throw new Error("Categoria de retirada inválida");
    }
    const expectedDeputyCount = Number.parseInt(
      requiredText(formData, "expected_deputy_count"),
      10,
    );
    if (!Number.isSafeInteger(expectedDeputyCount) || expectedDeputyCount < 1 || expectedDeputyCount > 500) {
      throw new Error("Contagem de deputados inválida");
    }
    await editorialFetch<PoliticianProfileSnapshotWithdrawalResult>(
      `/parliament/deputy-snapshots/${encodeURIComponent(snapshotId)}/withdrawal`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_snapshot_id: snapshotId,
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_snapshot_sha256: sha256(formData, "expected_snapshot_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          expected_withdrawal_proof_sha256: sha256(
            formData,
            "expected_withdrawal_proof_sha256",
          ),
          expected_public_effect_sha256: sha256(
            formData,
            "expected_public_effect_sha256",
          ),
          expected_deputy_count: expectedDeputyCount,
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          reason_category: reasonCategory as ParliamentWithdrawalReason,
          confirm_complete_snapshot: true,
          confirm_no_selective_removal: true,
          confirm_public_effect_reviewed: true,
          confirm_people_and_history_preserved: true,
          confirm_withdrawal: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  const destination = "/admin/revisao/parlamento/deputados/prontidao";
  if (failure) {
    const params = new URLSearchParams({ legislature, erro: failure });
    redirect(`${destination}?${params.toString()}`);
  }
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/parlamento/deputados");
  revalidatePath(destination);
  revalidatePath("/politicos");
  revalidatePath("/sitemap.xml");
  revalidatePath("/");
  const params = new URLSearchParams({ legislature, sucesso: "fotografia-retirada" });
  redirect(`${destination}?${params.toString()}`);
}

export async function createAiDreProposal(formData: FormData) {
  const snapshotId = evidenceId(formData, "snapshot_id");
  let created: AiDreProposalResult | null = null;
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_private_only", "Confirme que a proposta permanece privada"],
      ["confirm_archived_source_only", "Confirme o uso exclusivo da fonte DRE arquivada"],
      ["confirm_ai_not_source", "Confirme que a IA não é fonte nem revisora"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    created = await editorialFetch<AiDreProposalResult>("/ai/dre-proposals", {
      method: "POST",
      body: JSON.stringify({
        snapshot_id: snapshotId,
        confirm_private_only: true,
        confirm_archived_source_only: true,
        confirm_ai_not_source: true,
      }),
    });
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination("/admin/revisao/ia", failure));
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/ia");
  redirect(
    `/admin/revisao/${created!.case.id}?sucesso=${created!.created ? "ai-created" : "ai-existing"}`,
  );
}

export async function regenerateAiDreProposal(formData: FormData) {
  const id = caseId(formData);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_private_only", "Confirme que a nova versão permanece privada"],
      ["confirm_archived_source_only", "Confirme o uso exclusivo da fonte DRE arquivada"],
      ["confirm_ai_not_source", "Confirme que a IA não é fonte nem revisora"],
      ["confirm_new_immutable_version", "Confirme que será acrescentada uma nova versão"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    await editorialFetch<AiDreProposalResult>(
      `/ai/cases/${encodeURIComponent(id)}/regenerate`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_revision: expectedRevision(formData),
          expected_current_version_sha256: sha256(
            formData,
            "expected_current_version_sha256",
          ),
          rationale: requiredText(formData, "rationale"),
          confirm_private_only: true,
          confirm_archived_source_only: true,
          confirm_ai_not_source: true,
          confirm_new_immutable_version: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination(`/admin/revisao/${id}`, failure));
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/ia");
  revalidatePath(`/admin/revisao/${id}`);
  redirect(`/admin/revisao/${id}?sucesso=ai-regenerated`);
}

export async function publishAiExplanation(formData: FormData) {
  const id = caseId(formData);
  const publicId = aiPublicId(formData);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_source_reviewed", "Confirme a revisão integral da fonte oficial"],
      ["confirm_ai_label_reviewed", "Confirme o rótulo público de conteúdo gerado por IA"],
      [
        "confirm_no_prediction_or_recommendation",
        "Confirme que não existe previsão nem recomendação eleitoral",
      ],
      ["confirm_publication", "Confirme a publicação desta versão exata"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    await editorialFetch<AiEditorialPublicationResult>(
      `/ai/cases/${encodeURIComponent(id)}/publication`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_revision: expectedRevision(formData),
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          expected_public_id: publicId,
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_normalised_text_sha256: sha256(
            formData,
            "expected_normalised_text_sha256",
          ),
          expected_editorial_sha256: sha256(formData, "expected_editorial_sha256"),
          expected_output_sha256: sha256(formData, "expected_output_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          confirm_source_reviewed: true,
          confirm_ai_label_reviewed: true,
          confirm_no_prediction_or_recommendation: true,
          confirm_publication: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination(`/admin/revisao/${id}`, failure));
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/ia");
  revalidatePath(`/admin/revisao/${id}`);
  revalidatePath("/explicacoes");
  revalidatePath(`/explicacoes/${publicId}`);
  revalidatePath("/sitemap.xml");
  revalidatePath("/");
  redirect(`/admin/revisao/${id}?sucesso=ai-published`);
}

export async function withdrawAiExplanation(formData: FormData) {
  const id = caseId(formData);
  const publicId = aiPublicId(formData);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_no_selective_removal", "Confirme que a retirada não é seletiva"],
      ["confirm_public_effect_reviewed", "Confirme que reviu o efeito público"],
      ["confirm_withdrawal", "Confirme a retirada integral desta explicação"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    const reasonCategory = requiredText(formData, "reason_category");
    if (!(reasonCategory in PARLIAMENT_WITHDRAWAL_REASON_LABELS)) {
      throw new Error("Categoria de retirada inválida");
    }
    await editorialFetch<AiEditorialWithdrawalResult>(
      `/ai/cases/${encodeURIComponent(id)}/withdrawal`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_revision: expectedRevision(formData),
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          reason_category: reasonCategory as ParliamentWithdrawalReason,
          expected_public_id: publicId,
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_normalised_text_sha256: sha256(
            formData,
            "expected_normalised_text_sha256",
          ),
          expected_editorial_sha256: sha256(formData, "expected_editorial_sha256"),
          expected_output_sha256: sha256(formData, "expected_output_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          expected_public_review_id: evidenceId(formData, "expected_public_review_id"),
          expected_publication_audit_event_id: evidenceId(
            formData,
            "expected_publication_audit_event_id",
          ),
          expected_publication_event_id: evidenceId(
            formData,
            "expected_publication_event_id",
          ),
          expected_publication_event_sha256: sha256(
            formData,
            "expected_publication_event_sha256",
          ),
          expected_public_effect_sha256: sha256(
            formData,
            "expected_public_effect_sha256",
          ),
          confirm_no_selective_removal: true,
          confirm_public_effect_reviewed: true,
          confirm_withdrawal: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination(`/admin/revisao/${id}`, failure));
  revalidatePath("/admin/revisao");
  revalidatePath("/admin/revisao/ia");
  revalidatePath(`/admin/revisao/${id}`);
  revalidatePath("/explicacoes");
  revalidatePath(`/explicacoes/${publicId}`);
  revalidatePath("/sitemap.xml");
  revalidatePath("/");
  redirect(`/admin/revisao/${id}?sucesso=ai-withdrawn`);
}

export async function startEditorialReview(formData: FormData) {
  await decisionAction(formData, "start-review", false);
}

export async function approveEditorialCase(formData: FormData) {
  if (formData.get("confirm_source_reviewed") !== "on") {
    const id = caseId(formData);
    redirect(failureDestination(`/admin/revisao/${id}`, "Confirme a revisão da fonte oficial"));
  }
  await decisionAction(formData, "approve", true);
}

export async function rejectEditorialCase(formData: FormData) {
  await decisionAction(formData, "reject", false);
}

async function decisionAction(
  formData: FormData,
  action: "start-review" | "approve" | "reject",
  confirmSource: boolean,
) {
  const id = caseId(formData);
  let failure: string | null = null;
  try {
    await editorialFetch<EditorialCaseDetail>(`/cases/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: expectedRevision(formData),
        rationale: requiredText(formData, "rationale"),
        ...(confirmSource ? { confirm_source_reviewed: true } : {}),
      }),
    });
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination(`/admin/revisao/${id}`, failure));
  revalidatePath("/admin/revisao");
  revalidatePath(`/admin/revisao/${id}`);
  redirect(`/admin/revisao/${id}?sucesso=${action}`);
}

export async function correctEditorialCase(formData: FormData) {
  const id = caseId(formData);
  let failure: string | null = null;
  try {
    await editorialFetch<EditorialCaseDetail>(`/cases/${id}/correct`, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: expectedRevision(formData),
        rationale: requiredText(formData, "rationale"),
        normalized_data: normalizedObject(formData),
      }),
    });
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination(`/admin/revisao/${id}`, failure));
  revalidatePath("/admin/revisao");
  revalidatePath(`/admin/revisao/${id}`);
  redirect(`/admin/revisao/${id}?sucesso=correct`);
}

export async function publishParliamentCase(formData: FormData) {
  const id = caseId(formData);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_source_reviewed", "Confirme a nova revisão da fonte oficial"],
      ["confirm_no_individual_inference", "Confirme que não inferiu votos individuais"],
      ["confirm_publication", "Confirme a publicação deste âmbito específico"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    const snapshotId = requiredText(formData, "expected_snapshot_id");
    if (!/^[A-Za-z0-9_-]{1,200}$/.test(snapshotId)) {
      throw new Error("Fotografia parlamentar inválida");
    }
    await editorialFetch<ParliamentEditorialPublicationResult>(
      `/parliament/cases/${encodeURIComponent(id)}/publication`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_revision: expectedRevision(formData),
          rationale: requiredText(formData, "rationale"),
          confirmed_scope: parliamentScope(formData, "confirmed_scope"),
          expected_snapshot_id: snapshotId,
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_snapshot_sha256: sha256(formData, "expected_snapshot_sha256"),
          expected_editorial_sha256: sha256(formData, "expected_editorial_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          confirm_source_reviewed: true,
          confirm_no_individual_inference: true,
          confirm_publication: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination(`/admin/revisao/${id}`, failure));
  revalidatePath("/admin/revisao");
  revalidatePath(`/admin/revisao/${id}`);
  revalidatePath("/atividade-parlamentar");
  revalidatePath("/");
  redirect(`/admin/revisao/${id}?sucesso=published`);
}

export async function withdrawParliamentCase(formData: FormData) {
  const id = caseId(formData);
  let failure: string | null = null;
  try {
    for (const [field, message] of [
      ["confirm_no_selective_removal", "Confirme que a retirada não é seletiva"],
      ["confirm_public_effect_reviewed", "Confirme que reviu o efeito público calculado"],
      ["confirm_withdrawal", "Confirme a retirada integral deste âmbito"],
    ] as const) {
      if (formData.get(field) !== "on") throw new Error(message);
    }
    const snapshotId = requiredText(formData, "expected_snapshot_id");
    if (!/^[A-Za-z0-9_-]{1,200}$/.test(snapshotId)) {
      throw new Error("Fotografia parlamentar inválida");
    }
    const reasonCategory = requiredText(formData, "reason_category");
    if (!(reasonCategory in PARLIAMENT_WITHDRAWAL_REASON_LABELS)) {
      throw new Error("Categoria de retirada inválida");
    }
    await editorialFetch<ParliamentEditorialWithdrawalResult>(
      `/parliament/cases/${encodeURIComponent(id)}/withdrawal`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_revision: expectedRevision(formData),
          rationale: requiredText(formData, "rationale"),
          public_rationale: requiredText(formData, "public_rationale"),
          reason_category: reasonCategory as ParliamentWithdrawalReason,
          confirmed_scope: parliamentScope(formData, "confirmed_scope"),
          expected_snapshot_id: snapshotId,
          expected_source_sha256: sha256(formData, "expected_source_sha256"),
          expected_snapshot_sha256: sha256(formData, "expected_snapshot_sha256"),
          expected_editorial_sha256: sha256(formData, "expected_editorial_sha256"),
          expected_publication_proof_sha256: sha256(
            formData,
            "expected_publication_proof_sha256",
          ),
          expected_public_review_id: evidenceId(formData, "expected_public_review_id"),
          expected_publication_audit_event_id: evidenceId(
            formData,
            "expected_publication_audit_event_id",
          ),
          expected_publication_event_id: evidenceId(
            formData,
            "expected_publication_event_id",
          ),
          expected_publication_event_sha256: sha256(
            formData,
            "expected_publication_event_sha256",
          ),
          expected_public_effect_sha256: sha256(
            formData,
            "expected_public_effect_sha256",
          ),
          confirm_no_selective_removal: true,
          confirm_public_effect_reviewed: true,
          confirm_withdrawal: true,
        }),
      },
    );
  } catch (error) {
    failure = actionError(error);
  }
  if (failure) redirect(failureDestination(`/admin/revisao/${id}`, failure));
  revalidatePath("/admin/revisao");
  revalidatePath(`/admin/revisao/${id}`);
  revalidatePath("/atividade-parlamentar");
  revalidatePath("/");
  redirect(`/admin/revisao/${id}?sucesso=withdrawn`);
}
