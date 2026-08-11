import "server-only";

import { cache } from "react";
import { redirect } from "next/navigation";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import type { StaffSession } from "@/lib/editorial-types";

export class EditorialApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function apiBaseUrl(): string {
  const configured =
    process.env.ADMIN_API_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!configured) throw new EditorialApiError("API privada não configurada", 503);
  try {
    const url = new URL(configured);
    const localHttp =
      url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname);
    if (
      (url.protocol !== "https:" && !localHttp) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      throw new Error("unsafe API URL");
    }
    return url.toString().replace(/\/$/, "");
  } catch {
    throw new EditorialApiError("Endereço da API privada inválido", 503);
  }
}

export const getEditorialContext = cache(async () => {
  const supabase = await createServerSupabaseClient();
  if (!supabase) redirect("/auth/entrar?erro=configuracao");

  const claimsResult = await supabase.auth.getClaims();
  const claims = claimsResult.data?.claims;
  if (claimsResult.error || !claims) redirect("/auth/entrar?erro=sessao");
  if (claims.aal !== "aal2") redirect("/auth/mfa?next=/admin/revisao");

  // getClaims já validou a identidade; getSession é usado apenas para obter o
  // bearer bruto necessário na chamada servidor-a-servidor.
  const sessionResult = await supabase.auth.getSession();
  const accessToken = sessionResult.data.session?.access_token;
  if (!accessToken) redirect("/auth/entrar?erro=sessao");

  const response = await fetch(`${apiBaseUrl()}/api/v1/editorial/session`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/auth/entrar?erro=sessao");
  if (response.status === 403) redirect("/auth/entrar?erro=sem-acesso");
  if (!response.ok) {
    throw new EditorialApiError("Não foi possível validar o acesso editorial", response.status);
  }
  return {
    accessToken,
    staff: (await response.json()) as StaffSession,
  };
});

export async function editorialFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { accessToken } = await getEditorialContext();
  const response = await fetch(`${apiBaseUrl()}/api/v1/editorial${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = "A operação editorial não foi concluída";
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") message = payload.detail;
    } catch {
      // Mantém uma mensagem neutra quando a API não devolve JSON.
    }
    throw new EditorialApiError(message, response.status);
  }
  return (await response.json()) as T;
}
