"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { EditorialApiError, editorialFetch } from "@/lib/editorial-api";
import type { EditorialCaseDetail } from "@/lib/editorial-types";

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
