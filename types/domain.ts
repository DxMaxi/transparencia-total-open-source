export type VoteChoice = "FAVOR" | "AGAINST" | "ABSTENTION" | "ABSENT";

export type PromiseStatus =
  | "UNVERIFIED"
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
  sha256?: string;
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

export type ProfileCoverageState = "AVAILABLE" | "PARTIAL" | "UNAVAILABLE";

export interface ProfileCoverageArea {
  state: ProfileCoverageState;
  recordCount: number;
  note: string;
  observedFrom?: string;
  observedThrough?: string;
  source?: OfficialSource;
}

export interface PoliticianProfileCoverage {
  identity: ProfileCoverageArea;
  membershipObservations: ProfileCoverageArea;
  mandates: ProfileCoverageArea;
  attendance: ProfileCoverageArea;
  initiatives: ProfileCoverageArea;
  nominalVotes: ProfileCoverageArea;
  declarations: ProfileCoverageArea;
  matchingRule: string;
}

export interface MembershipObservation {
  id: string;
  legislature: string;
  parliamentaryName: string;
  party: string;
  partyShort: string;
  constituency: string;
  observedAt: string;
  verifiedAt: string;
  source: OfficialSource;
}

export interface MandateRecord {
  id: string;
  officeTitle: string;
  legislature?: string;
  party?: string;
  partyShort?: string;
  constituency?: string;
  startedAt: string;
  endedAt?: string;
  verifiedAt: string;
  source: OfficialSource;
}

export interface AttendanceSummary {
  available: boolean;
  recordCount: number;
  presentCount: number;
  absentCount: number;
  excusedCount: number;
  attendanceRate?: number;
  observedFrom?: string;
  observedThrough?: string;
  note: string;
  source?: OfficialSource;
}

export interface PoliticianInitiativeRecord {
  id: string;
  number: string;
  initiativeType: string;
  title: string;
  status?: string;
  introducedAt?: string;
  relation: "AUTHOR" | "COAUTHOR" | "PROPOSER";
  source: OfficialSource;
}

export interface AssetDeclarationRecord {
  id: string;
  declarationType: string;
  declaredAt?: string;
  periodLabel?: string;
  publicAccessStatus: string;
  verifiedAt: string;
  source: OfficialSource;
}

export interface OfficialLookup {
  publisher: OfficialSource["publisher"];
  label: string;
  url: string;
  note: string;
}

export interface PoliticianProfileData {
  contractVersion: "v5.6" | "legacy";
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
  attendanceRate?: number;
  attendanceLabel: string;
  nominalVotesAvailable: boolean;
  nominalVoteCount: number;
  verifiedAt: string;
  profileSource: OfficialSource;
  membershipObservations: MembershipObservation[];
  mandates: MandateRecord[];
  attendance: AttendanceSummary;
  initiatives: PoliticianInitiativeRecord[];
  declarations: AssetDeclarationRecord[];
  declaration?: AssetDeclarationRecord;
  declarationLookupSource: OfficialLookup;
  coverage: PoliticianProfileCoverage;
  votes: VoteRecord[];
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
}
