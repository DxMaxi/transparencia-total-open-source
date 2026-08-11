function publicSiteUrl(): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (configured) {
    try {
      const parsed = new URL(configured);
      const localHttp =
        parsed.protocol === "http:" && ["localhost", "127.0.0.1"].includes(parsed.hostname);
      if (
        (parsed.protocol === "https:" || localHttp) &&
        !parsed.username &&
        !parsed.password &&
        ["", "/"].includes(parsed.pathname) &&
        !parsed.search &&
        !parsed.hash
      ) {
        return parsed.toString().replace(/\/$/, "");
      }
    } catch {
      // O valor de produção permanece o fallback seguro para metadados.
    }
  }
  return "https://www.transparenciatotal.pt";
}

export const SITE_URL = publicSiteUrl();
export const CONTACT_EMAIL = "maximiano.jp.moreira@gmail.com";
export const PROJECT_NAME = "Transparência Total / Fator Cívico";
export const LEGAL_RESPONSIBLE_NAME =
  process.env.NEXT_PUBLIC_LEGAL_RESPONSIBLE_NAME?.trim() || "Maximiano Moreira";
export const LEGAL_RESPONSIBLE = LEGAL_RESPONSIBLE_NAME;
export const LEGAL_ADDRESS = process.env.NEXT_PUBLIC_LEGAL_ADDRESS?.trim() ?? "";
export const LEGAL_TAX_ID = process.env.NEXT_PUBLIC_LEGAL_TAX_ID?.trim() ?? "";
export const LEGAL_REGISTRATION = process.env.NEXT_PUBLIC_LEGAL_REGISTRATION?.trim() ?? "";
export const LEGAL_UPDATED_AT = "11 de agosto de 2026";
