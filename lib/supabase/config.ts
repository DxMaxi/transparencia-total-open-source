export type SupabasePublicConfig = {
  url: string;
  publishableKey: string;
};

export function getSupabasePublicConfig(): SupabasePublicConfig | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url || !publishableKey) return null;
  try {
    const parsed = new URL(url);
    const localHttp =
      parsed.protocol === "http:" && ["localhost", "127.0.0.1"].includes(parsed.hostname);
    if (parsed.protocol !== "https:" && !localHttp) return null;
    if (
      parsed.username ||
      parsed.password ||
      !["", "/"].includes(parsed.pathname) ||
      parsed.search ||
      parsed.hash
    )
      return null;
    return { url: parsed.toString().replace(/\/$/, ""), publishableKey };
  } catch {
    return null;
  }
}
