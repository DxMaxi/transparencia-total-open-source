export const PUBLIC_API_TIMEOUT_MS = 10_000;
export const PUBLIC_API_REVALIDATE_SECONDS = 60;

export type PublicApiFailureReason =
  | "not_configured"
  | "timeout"
  | "abort"
  | "network"
  | "http"
  | "invalid_json"
  | "unknown";

type NamedError = {
  name?: unknown;
};

export function publicApiEndpointLabel(path: string): string {
  try {
    const parsed = new URL(path, "https://public-api.invalid");
    return parsed.pathname.startsWith("/api/") ? parsed.pathname : "/invalid";
  } catch {
    return "/invalid";
  }
}

export function classifyPublicApiError(error: unknown): PublicApiFailureReason {
  const name =
    typeof error === "object" && error !== null && "name" in error
      ? String((error as NamedError).name)
      : "";

  if (name === "TimeoutError") return "timeout";
  if (name === "AbortError") return "abort";
  if (name === "SyntaxError" || error instanceof SyntaxError) return "invalid_json";
  if (name === "TypeError" || error instanceof TypeError) return "network";
  return "unknown";
}
