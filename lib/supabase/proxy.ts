import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getSupabasePublicConfig } from "./config";

export async function refreshSupabaseSession(
  request: NextRequest,
  forwardedHeaders: Headers = request.headers,
) {
  const config = getSupabasePublicConfig();
  const nextResponse = () => NextResponse.next({ request: { headers: forwardedHeaders } });
  if (!config) return nextResponse();

  let response = nextResponse();
  const supabase = createServerClient(config.url, config.publishableKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = nextResponse();
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });

  // Não confiar em getSession para identidade: getClaims valida a assinatura.
  await supabase.auth.getClaims();
  return response;
}
