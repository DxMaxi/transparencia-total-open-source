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
  verifiedAt: string;
  profileSource: OfficialSource;
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
  records: PublicParliamentaryVoteRecord[];
  verifiedAt: string;
  source: OfficialSource;
};

export type PublicParliamentActivity = {
  sessions: PublicParliamentarySession[];
  initiatives: PublicParliamentaryInitiative[];
  votes: PublicParliamentaryVote[];
  availability: {
    sessions: boolean;
    initiatives: boolean;
    votes: boolean;
  };
};
