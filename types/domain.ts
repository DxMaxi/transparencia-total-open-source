export type VoteChoice = "FAVOR" | "AGAINST" | "ABSTENTION" | "ABSENT";

export type PromiseStatus =
  | "FULFILLED"
  | "IN_PROGRESS"
  | "BROKEN"
  | "ABANDONED";

export interface OfficialSource {
  label: string;
  url: string;
  publisher:
    | "AR"
    | "DRE"
    | "EPT"
    | "BASE"
    | "TCONTAS"
    | "PE"
    | "MP"
    | "TRIBUNAL"
    | "MEDIA"
    | "SNS"
    | "MUNICIPIO"
    | "OFICIAL";
  retrievedAt?: string;
}

export interface VoteRecord {
  id: string;
  title: string;
  date: string;
  choice: VoteChoice;
  result: string;
  initiativeNumber: string;
  source: OfficialSource;
  isNominal: boolean;
}

export interface PoliticianProfileData {
  id: string;
  slug: string;
  name: string;
  role: string;
  party: string;
  partyShort: string;
  constituency: string;
  legislature: string;
  portraitUrl?: string;
  attendanceRate?: number;
  attendanceLabel: string;
  verifiedAt: string;
  profileSource: OfficialSource;
  declarationSource: OfficialSource;
  votes: VoteRecord[];
  isDemonstration?: boolean;
}

export interface PromiseEvidence {
  id: string;
  legalReference: string;
  summary: string;
  source: OfficialSource;
  publishedAt: string;
}

export interface GovernmentPromise {
  id: string;
  title: string;
  area: string;
  status: PromiseStatus;
  progress: number;
  programmePage: string;
  programmeSource: OfficialSource;
  rationale: string;
  lastReviewedAt: string;
  evidence: PromiseEvidence[];
  isDemonstration?: boolean;
}
