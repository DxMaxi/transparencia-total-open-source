import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";

function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/auth/mfa";
  return value.startsWith("/admin/") || value.startsWith("/auth/mfa")
    ? value
    : "/auth/mfa";
}

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const destination = safeNext(url.searchParams.get("next"));
  const supabase = await createServerSupabaseClient();
  if (!supabase) return NextResponse.redirect(new URL("/auth/entrar?erro=configuracao", url));

  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;
  let error: unknown = null;
  if (code) {
    ({ error } = await supabase.auth.exchangeCodeForSession(code));
  } else if (tokenHash && type) {
    ({ error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type }));
  } else {
    error = new Error("Parâmetros de confirmação em falta");
  }

  if (error) return NextResponse.redirect(new URL("/auth/entrar?erro=confirmacao", url));
  return NextResponse.redirect(new URL(destination, url));
}
