export type OrganisationKind =
  | "PUBLIC_BODY"
  | "COMPANY"
  | "NON_PROFIT"
  | "EUROPEAN_BODY"
  | "OTHER";

export type PublicOrganisationSummary = {
  id: string;
  legal_name: string;
  kind: OrganisationKind;
  registry_record_id: string;
  public_record_sha256: string;
  published_at: string;
};

export type PublicOrganisationReply = {
  public_reference: string;
  original_record_sha256: string;
  claimant_public_name: string;
  claimant_role: string;
  statement_text: string;
  statement_sha256: string;
  official_response_url: string | null;
  submitted_at: string;
};

export type PublicOrganisation = PublicOrganisationSummary & {
  official_url: string;
  source_record_sha256: string;
  source: {
    publisher: "IRN";
    title: string;
    url: string;
    retrieved_at: string;
    content_sha256: string;
  };
  replies: PublicOrganisationReply[];
  coverage_notice: string;
};

export type PublicOrganisationHistory = {
  public_id: string;
  action: "PUBLISH" | "WITHDRAW";
  public_record_sha256: string;
  source_record_sha256: string;
  public_rationale: string;
  actor_alias: string;
  occurred_at: string;
};

export type PublicOrganisationHistoryResult = {
  public_id: string;
  items: PublicOrganisationHistory[];
  replies: PublicOrganisationReply[];
  coverage_notice: string;
};

type LoadResult<T> =
  | { status: "ok"; data: T }
  | { status: "not_found" | "unavailable" };

const idPattern = /^base_public_org_[0-9a-f]{32}$/;
const hashPattern = /^[0-9a-f]{64}$/;
const kinds = new Set<OrganisationKind>([
  "PUBLIC_BODY",
  "COMPANY",
  "NON_PROFIT",
  "EUROPEAN_BODY",
  "OTHER",
]);
export const ORGANISATION_KIND_LABELS: Record<OrganisationKind, string> = {
  PUBLIC_BODY: "Entidade pública",
  COMPANY: "Empresa",
  NON_PROFIT: "Organização sem fins lucrativos",
  EUROPEAN_BODY: "Entidade europeia",
  OTHER: "Outra organização",
};
const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

function object(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function timestamp(value: unknown): string | null {
  const result = text(value);
  return result !== null && Number.isFinite(Date.parse(result)) ? result : null;
}

function publicUrl(value: unknown, exactIrn = false): string | null {
  const result = text(value);
  if (result === null) return null;
  try {
    const url = new URL(result);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      (exactIrn &&
        (url.hostname !== "publicacoes.mj.pt" ||
          url.port !== "" ||
          url.pathname !== "/DetalhePublicacao.aspx" ||
          url.search ||
          url.hash))
    ) {
      return null;
    }
    return result;
  } catch {
    return null;
  }
}

function summary(value: unknown): PublicOrganisationSummary | null {
  const item = object(value);
  if (item === null) return null;
  const id = text(item.id);
  const legalName = text(item.legal_name);
  const kind = text(item.kind);
  const registryRecordId = text(item.registry_record_id);
  const publicRecordSha256 = text(item.public_record_sha256);
  const publishedAt = timestamp(item.published_at);
  if (
    id === null ||
    !idPattern.test(id) ||
    legalName === null ||
    kind === null ||
    !kinds.has(kind as OrganisationKind) ||
    registryRecordId === null ||
    publicRecordSha256 === null ||
    !hashPattern.test(publicRecordSha256) ||
    publishedAt === null
  ) {
    return null;
  }
  return {
    id,
    legal_name: legalName,
    kind: kind as OrganisationKind,
    registry_record_id: registryRecordId,
    public_record_sha256: publicRecordSha256,
    published_at: publishedAt,
  };
}

