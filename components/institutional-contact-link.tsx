import Link from "next/link";
import { CONTACT_EMAIL } from "@/lib/site";

export function InstitutionalContactLink({
  className,
  fallbackLabel = "canal institucional em preparação",
}: {
  className?: string;
  fallbackLabel?: string;
}) {
  if (CONTACT_EMAIL) {
    return (
      <a className={className} href={`mailto:${CONTACT_EMAIL}`}>
        {CONTACT_EMAIL}
      </a>
    );
  }

  return (
    <Link className={className} href="/contacto">
      {fallbackLabel}
    </Link>
  );
}
