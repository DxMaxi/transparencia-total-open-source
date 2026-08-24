import type { OfficialSource } from "@/types/domain";

export type PublicDataMode = "LIVE" | "EMPTY" | "UNAVAILABLE";

export type PublicRecordCounts = {
  politicians: number;
  parliamentSessions: number;
  parliamentInitiatives: number;
  parliamentVotes: number;
  promises: number;
  contracts: number;
  relationships: number;
  news: number;
  citizenAlerts: number;
};

export type SourceSyncState = {
  sourceName: string;
  status: "NEVER" | "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED";
  startedAt?: string;
  finishedAt?: string;
  recordsRead: number;
  recordsWritten: number;
  warningCount: number;
  datasetUrl?: string;
  codeVersion?: string;
};

export type PublicDataStatus = {
  mode: PublicDataMode;
  generatedAt: string;
  databaseConfigured: boolean;
  counts: PublicRecordCounts;
  sources: SourceSyncState[];
  message: string;
  publicationRule: string;
};

export type PublicGlobalSearchKind =
  | "politicians"
  | "parliament_sessions"
  | "parliament_initiatives"
  | "parliament_votes"
  | "promises"
  | "ai_explanations";

export type PublicGlobalSearchItem = {
  id: string;
  kind: PublicGlobalSearchKind;
  title: string;
  description: string;
  href: string;
  source: OfficialSource;
  verifiedAt: string;
  observedAt?: string;
  coverageState: "AVAILABLE";
  coverageNote: string;
};

export type PublicGlobalSearchSection = {
  kind: PublicGlobalSearchKind;
  label: string;
  availability: "AVAILABLE" | "UNAVAILABLE";
  total?: number;
  totalIsExact: boolean;
  items: PublicGlobalSearchItem[];
  viewAllHref: string;
  coverageNote: string;
};

export type PublicGlobalSearch = {
  query: string;
  legislature: string;
  sectionLimit: number;
  totalResults: number;
  availableSections: number;
  unavailableSections: number;
  sections: PublicGlobalSearchSection[];
  publicationRule: string;
  searchRule: string;
  available: boolean;
};

export type PublicAiSummary = {
  title: string;
  summary2Minutes: string;
  whatChanges: string[];
  whoIsAffected: string[];
  datesAndDeadlines: string[];
  dutiesAndRights: string[];
  uncertainties: string[];
  glossary: Array<{ term: string; explanation: string }>;
  sourceAnchors: Array<{ section: string; reason: string }>;
};

export type PublicAiExplanation = {
  id: string;
  contentKind: "AI_EXPLANATION";
  label: "Explicação gerada por IA — revista por humano";
  aiGenerated: true;
  aiIsSource: false;
  humanReviewRequired: true;
  notPrediction: true;
  noVotingRecommendation: true;
  abstained: boolean;
  summary: PublicAiSummary;
  source: {
    publisher: "DRE";
    label: string;
    title: string;
    officialIdentifier?: string;
    url: string;
    retrievedAt: string;
    publishedAt?: string;
    contentSha256: string;
    normalisedTextSha256: string;
  };
  generation: {
    provider: string;
    model: string;
    promptVersion: string;
    promptSha256: string;
    inputSha256: string;
    outputSha256: string;
    generatedAt: string;
    sourceCharacters: number;
    processedCharacters: number;
    sourceTruncated: boolean;
    providerStore: false;
  };
  editorial: {
    humanReviewed: true;
    reviewedBy: string;
    publishedAt: string;
    editorialVersionSha256: string;
    publicationProofSha256: string;
    publicationEventReferenceSha256: string;
  };
  limitations: string[];
};

export type PublicAiExplanationList = {
  items: PublicAiExplanation[];
  total: number;
  limit: number;
  offset: number;
  query?: string;
  totalIsExact: true;
  publicationRule: string;
  available: boolean;
};

export type PublicAiPublicationHistoryItem = {
  eventReferenceSha256: string;
  action: "PUBLISHED" | "WITHDRAWN";
  publicId: string;
  title: string;
  decidedAt: string;
  actorAlias: string;
  publicRationale: string;
  reasonCategory?: string;
  source: PublicAiExplanation["source"];
  editorialVersionSha256: string;
  publicationProofSha256: string;
  publicEffect?: {
    kind: "DATA_UNAVAILABLE";
    publicId: string;
    message: string;
  };
  publicEffectSha256?: string;
};

export type EvidenceSource = {
  label: string;
  url: string;
  publisher: string;
  sha256: string;
};

export type InterestNodeData = Record<string, unknown> & {
  label: string;
  subtitle: string;
  kind: "person" | "public" | "company" | "contract" | "party" | "other";
  verified: boolean;
};

export type InterestGraphNode = {
  id: string;
  position?: { x: number; y: number };
  data: InterestNodeData;
};

export type InterestEdgeData = Record<string, unknown> & {
  label: string;
  period: string;
  reviewState: "Revisto" | "Pendente";
  source: EvidenceSource;
  year?: number;
  party?: string;
  amount?: number;
  company?: string;
};

export type InterestGraphEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
  data: InterestEdgeData;
};

export type InterestGraphDataset = {
  nodes: InterestGraphNode[];
  edges: InterestGraphEdge[];
};

export type SpeechVoteComparisonData = {
  id?: string;
  subject: string;
  statement: {
    quote: string;
    speaker: string;
    date: string;
    source: EvidenceSource;
  };
  vote: {
    choice: string;
    initiative: string;
    date: string;
    source: EvidenceSource;
  };
  comparison: {
    outcome: "CONSISTENT" | "INCONSISTENT" | "INCONCLUSIVE";
    score: number | null;
    comparablePairs: number;
    totalStatements: number;
    methodologyVersion: string;
    rationale: string;
  };
};