function reply(value: unknown): PublicOrganisationReply | null {
  const item = object(value);
  if (item === null) return null;
  const publicReference = text(item.public_reference);
  const originalRecordSha256 = text(item.original_record_sha256);
  const claimantPublicName = text(item.claimant_public_name);
  const claimantRole = text(item.claimant_role);
  const statementText = text(item.statement_text);
  const statementSha256 = text(item.statement_sha256);
  const submittedAt = timestamp(item.submitted_at);
  const officialResponseUrl =
    item.official_response_url === null
      ? null
      : publicUrl(item.official_response_url);
  if (
    publicReference === null ||
    originalRecordSha256 === null ||
    !hashPattern.test(originalRecordSha256) ||
    claimantPublicName === null ||
    claimantRole === null ||
    statementText === null ||
    statementSha256 === null ||
    !hashPattern.test(statementSha256) ||
    submittedAt === null ||
    (item.official_response_url !== null && officialResponseUrl === null)
  ) {
    return null;
  }
  return {
    public_reference: publicReference,
    original_record_sha256: originalRecordSha256,
    claimant_public_name: claimantPublicName,
    claimant_role: claimantRole,
    statement_text: statementText,
    statement_sha256: statementSha256,
    official_response_url: officialResponseUrl,
    submitted_at: submittedAt,
  };
}

function historyItem(value: unknown): PublicOrganisationHistory | null {
  const item = object(value);
  if (item === null) return null;
  const publicId = text(item.public_id);
  const action = text(item.action);
  const publicRecordSha256 = text(item.public_record_sha256);
  const sourceRecordSha256 = text(item.source_record_sha256);
  const publicRationale = text(item.public_rationale);
  const actorAlias = text(item.actor_alias);
  const occurredAt = timestamp(item.occurred_at);
  if (
    publicId === null ||
    !idPattern.test(publicId) ||
    (action !== "PUBLISH" && action !== "WITHDRAW") ||
    publicRecordSha256 === null ||
    !hashPattern.test(publicRecordSha256) ||
    sourceRecordSha256 === null ||
    !hashPattern.test(sourceRecordSha256) ||
    publicRationale === null ||
    actorAlias === null ||
    occurredAt === null
  ) {
    return null;
  }
  return {
    public_id: publicId,
    action,
    public_record_sha256: publicRecordSha256,
    source_record_sha256: sourceRecordSha256,
    public_rationale: publicRationale,
    actor_alias: actorAlias,
    occurred_at: occurredAt,
  };
}

