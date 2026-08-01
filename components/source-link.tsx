import { ExternalLinkIcon } from "@/components/icons";
import type { OfficialSource } from "@/types/domain";

export function SourceLink({
  source,
  compact = false,
}: {
  source: OfficialSource;
  compact?: boolean;
}) {
  return (
    <a
      className={compact ? "source-link source-link--compact" : "source-link"}
      href={source.url}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={`${source.label} — abrir fonte oficial num novo separador`}
    >
      <span className="source-publisher">{source.publisher}</span>
      <span>{source.label}</span>
      <ExternalLinkIcon className="source-link__icon" />
    </a>
  );
}
