import type { OfficialSource } from "@/types/domain";

export type PublicDataMode = "LIVE" | "EMPTY" | "DEMO" | "UNAVAILABLE";

export type PublicRecordCounts = {
  politicians: number;
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
  isDemonstration: boolean;
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
  isDemonstration: boolean;
};

export type InterestGraphEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
  data: InterestEdgeData;
};

export type InterestGraphDataset = {
  isDemonstration: boolean;
  nodes: InterestGraphNode[];
  edges: InterestGraphEdge[];
};

export type SpeechVoteComparisonData = {
  id?: string;
  isDemonstration: boolean;
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
