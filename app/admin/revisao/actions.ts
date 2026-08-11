"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { EditorialApiError, editorialFetch } from "@/lib/editorial-api";
import {
  PARLIAMENT_WITHDRAWAL_REASON_LABELS,
  type EditorialCaseDetail,
  type ParliamentEditorialPublicationResult,
  type ParliamentEditorialProposalResult,
  type ParliamentEditorialScope,
  type ParliamentEditorialWithdrawalResult,
  type ParliamentWithdrawalReason,
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
