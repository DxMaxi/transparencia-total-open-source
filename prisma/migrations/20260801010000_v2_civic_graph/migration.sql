-- CreateEnum
CREATE TYPE "VerificationStatus" AS ENUM ('INGESTED', 'PENDING_REVIEW', 'VERIFIED', 'REJECTED', 'SUPERSEDED');

-- CreateEnum
CREATE TYPE "PublicationStatus" AS ENUM ('DRAFT', 'UNDER_REVIEW', 'PUBLISHED', 'WITHDRAWN');

-- CreateEnum
CREATE TYPE "InterestEntityKind" AS ENUM ('PERSON', 'PARTY', 'PUBLIC_BODY', 'COMPANY', 'NON_PROFIT', 'EUROPEAN_BODY', 'OTHER');

-- CreateEnum
CREATE TYPE "InterestRelationshipType" AS ENUM ('PUBLIC_OFFICE', 'BOARD_MEMBERSHIP', 'OWNERSHIP', 'PARTY_MEMBERSHIP', 'CAMPAIGN_DONATION', 'FAMILY_RELATION', 'OFFICIAL_MEETING', 'PUBLIC_CONTRACT', 'OTHER_OFFICIAL');

-- CreateEnum
CREATE TYPE "PublicContractProcedure" AS ENUM ('DIRECT_AWARD', 'PRIOR_CONSULTATION', 'PUBLIC_TENDER', 'LIMITED_TENDER', 'NEGOTIATED_PROCEDURE', 'FRAMEWORK_AGREEMENT', 'OTHER', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "ContractPartyRole" AS ENUM ('CONTRACTING_AUTHORITY', 'CONTRACTOR', 'CO_CONTRACTOR');

-- CreateEnum
CREATE TYPE "MatchMethod" AS ENUM ('EXACT_PUBLIC_ORGANISATION_ID', 'EXACT_PROTECTED_IDENTIFIER', 'NORMALISED_NAME', 'MANUAL_OFFICIAL_EVIDENCE');

-- CreateEnum
CREATE TYPE "MatchDecision" AS ENUM ('PENDING_REVIEW', 'CONFIRMED', 'REJECTED');

-- CreateEnum
CREATE TYPE "JudicialCaseStatus" AS ENUM ('REPORTED_INVESTIGATION', 'FORMALLY_ACCUSED', 'TRIAL', 'CONVICTED', 'ACQUITTED', 'ARCHIVED', 'APPEAL', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "JudicialSubjectRole" AS ENUM ('INVESTIGATED', 'ACCUSED', 'DEFENDANT', 'CONVICTED', 'ACQUITTED', 'OTHER');

-- CreateEnum
CREATE TYPE "NewsReviewStatus" AS ENUM ('INGESTED', 'PENDING_EVIDENCE', 'VERIFIED_WITH_OFFICIAL_EVIDENCE', 'REJECTED');

-- CreateEnum
CREATE TYPE "CitizenAlertCategory" AS ENUM ('TAX', 'LABOUR', 'SOCIAL_SUPPORT', 'HEALTH', 'HOUSING', 'EDUCATION', 'LOCAL_SERVICE', 'OTHER');

-- CreateEnum
CREATE TYPE "ImpactDirection" AS ENUM ('INCREASE', 'DECREASE', 'MIXED', 'NO_CHANGE', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "RightOfReplyStatus" AS ENUM ('RECEIVED', 'IDENTITY_PENDING', 'EVIDENCE_REVIEW', 'PUBLISHED', 'REJECTED', 'SUPERSEDED');

-- CreateEnum
CREATE TYPE "LegalBasis" AS ENUM ('PUBLIC_INTEREST', 'LEGAL_OBLIGATION', 'LEGITIMATE_INTEREST', 'CONSENT', 'NOT_APPLICABLE');

-- CreateEnum
CREATE TYPE "DataSensitivity" AS ENUM ('PUBLIC_OFFICIAL', 'PUBLIC_PERSONAL', 'RESTRICTED_IDENTIFIER', 'SPECIAL_CATEGORY', 'CRIMINAL_DATA');

-- AlterEnum
-- This migration adds more than one value to an enum.
-- With PostgreSQL versions 11 and earlier, this is not possible
-- in a single migration. This can be worked around by creating
-- multiple migrations, each migration adding only one value to
-- the enum.


ALTER TYPE "SourcePublisher" ADD VALUE 'BASE_GOV';
ALTER TYPE "SourcePublisher" ADD VALUE 'COURT_OF_AUDIT';
ALTER TYPE "SourcePublisher" ADD VALUE 'EUROPEAN_PARLIAMENT';
ALTER TYPE "SourcePublisher" ADD VALUE 'PUBLIC_PROSECUTOR';
ALTER TYPE "SourcePublisher" ADD VALUE 'COURT';
ALTER TYPE "SourcePublisher" ADD VALUE 'MEDIA';

-- AlterEnum
-- This migration adds more than one value to an enum.
-- With PostgreSQL versions 11 and earlier, this is not possible
-- in a single migration. This can be worked around by creating
-- multiple migrations, each migration adding only one value to
-- the enum.


ALTER TYPE "DocumentKind" ADD VALUE 'PUBLIC_CONTRACT';
ALTER TYPE "DocumentKind" ADD VALUE 'AUDIT_REPORT';
ALTER TYPE "DocumentKind" ADD VALUE 'JUDICIAL_ACT';
ALTER TYPE "DocumentKind" ADD VALUE 'NEWS_ARTICLE';
ALTER TYPE "DocumentKind" ADD VALUE 'EUROPEAN_VOTE';
ALTER TYPE "DocumentKind" ADD VALUE 'RIGHT_OF_REPLY';

-- AlterTable
ALTER TABLE "statement_vote_comparisons" ADD COLUMN     "comparable" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "confidence" DECIMAL(5,4),
ADD COLUMN     "publication_status" "PublicationStatus" NOT NULL DEFAULT 'DRAFT',
ADD COLUMN     "topic_key" TEXT NOT NULL DEFAULT 'unclassified',
ADD COLUMN     "verification_status" "VerificationStatus" NOT NULL DEFAULT 'PENDING_REVIEW';

-- CreateTable
CREATE TABLE "interest_entities" (
    "id" TEXT NOT NULL,
    "kind" "InterestEntityKind" NOT NULL,
    "public_label" TEXT NOT NULL,
    "person_id" TEXT,
    "party_id" TEXT,
    "organisation_id" TEXT,
    "verification_status" "VerificationStatus" NOT NULL DEFAULT 'PENDING_REVIEW',
    "publication_status" "PublicationStatus" NOT NULL DEFAULT 'DRAFT',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "interest_entities_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "organisations" (
    "id" TEXT NOT NULL,
    "source_id" TEXT,
    "legal_name" TEXT NOT NULL,
    "normalised_name" TEXT NOT NULL,
    "kind" "InterestEntityKind" NOT NULL,
    "public_nipc" TEXT,
    "official_url" TEXT,
    "source_document_id" TEXT NOT NULL,
    "verification_status" "VerificationStatus" NOT NULL DEFAULT 'PENDING_REVIEW',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "organisations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "protected_identifier_digests" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "identifier_type" TEXT NOT NULL,
    "digest" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "legal_basis" "LegalBasis" NOT NULL,
    "retention_until" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "protected_identifier_digests_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "public_contracts" (
    "id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "object" TEXT NOT NULL,
    "procedure" "PublicContractProcedure" NOT NULL DEFAULT 'UNKNOWN',
    "cpv_code" TEXT,
    "base_value" DECIMAL(20,2),
    "contract_value" DECIMAL(20,2),
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "decision_at" TIMESTAMP(3),
    "signed_at" TIMESTAMP(3),
    "published_at" TIMESTAMP(3),
    "execution_days" INTEGER,
    "source_document_id" TEXT NOT NULL,
    "verification_status" "VerificationStatus" NOT NULL DEFAULT 'INGESTED',
    "publication_status" "PublicationStatus" NOT NULL DEFAULT 'UNDER_REVIEW',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "public_contracts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "public_contract_parties" (
    "id" TEXT NOT NULL,
    "public_contract_id" TEXT NOT NULL,
    "interest_entity_id" TEXT NOT NULL,
    "role" "ContractPartyRole" NOT NULL,
    "source_name" TEXT NOT NULL,
    "source_public_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "public_contract_parties_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "contract_match_reviews" (
    "id" TEXT NOT NULL,
    "public_contract_id" TEXT NOT NULL,
    "interest_entity_id" TEXT NOT NULL,
    "method" "MatchMethod" NOT NULL,
    "candidate_label" TEXT NOT NULL,
    "identifier_digest" TEXT,
    "score" DECIMAL(5,4),
    "decision" "MatchDecision" NOT NULL DEFAULT 'PENDING_REVIEW',
    "rationale" TEXT NOT NULL,
    "evidence_document_id" TEXT NOT NULL,
    "reviewed_by" TEXT,
    "reviewed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "contract_match_reviews_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "interest_relationships" (
    "id" TEXT NOT NULL,
    "from_entity_id" TEXT NOT NULL,
    "to_entity_id" TEXT NOT NULL,
    "type" "InterestRelationshipType" NOT NULL,
    "public_contract_id" TEXT,
    "public_description" TEXT NOT NULL,
    "valid_from" TIMESTAMP(3),
    "valid_until" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "verification_status" "VerificationStatus" NOT NULL DEFAULT 'PENDING_REVIEW',
    "publication_status" "PublicationStatus" NOT NULL DEFAULT 'DRAFT',
    "public_interest_test" TEXT NOT NULL,
    "methodology_version" TEXT NOT NULL,
    "reviewed_by" TEXT,
    "reviewed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "interest_relationships_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "judicial_cases" (
    "id" TEXT NOT NULL,
    "official_identifier" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "status" "JudicialCaseStatus" NOT NULL,
    "authority_name" TEXT NOT NULL,
    "factual_summary" TEXT NOT NULL,
    "opened_at" TIMESTAMP(3),
    "decided_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "verification_status" "VerificationStatus" NOT NULL DEFAULT 'PENDING_REVIEW',
    "publication_status" "PublicationStatus" NOT NULL DEFAULT 'DRAFT',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "judicial_cases_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "judicial_case_subjects" (
    "id" TEXT NOT NULL,
    "judicial_case_id" TEXT NOT NULL,
    "interest_entity_id" TEXT NOT NULL,
    "person_id" TEXT,
    "role" "JudicialSubjectRole" NOT NULL,
    "role_source_text" TEXT NOT NULL,

    CONSTRAINT "judicial_case_subjects_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "news_articles" (
    "id" TEXT NOT NULL,
    "external_id" TEXT NOT NULL,
    "outlet_name" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "excerpt" TEXT,
    "published_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "review_status" "NewsReviewStatus" NOT NULL DEFAULT 'INGESTED',
    "publication_status" "PublicationStatus" NOT NULL DEFAULT 'UNDER_REVIEW',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "news_articles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "news_evidence" (
    "id" TEXT NOT NULL,
    "news_article_id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "supported_claim" TEXT NOT NULL,
    "verified_by" TEXT,
    "verified_at" TIMESTAMP(3),

    CONSTRAINT "news_evidence_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "news_entity_mentions" (
    "id" TEXT NOT NULL,
    "news_article_id" TEXT NOT NULL,
    "interest_entity_id" TEXT NOT NULL,
    "person_id" TEXT,
    "party_id" TEXT,
    "matched_text" TEXT NOT NULL,
    "verified" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "news_entity_mentions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "coherence_snapshots" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "period_starts_at" TIMESTAMP(3) NOT NULL,
    "period_ends_at" TIMESTAMP(3) NOT NULL,
    "comparable_count" INTEGER NOT NULL,
    "consistent_count" INTEGER NOT NULL,
    "inconsistent_count" INTEGER NOT NULL,
    "score" DECIMAL(5,2),
    "coverage_note" TEXT NOT NULL,
    "methodology_version" TEXT NOT NULL,
    "aggregate_sha256" TEXT NOT NULL,
    "computed_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "coherence_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "citizen_impact_rules" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "law_id" TEXT NOT NULL,
    "category" "CitizenAlertCategory" NOT NULL,
    "title" TEXT NOT NULL,
    "eligibility_json" JSONB NOT NULL,
    "calculation_json" JSONB NOT NULL,
    "explanation_template" TEXT NOT NULL,
    "direction" "ImpactDirection" NOT NULL DEFAULT 'UNKNOWN',
    "effective_from" TIMESTAMP(3) NOT NULL,
    "effective_until" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "methodology_version" TEXT NOT NULL,
    "verification_status" "VerificationStatus" NOT NULL DEFAULT 'PENDING_REVIEW',
    "publication_status" "PublicationStatus" NOT NULL DEFAULT 'DRAFT',
    "reviewed_by" TEXT,
    "reviewed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "citizen_impact_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "citizen_alerts" (
    "id" TEXT NOT NULL,
    "category" "CitizenAlertCategory" NOT NULL,
    "title" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "law_id" TEXT,
    "impact_rule_id" TEXT,
    "municipality_id" TEXT,
    "source_document_id" TEXT NOT NULL,
    "effective_at" TIMESTAMP(3),
    "expires_at" TIMESTAMP(3),
    "publication_status" "PublicationStatus" NOT NULL DEFAULT 'UNDER_REVIEW',
    "requires_human_review" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "citizen_alerts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "rights_of_reply" (
    "id" TEXT NOT NULL,
    "public_reference" TEXT NOT NULL,
    "target_type" TEXT NOT NULL,
    "target_id" TEXT NOT NULL,
    "original_record_sha256" TEXT NOT NULL,
    "claimant_public_name" TEXT NOT NULL,
    "claimant_role" TEXT NOT NULL,
    "statement_text" TEXT NOT NULL,
    "statement_sha256" TEXT NOT NULL,
    "official_response_url" TEXT,
    "source_document_id" TEXT,
    "status" "RightOfReplyStatus" NOT NULL DEFAULT 'RECEIVED',
    "submitted_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "published_at" TIMESTAMP(3),
    "supersedes_id" TEXT,
    "audit_sha256" TEXT NOT NULL,

    CONSTRAINT "rights_of_reply_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "data_publication_reviews" (
    "id" TEXT NOT NULL,
    "entity_type" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "purpose" TEXT NOT NULL,
    "legal_basis" "LegalBasis" NOT NULL,
    "sensitivity" "DataSensitivity" NOT NULL,
    "necessity_assessment" TEXT NOT NULL,
    "proportionality_test" TEXT NOT NULL,
    "retention_until" TIMESTAMP(3),
    "publishable" BOOLEAN NOT NULL DEFAULT false,
    "source_document_id" TEXT,
    "reviewed_by" TEXT NOT NULL,
    "reviewed_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "data_publication_reviews_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "interest_entities_person_id_key" ON "interest_entities"("person_id");

-- CreateIndex
CREATE UNIQUE INDEX "interest_entities_party_id_key" ON "interest_entities"("party_id");

-- CreateIndex
CREATE UNIQUE INDEX "interest_entities_organisation_id_key" ON "interest_entities"("organisation_id");

-- CreateIndex
CREATE INDEX "interest_entities_kind_publication_status_idx" ON "interest_entities"("kind", "publication_status");

-- CreateIndex
CREATE UNIQUE INDEX "organisations_source_id_key" ON "organisations"("source_id");

-- CreateIndex
CREATE INDEX "organisations_normalised_name_idx" ON "organisations"("normalised_name");

-- CreateIndex
CREATE INDEX "organisations_public_nipc_idx" ON "organisations"("public_nipc");

-- CreateIndex
CREATE INDEX "protected_identifier_digests_person_id_idx" ON "protected_identifier_digests"("person_id");

-- CreateIndex
CREATE UNIQUE INDEX "protected_identifier_digests_identifier_type_digest_key" ON "protected_identifier_digests"("identifier_type", "digest");

-- CreateIndex
CREATE UNIQUE INDEX "public_contracts_source_id_key" ON "public_contracts"("source_id");

-- CreateIndex
CREATE INDEX "public_contracts_procedure_published_at_idx" ON "public_contracts"("procedure", "published_at");

-- CreateIndex
CREATE INDEX "public_contracts_contract_value_idx" ON "public_contracts"("contract_value");

-- CreateIndex
CREATE INDEX "public_contracts_publication_status_verification_status_idx" ON "public_contracts"("publication_status", "verification_status");

-- CreateIndex
CREATE INDEX "public_contract_parties_interest_entity_id_role_idx" ON "public_contract_parties"("interest_entity_id", "role");

-- CreateIndex
CREATE UNIQUE INDEX "public_contract_parties_public_contract_id_interest_entity__key" ON "public_contract_parties"("public_contract_id", "interest_entity_id", "role");

-- CreateIndex
CREATE INDEX "contract_match_reviews_decision_created_at_idx" ON "contract_match_reviews"("decision", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "contract_match_reviews_public_contract_id_interest_entity_i_key" ON "contract_match_reviews"("public_contract_id", "interest_entity_id", "method");

-- CreateIndex
CREATE INDEX "interest_relationships_type_publication_status_verification_idx" ON "interest_relationships"("type", "publication_status", "verification_status");

-- CreateIndex
CREATE INDEX "interest_relationships_from_entity_id_idx" ON "interest_relationships"("from_entity_id");

-- CreateIndex
CREATE INDEX "interest_relationships_to_entity_id_idx" ON "interest_relationships"("to_entity_id");

-- CreateIndex
CREATE UNIQUE INDEX "interest_relationships_from_entity_id_to_entity_id_type_sou_key" ON "interest_relationships"("from_entity_id", "to_entity_id", "type", "source_document_id");

-- CreateIndex
CREATE INDEX "judicial_cases_status_publication_status_idx" ON "judicial_cases"("status", "publication_status");

-- CreateIndex
CREATE UNIQUE INDEX "judicial_cases_authority_name_official_identifier_key" ON "judicial_cases"("authority_name", "official_identifier");

-- CreateIndex
CREATE UNIQUE INDEX "judicial_case_subjects_judicial_case_id_interest_entity_id__key" ON "judicial_case_subjects"("judicial_case_id", "interest_entity_id", "role");

-- CreateIndex
CREATE UNIQUE INDEX "news_articles_external_id_key" ON "news_articles"("external_id");

-- CreateIndex
CREATE INDEX "news_articles_published_at_idx" ON "news_articles"("published_at");

-- CreateIndex
CREATE INDEX "news_articles_review_status_publication_status_idx" ON "news_articles"("review_status", "publication_status");

-- CreateIndex
CREATE UNIQUE INDEX "news_evidence_news_article_id_source_document_id_supported__key" ON "news_evidence"("news_article_id", "source_document_id", "supported_claim");

-- CreateIndex
CREATE INDEX "news_entity_mentions_person_id_idx" ON "news_entity_mentions"("person_id");

-- CreateIndex
CREATE INDEX "news_entity_mentions_party_id_idx" ON "news_entity_mentions"("party_id");

-- CreateIndex
CREATE UNIQUE INDEX "news_entity_mentions_news_article_id_interest_entity_id_key" ON "news_entity_mentions"("news_article_id", "interest_entity_id");

-- CreateIndex
CREATE UNIQUE INDEX "coherence_snapshots_person_id_period_starts_at_period_ends__key" ON "coherence_snapshots"("person_id", "period_starts_at", "period_ends_at", "methodology_version");

-- CreateIndex
CREATE UNIQUE INDEX "citizen_impact_rules_code_key" ON "citizen_impact_rules"("code");

-- CreateIndex
CREATE INDEX "citizen_impact_rules_category_effective_from_idx" ON "citizen_impact_rules"("category", "effective_from");

-- CreateIndex
CREATE INDEX "citizen_alerts_category_publication_status_effective_at_idx" ON "citizen_alerts"("category", "publication_status", "effective_at");

-- CreateIndex
CREATE INDEX "citizen_alerts_municipality_id_idx" ON "citizen_alerts"("municipality_id");

-- CreateIndex
CREATE UNIQUE INDEX "rights_of_reply_public_reference_key" ON "rights_of_reply"("public_reference");

-- CreateIndex
CREATE UNIQUE INDEX "rights_of_reply_audit_sha256_key" ON "rights_of_reply"("audit_sha256");

-- CreateIndex
CREATE INDEX "rights_of_reply_target_type_target_id_submitted_at_idx" ON "rights_of_reply"("target_type", "target_id", "submitted_at");

-- CreateIndex
CREATE INDEX "rights_of_reply_status_idx" ON "rights_of_reply"("status");

-- CreateIndex
CREATE INDEX "data_publication_reviews_entity_type_entity_id_reviewed_at_idx" ON "data_publication_reviews"("entity_type", "entity_id", "reviewed_at");

-- CreateIndex
CREATE INDEX "data_publication_reviews_publishable_sensitivity_idx" ON "data_publication_reviews"("publishable", "sensitivity");

-- CreateIndex
CREATE INDEX "statement_vote_comparisons_topic_key_comparable_publication_idx" ON "statement_vote_comparisons"("topic_key", "comparable", "publication_status");

-- AddForeignKey
ALTER TABLE "interest_entities" ADD CONSTRAINT "interest_entities_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "interest_entities" ADD CONSTRAINT "interest_entities_party_id_fkey" FOREIGN KEY ("party_id") REFERENCES "parties"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "interest_entities" ADD CONSTRAINT "interest_entities_organisation_id_fkey" FOREIGN KEY ("organisation_id") REFERENCES "organisations"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "organisations" ADD CONSTRAINT "organisations_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "protected_identifier_digests" ADD CONSTRAINT "protected_identifier_digests_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "protected_identifier_digests" ADD CONSTRAINT "protected_identifier_digests_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public_contracts" ADD CONSTRAINT "public_contracts_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public_contract_parties" ADD CONSTRAINT "public_contract_parties_public_contract_id_fkey" FOREIGN KEY ("public_contract_id") REFERENCES "public_contracts"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public_contract_parties" ADD CONSTRAINT "public_contract_parties_interest_entity_id_fkey" FOREIGN KEY ("interest_entity_id") REFERENCES "interest_entities"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "contract_match_reviews" ADD CONSTRAINT "contract_match_reviews_public_contract_id_fkey" FOREIGN KEY ("public_contract_id") REFERENCES "public_contracts"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "contract_match_reviews" ADD CONSTRAINT "contract_match_reviews_interest_entity_id_fkey" FOREIGN KEY ("interest_entity_id") REFERENCES "interest_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "contract_match_reviews" ADD CONSTRAINT "contract_match_reviews_evidence_document_id_fkey" FOREIGN KEY ("evidence_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "interest_relationships" ADD CONSTRAINT "interest_relationships_from_entity_id_fkey" FOREIGN KEY ("from_entity_id") REFERENCES "interest_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "interest_relationships" ADD CONSTRAINT "interest_relationships_to_entity_id_fkey" FOREIGN KEY ("to_entity_id") REFERENCES "interest_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "interest_relationships" ADD CONSTRAINT "interest_relationships_public_contract_id_fkey" FOREIGN KEY ("public_contract_id") REFERENCES "public_contracts"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "interest_relationships" ADD CONSTRAINT "interest_relationships_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "judicial_cases" ADD CONSTRAINT "judicial_cases_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "judicial_case_subjects" ADD CONSTRAINT "judicial_case_subjects_judicial_case_id_fkey" FOREIGN KEY ("judicial_case_id") REFERENCES "judicial_cases"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "judicial_case_subjects" ADD CONSTRAINT "judicial_case_subjects_interest_entity_id_fkey" FOREIGN KEY ("interest_entity_id") REFERENCES "interest_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "judicial_case_subjects" ADD CONSTRAINT "judicial_case_subjects_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_articles" ADD CONSTRAINT "news_articles_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_evidence" ADD CONSTRAINT "news_evidence_news_article_id_fkey" FOREIGN KEY ("news_article_id") REFERENCES "news_articles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_evidence" ADD CONSTRAINT "news_evidence_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_entity_mentions" ADD CONSTRAINT "news_entity_mentions_news_article_id_fkey" FOREIGN KEY ("news_article_id") REFERENCES "news_articles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_entity_mentions" ADD CONSTRAINT "news_entity_mentions_interest_entity_id_fkey" FOREIGN KEY ("interest_entity_id") REFERENCES "interest_entities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_entity_mentions" ADD CONSTRAINT "news_entity_mentions_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_entity_mentions" ADD CONSTRAINT "news_entity_mentions_party_id_fkey" FOREIGN KEY ("party_id") REFERENCES "parties"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "coherence_snapshots" ADD CONSTRAINT "coherence_snapshots_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "citizen_impact_rules" ADD CONSTRAINT "citizen_impact_rules_law_id_fkey" FOREIGN KEY ("law_id") REFERENCES "laws"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "citizen_impact_rules" ADD CONSTRAINT "citizen_impact_rules_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "citizen_alerts" ADD CONSTRAINT "citizen_alerts_law_id_fkey" FOREIGN KEY ("law_id") REFERENCES "laws"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "citizen_alerts" ADD CONSTRAINT "citizen_alerts_impact_rule_id_fkey" FOREIGN KEY ("impact_rule_id") REFERENCES "citizen_impact_rules"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "citizen_alerts" ADD CONSTRAINT "citizen_alerts_municipality_id_fkey" FOREIGN KEY ("municipality_id") REFERENCES "municipalities"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "citizen_alerts" ADD CONSTRAINT "citizen_alerts_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "rights_of_reply" ADD CONSTRAINT "rights_of_reply_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "rights_of_reply" ADD CONSTRAINT "rights_of_reply_supersedes_id_fkey" FOREIGN KEY ("supersedes_id") REFERENCES "rights_of_reply"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "data_publication_reviews" ADD CONSTRAINT "data_publication_reviews_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- Invariantes que o Prisma não consegue expressar diretamente.
ALTER TABLE "interest_entities" ADD CONSTRAINT "interest_entities_exactly_one_subject_check"
CHECK (num_nonnulls("person_id", "party_id", "organisation_id") = 1);

ALTER TABLE "interest_relationships" ADD CONSTRAINT "interest_relationships_distinct_nodes_check"
CHECK ("from_entity_id" <> "to_entity_id");

ALTER TABLE "public_contracts" ADD CONSTRAINT "public_contracts_non_negative_values_check"
CHECK (("base_value" IS NULL OR "base_value" >= 0) AND ("contract_value" IS NULL OR "contract_value" >= 0));

ALTER TABLE "coherence_snapshots" ADD CONSTRAINT "coherence_snapshot_counts_check"
CHECK (
  "comparable_count" >= 0
  AND "consistent_count" >= 0
  AND "inconsistent_count" >= 0
  AND "consistent_count" + "inconsistent_count" <= "comparable_count"
  AND ("score" IS NULL OR ("score" >= 0 AND "score" <= 100))
);

ALTER TABLE "rights_of_reply" ADD CONSTRAINT "rights_of_reply_hashes_check"
CHECK (
  length("original_record_sha256") = 64
  AND length("statement_sha256") = 64
  AND length("audit_sha256") = 64
);
