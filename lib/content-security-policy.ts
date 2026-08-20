type ContentSecurityPolicyOptions = {
  isDevelopment: boolean;
  nonce?: string;
};

function configuredOrigin(value: string | undefined): string | null {
  const configured = value?.trim();
  if (!configured) return null;
  try {
    const url = new URL(configured);
    const localHttp =
      url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname);
    return url.protocol === "https:" || localHttp ? url.origin : null;
  } catch {
    return null;
  }
}

export function buildContentSecurityPolicy({
  isDevelopment,
  nonce,
}: ContentSecurityPolicyOptions): string {
  const connectSources = [
    "'self'",
    configuredOrigin(process.env.NEXT_PUBLIC_API_URL),
    configuredOrigin(process.env.NEXT_PUBLIC_SUPABASE_URL),
    ...(isDevelopment ? ["ws:", "wss:"] : []),
  ]
    .filter(Boolean)
    .join(" ");
  const scriptSources = nonce
    ? ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(isDevelopment ? ["'unsafe-eval'"] : [])]
    : ["'self'", "'unsafe-inline'", ...(isDevelopment ? ["'unsafe-eval'"] : [])];
  const styleSources =
    nonce && !isDevelopment
      ? ["'self'", `'nonce-${nonce}'`]
      : ["'self'", "'unsafe-inline'"];

  return [
    "default-src 'self'",
    "base-uri 'self'",
    `connect-src ${connectSources}`,
    "font-src 'self' data:",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "frame-src 'none'",
    "img-src 'self' data: https:",
    "manifest-src 'self'",
    "media-src 'self'",
    "object-src 'none'",
    `script-src ${scriptSources.join(" ")}`,
    `style-src ${styleSources.join(" ")}`,
    isDevelopment ? "worker-src 'self' blob:" : "worker-src 'self'",
    ...(!isDevelopment ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}