export type PublicInvestigatorDataset = InterestGraphDataset & {
  comparisons: SpeechVoteComparisonData[];
};

export type PublicPersonSummary = {
  id: string;
  slug: string;
  name: string;
  role: string;
  party: string;
  partyShort: string;
  constituency: string;
  legislature: string;
  portraitUrl?: string;
  observedAt: string;
  verifiedAt: string;
  profileSource: OfficialSource;
};

export type PublicPoliticianFacet = {
  value: string;
  label: string;
  count: number;
};

export type PublicPoliticianDirectory = {
  people: PublicPersonSummary[];
  total: number;
  totalIsExact: boolean;
  limit: number;
  nextCursor?: string;
  query?: string;
  partyShort?: string;
  parties: PublicPoliticianFacet[];
  paginationMode: "CURSOR" | "LEGACY_PAGE";
  compatibilityMode: "CURRENT" | "LEGACY_COMPLETE" | "LEGACY_LIMITED" | "UNAVAILABLE";
  currentPage: number;
  hasNext: boolean;
  hasPrevious: boolean;
  cursorRejected: boolean;
  searchRule: string;
};

export type PublicParliamentarySession = {
  id: string;
  sourceId: string;
  legislature: string;
  sessionNumber?: string;
  title: string;
  startsAt: string;
  endsAt?: string;
  verifiedAt: string;
  source: OfficialSource;
};

export type PublicParliamentaryInitiative = {
  id: string;
  sourceId: string;
  legislature: string;
  number: string;
  initiativeType: string;
  title: string;
  description?: string;
  introducedAt?: string;
  status?: string;
  officialUrl: string;
  verifiedAt: string;
  source: OfficialSource;
};

export type PublicParliamentaryVoteRecord = {
  actorLabel: string;
  actorType: "PERSON" | "PARTY" | "UNKNOWN";
  choice: "FAVOR" | "AGAINST" | "ABSTENTION" | "ABSENT" | "UNKNOWN";
  personSourceId?: string;
  partySourceId?: string;
};

export type PublicParliamentaryVote = {
  id: string;
  sourceId: string;
  legislature: string;
  title: string;
  initiativeNumber?: string;
  votedAt?: string;
  result?: string;
  isNominal: boolean;
  initiativeType?: string;
  initiativeTitle?: string;
  initiativeStatus?: string;
  initiativeOfficialUrl?: string;
  records: PublicParliamentaryVoteRecord[];
  verifiedAt: string;
  source: OfficialSource;
};

export type PublicParliamentPublicationHistoryItem = {
  eventReferenceSha256: string;
  action: "PUBLISHED" | "WITHDRAWN";
  scope: "activity" | "votes";
  scopeLabel: string;
  legislature: string;
  targetReferenceSha256: string;
  decidedAt: string;
  actorAlias: string;
  publicRationale: string;
  reasonCategory?: string;
  source: OfficialSource;
  snapshotSha256: string;
  manifestCounts: {
    sessions: number;
    initiatives: number;
    votes: number;
    voteRecords: number;
  };
  publicEffect?: {
    kind: "DATA_UNAVAILABLE" | "FALLBACK_TO_PREVIOUS_SNAPSHOT";
    scope: "activity" | "votes";
    legislature: string;
    message: string;
    snapshotReferenceSha256?: string;
    snapshotSha256?: string;
    sourceSha256?: string;
  };
  publicEffectSha256?: string;
};

export type PublicParliamentActivity = {
  sessions: PublicParliamentarySession[];
  initiatives: PublicParliamentaryInitiative[];
  votes: PublicParliamentaryVote[];
  publicationHistory: PublicParliamentPublicationHistoryItem[];
  availability: {
    sessions: boolean;
    initiatives: boolean;
    votes: boolean;
    publicationHistory: boolean;
  };
};

export type PublicParliamentFacetOption = {
  value: string;
  label: string;
  count: number;
};

export type PublicParliamentExplorer = {
  kind: "sessions" | "initiatives" | "votes";
  legislature: string;
  query?: string;
  dateFrom?: string;
  dateTo?: string;
  sessions: PublicParliamentarySession[];
  initiatives: PublicParliamentaryInitiative[];
  votes: PublicParliamentaryVote[];
  total: number;
  totalIsExact: boolean;
  limit: number;
  offset: number;
  facets: {
    legislatures: string[];
    initiativeTypes: PublicParliamentFacetOption[];
    initiativeStatuses: PublicParliamentFacetOption[];
    voteResults: PublicParliamentFacetOption[];
    parties: PublicParliamentFacetOption[];
    topicsAvailable: false;
    topicsNote: string;
  };
  explanationRule: string;
  publicationHistory: PublicParliamentPublicationHistoryItem[];
  availability: {
    explorer: boolean;
    publicationHistory: boolean;
    compatibilityMode:
      | "CURRENT"
      | "LIMITED_READ_ONLY"
      | "API_UPGRADE_REQUIRED"
      | "UNAVAILABLE";
  };
};

export type PublicParliamentCoverageRow = {
  legislature: string;
  scope: "activity" | "votes";
  recordKind: "sessions" | "initiatives" | "votes" | "vote_records";
  recordLabel: string;
  publishedCount: number;
  countIsExact: true;
  observedFrom?: string;
  observedThrough?: string;
  collectedAt: string;
  verifiedAt: string;
  source: OfficialSource;
  snapshotSha256: string;
  historicalCompleteness: "NOT_ASSERTED";
  limitation: string;
};

export type PublicParliamentCoverage = {
  available: boolean;
  rows: PublicParliamentCoverageRow[];
  message: string;
};