async function request(
  path: string,
): Promise<{ status: number; body: unknown } | null> {
  if (!apiBase) return null;
  try {
    const response = await fetch(`${apiBase}${path}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    return {
      status: response.status,
      body: await response.json().catch(() => null),
    };
  } catch {
    return null;
  }
}

export async function loadPublicOrganisations(
  page: number,
  limit = 24,
): Promise<
  LoadResult<{
    items: PublicOrganisationSummary[];
    total: number;
    limit: number;
    offset: number;
    coverage_notice: string;
  }>
> {
  const safeLimit =
    Number.isSafeInteger(limit) && limit >= 1 && limit <= 100 ? limit : 24;
  const maximumPage = Math.floor(10_000 / safeLimit) + 1;
  const safePage =
    Number.isSafeInteger(page) && page > 0
      ? Math.min(page, maximumPage)
      : 1;
  const response = await request(
    `/api/v1/public/organisations?limit=${safeLimit}&offset=${
      (safePage - 1) * safeLimit
    }`,
  );
  const body = object(response?.body);
  if (response?.status !== 200 || body === null || !Array.isArray(body.items)) {
    return { status: "unavailable" };
  }
  const items = body.items.map(summary);
  const total = body.total;
  const returnedLimit = body.limit;
  const offset = body.offset;
  const coverageNotice = text(body.coverage_notice);
  if (
    items.some((item) => item === null) ||
    !Number.isSafeInteger(total) ||
    Number(total) < 0 ||
    returnedLimit !== safeLimit ||
    offset !== (safePage - 1) * safeLimit ||
    coverageNotice === null
  ) {
    return { status: "unavailable" };
  }
  return {
    status: "ok",
    data: {
      items: items as PublicOrganisationSummary[],
      total: Number(total),
      limit: safeLimit,
      offset: Number(offset),
      coverage_notice: coverageNotice,
    },
  };
}

export async function loadPublicOrganisation(
  publicId: string,
): Promise<LoadResult<PublicOrganisation>> {
  if (!idPattern.test(publicId)) return { status: "not_found" };
  const response = await request(
    `/api/v1/public/organisations/${encodeURIComponent(publicId)}`,
  );
  if (response === null) return { status: "unavailable" };
  if (response.status === 404) return { status: "not_found" };
  const body = object(response.body);
  const base = summary(body);
  const source = object(body?.source);
  const sourceTitle = text(source?.title);
  const sourceUrl = publicUrl(source?.url, true);
  const retrievedAt = timestamp(source?.retrieved_at);
  const sourceContentSha256 = text(source?.content_sha256);
  const officialUrl = publicUrl(body?.official_url, true);
  const sourceRecordSha256 = text(body?.source_record_sha256);
  const coverageNotice = text(body?.coverage_notice);
  const replies = Array.isArray(body?.replies)
    ? body.replies.map(reply)
    : null;
  if (
    response.status !== 200 ||
    body === null ||
    base === null ||
    source === null ||
    source.publisher !== "IRN" ||
    sourceTitle === null ||
    sourceUrl === null ||
    retrievedAt === null ||
    sourceContentSha256 === null ||
    !hashPattern.test(sourceContentSha256) ||
    officialUrl === null ||
    sourceRecordSha256 === null ||
    !hashPattern.test(sourceRecordSha256) ||
    coverageNotice === null ||
    replies === null ||
    replies.some((item) => item === null)
  ) {
    return { status: "unavailable" };
  }
  return {
    status: "ok",
    data: {
      ...base,
      official_url: officialUrl,
      source_record_sha256: sourceRecordSha256,
      source: {
        publisher: "IRN",
        title: sourceTitle,
        url: sourceUrl,
        retrieved_at: retrievedAt,
        content_sha256: sourceContentSha256,
      },
      replies: replies as PublicOrganisationReply[],
      coverage_notice: coverageNotice,
    },
  };
}

export async function loadPublicOrganisationHistory(
  publicId: string,
): Promise<LoadResult<PublicOrganisationHistoryResult>> {
  if (!idPattern.test(publicId)) return { status: "not_found" };
  const response = await request(
    `/api/v1/public/organisations/${encodeURIComponent(
      publicId,
    )}/publication-history`,
  );
  if (response === null) return { status: "unavailable" };
  if (response.status === 404) return { status: "not_found" };
  const body = object(response.body);
  if (
    response.status !== 200 ||
    body === null ||
    !Array.isArray(body.items) ||
    !Array.isArray(body.replies)
  ) {
    return { status: "unavailable" };
  }
  const returnedPublicId = text(body.public_id);
  const coverageNotice = text(body.coverage_notice);
  const items = body.items.map(historyItem);
  const replies = body.replies.map(reply);
  const snapshotHashes = new Set(
    items.flatMap((item) => (item ? [item.public_record_sha256] : [])),
  );
  if (
    returnedPublicId !== publicId ||
    coverageNotice === null ||
    items.some((item) => item === null || item.public_id !== publicId) ||
    replies.some(
      (item) =>
        item === null || !snapshotHashes.has(item.original_record_sha256),
    )
  ) {
    return { status: "unavailable" };
  }
  return {
    status: "ok",
    data: {
      public_id: publicId,
      items: items as PublicOrganisationHistory[],
      replies: replies as PublicOrganisationReply[],
      coverage_notice: coverageNotice,
    },
  };
}
