-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "SourcePublisher" AS ENUM ('PARLIAMENT', 'DRE', 'TRANSPARENCY_ENTITY', 'SNS', 'MUNICIPALITY', 'OTHER_OFFICIAL');

-- CreateEnum
CREATE TYPE "DocumentKind" AS ENUM ('OPEN_DATASET', 'LAW', 'REGULATION', 'GOVERNMENT_PROGRAMME', 'PARLIAMENTARY_DIARY', 'ATTENDANCE', 'DECLARATION', 'PUBLIC_REPORT', 'MUNICIPAL_NOTICE', 'OTHER');

-- CreateEnum
CREATE TYPE "PersonRole" AS ENUM ('DEPUTY', 'MINISTER', 'SECRETARY_OF_STATE', 'MAYOR', 'OTHER_PUBLIC_OFFICE');

-- CreateEnum
CREATE TYPE "VoteChoice" AS ENUM ('FAVOR', 'AGAINST', 'ABSTENTION', 'ABSENT', 'PAIRED', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "VoteActorType" AS ENUM ('PERSON', 'PARTY', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "PromiseStatus" AS ENUM ('UNVERIFIED', 'FULFILLED', 'IN_PROGRESS', 'BROKEN', 'ABANDONED');

-- CreateEnum
CREATE TYPE "EvidenceKind" AS ENUM ('IMPLEMENTS', 'PARTIALLY_IMPLEMENTS', 'DELAYS', 'REPEALS', 'ABANDONS', 'CONTEXT');

-- CreateEnum
CREATE TYPE "ReviewDecision" AS ENUM ('ACCEPT', 'REJECT', 'NEEDS_MORE_EVIDENCE');

-- CreateEnum
CREATE TYPE "AiReviewStatus" AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'SUPERSEDED');

-- CreateEnum
CREATE TYPE "ComparisonOutcome" AS ENUM ('CONSISTENT', 'INCONSISTENT', 'INCONCLUSIVE', 'NOT_COMPARABLE');

-- CreateEnum
CREATE TYPE "LocalItemKind" AS ENUM ('SOCIAL_SUPPORT', 'HEALTH_SERVICE', 'PUBLIC_WORK', 'EMERGENCY', 'MUNICIPAL_DECISION', 'OTHER');

-- CreateEnum
CREATE TYPE "LocalItemStatus" AS ENUM ('ANNOUNCED', 'ACTIVE', 'INTERRUPTED', 'COMPLETED', 'CANCELLED', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "SyncStatus" AS ENUM ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED');

-- CreateTable
CREATE TABLE "parties" (
    "id" TEXT NOT NULL,
    "source_id" TEXT,
    "name" TEXT NOT NULL,
    "short_name" TEXT NOT NULL,
    "color" TEXT,
    "official_url" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "parties_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "people" (
    "id" TEXT NOT NULL,
    "source_id" TEXT,
    "full_name" TEXT NOT NULL,
    "parliamentary_name" TEXT,
    "slug" TEXT NOT NULL,
    "role" "PersonRole" NOT NULL,
    "photo_url" TEXT,
    "official_profile_url" TEXT,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "people_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mandates" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "party_id" TEXT,
    "legislature" TEXT,
    "office_title" TEXT NOT NULL,
    "constituency" TEXT,
    "started_at" TIMESTAMP(3) NOT NULL,
    "ended_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "mandates_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "parliamentary_sessions" (
    "id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "legislature" TEXT NOT NULL,
    "session_number" TEXT,
    "title" TEXT NOT NULL,
    "starts_at" TIMESTAMP(3) NOT NULL,
    "ends_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,

    CONSTRAINT "parliamentary_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "attendance_records" (
    "id" TEXT NOT NULL,
    "mandate_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "present" BOOLEAN,
    "absence_reason" TEXT,
    "is_excused" BOOLEAN,
    "source_document_id" TEXT NOT NULL,
    "recorded_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "attendance_records_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "parliamentary_initiatives" (
    "id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "legislature" TEXT NOT NULL,
    "number" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "introduced_at" TIMESTAMP(3),
    "status" TEXT,
    "official_url" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "parliamentary_initiatives_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "vote_events" (
    "id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "initiative_id" TEXT,
    "session_id" TEXT,
    "title" TEXT NOT NULL,
    "voted_at" TIMESTAMP(3),
    "result" TEXT,
    "is_nominal" BOOLEAN NOT NULL DEFAULT false,
    "source_document_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "vote_events_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "vote_records" (
    "id" TEXT NOT NULL,
    "vote_event_id" TEXT NOT NULL,
    "actor_type" "VoteActorType" NOT NULL,
    "actor_label" TEXT NOT NULL,
    "person_id" TEXT,
    "party_id" TEXT,
    "choice" "VoteChoice" NOT NULL,
    "source_document_id" TEXT NOT NULL,

    CONSTRAINT "vote_records_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "laws" (
    "id" TEXT NOT NULL,
    "official_identifier" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "eli_url" TEXT,
    "published_at" TIMESTAMP(3),
    "effective_at" TIMESTAMP(3),
    "initiative_id" TEXT,
    "source_document_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "laws_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "government_programmes" (
    "id" TEXT NOT NULL,
    "government_number" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "mandate_starts_at" TIMESTAMP(3),
    "mandate_ends_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "government_programmes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "promises" (
    "id" TEXT NOT NULL,
    "programme_id" TEXT NOT NULL,
    "stable_key" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "area" TEXT NOT NULL,
    "programme_page" TEXT,
    "status" "PromiseStatus" NOT NULL DEFAULT 'UNVERIFIED',
    "progress" INTEGER NOT NULL DEFAULT 0,
    "rationale" TEXT,
    "methodology_version" TEXT NOT NULL,
    "last_reviewed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "promises_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "promise_evidence" (
    "id" TEXT NOT NULL,
    "promise_id" TEXT NOT NULL,
    "law_id" TEXT,
    "source_document_id" TEXT NOT NULL,
    "kind" "EvidenceKind" NOT NULL,
    "explanation" TEXT NOT NULL,
    "effective_from" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "promise_evidence_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "promise_reviews" (
    "id" TEXT NOT NULL,
    "promise_id" TEXT NOT NULL,
    "previous_status" "PromiseStatus" NOT NULL,
    "proposed_status" "PromiseStatus" NOT NULL,
    "decision" "ReviewDecision" NOT NULL,
    "reviewer_alias" TEXT NOT NULL,
    "rationale" TEXT NOT NULL,
    "source_document_id" TEXT,
    "reviewed_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "promise_reviews_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "public_statements" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "statement_text" TEXT NOT NULL,
    "stated_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "source_offset" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "public_statements_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "statement_vote_comparisons" (
    "id" TEXT NOT NULL,
    "statement_id" TEXT NOT NULL,
    "vote_event_id" TEXT NOT NULL,
    "outcome" "ComparisonOutcome" NOT NULL,
    "rationale" TEXT NOT NULL,
    "methodology_version" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "reviewed_by" TEXT NOT NULL,
    "reviewed_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "statement_vote_comparisons_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "asset_declaration_metadata" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "declaration_type" TEXT NOT NULL,
    "declared_at" TIMESTAMP(3),
    "period_label" TEXT,
    "public_access_status" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "notes" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "asset_declaration_metadata_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ai_summaries" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "prompt_sha256" TEXT NOT NULL,
    "output_json" JSONB NOT NULL,
    "review_status" "AiReviewStatus" NOT NULL DEFAULT 'PENDING',
    "reviewed_by" TEXT,
    "reviewed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ai_summaries_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "districts" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,

    CONSTRAINT "districts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "municipalities" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "district_id" TEXT NOT NULL,

    CONSTRAINT "municipalities_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "local_transparency_items" (
    "id" TEXT NOT NULL,
    "municipality_id" TEXT NOT NULL,
    "kind" "LocalItemKind" NOT NULL,
    "status" "LocalItemStatus" NOT NULL DEFAULT 'UNKNOWN',
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "starts_at" TIMESTAMP(3),
    "ends_at" TIMESTAMP(3),
    "source_document_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "local_transparency_items_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "push_subscriptions" (
    "id" TEXT NOT NULL,
    "endpoint" TEXT NOT NULL,
    "p256dh" TEXT NOT NULL,
    "auth" TEXT NOT NULL,
    "districts" JSONB NOT NULL,
    "municipalities" JSONB NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "push_subscriptions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "source_documents" (
    "id" TEXT NOT NULL,
    "publisher" "SourcePublisher" NOT NULL,
    "kind" "DocumentKind" NOT NULL,
    "title" TEXT NOT NULL,
    "official_identifier" TEXT,
    "url" TEXT NOT NULL,
    "retrieved_at" TIMESTAMP(3) NOT NULL,
    "published_at" TIMESTAMP(3),
    "content_sha256" TEXT NOT NULL,
    "mime_type" TEXT,
    "raw_storage_key" TEXT,
    "parser_version" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "source_documents_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "sync_runs" (
    "id" TEXT NOT NULL,
    "source_name" TEXT NOT NULL,
    "dataset_url" TEXT,
    "status" "SyncStatus" NOT NULL DEFAULT 'RUNNING',
    "started_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMP(3),
    "records_read" INTEGER NOT NULL DEFAULT 0,
    "records_written" INTEGER NOT NULL DEFAULT 0,
    "warnings" JSONB,
    "error_message" TEXT,
    "code_version" TEXT NOT NULL,

    CONSTRAINT "sync_runs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_events" (
    "id" TEXT NOT NULL,
    "entity_type" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "actor_alias" TEXT NOT NULL,
    "before_json" JSONB,
    "after_json" JSONB,
    "reason" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_events_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "parties_source_id_key" ON "parties"("source_id");

-- CreateIndex
CREATE INDEX "parties_short_name_idx" ON "parties"("short_name");

-- CreateIndex
CREATE UNIQUE INDEX "people_source_id_key" ON "people"("source_id");

-- CreateIndex
CREATE UNIQUE INDEX "people_slug_key" ON "people"("slug");

-- CreateIndex
CREATE INDEX "people_full_name_idx" ON "people"("full_name");

-- CreateIndex
CREATE INDEX "people_role_active_idx" ON "people"("role", "active");

-- CreateIndex
CREATE INDEX "mandates_legislature_idx" ON "mandates"("legislature");

-- CreateIndex
CREATE INDEX "mandates_party_id_idx" ON "mandates"("party_id");

-- CreateIndex
CREATE UNIQUE INDEX "mandates_person_id_office_title_started_at_key" ON "mandates"("person_id", "office_title", "started_at");

-- CreateIndex
CREATE UNIQUE INDEX "parliamentary_sessions_source_id_key" ON "parliamentary_sessions"("source_id");

-- CreateIndex
CREATE INDEX "parliamentary_sessions_legislature_starts_at_idx" ON "parliamentary_sessions"("legislature", "starts_at");

-- CreateIndex
CREATE INDEX "attendance_records_session_id_present_idx" ON "attendance_records"("session_id", "present");

-- CreateIndex
CREATE UNIQUE INDEX "attendance_records_mandate_id_session_id_key" ON "attendance_records"("mandate_id", "session_id");

-- CreateIndex
CREATE UNIQUE INDEX "parliamentary_initiatives_source_id_key" ON "parliamentary_initiatives"("source_id");

-- CreateIndex
CREATE INDEX "parliamentary_initiatives_legislature_type_idx" ON "parliamentary_initiatives"("legislature", "type");

-- CreateIndex
CREATE INDEX "parliamentary_initiatives_introduced_at_idx" ON "parliamentary_initiatives"("introduced_at");

-- CreateIndex
CREATE UNIQUE INDEX "vote_events_source_id_key" ON "vote_events"("source_id");

-- CreateIndex
CREATE INDEX "vote_events_voted_at_idx" ON "vote_events"("voted_at");

-- CreateIndex
CREATE INDEX "vote_events_initiative_id_idx" ON "vote_events"("initiative_id");

-- CreateIndex
CREATE INDEX "vote_records_person_id_choice_idx" ON "vote_records"("person_id", "choice");

-- CreateIndex
CREATE INDEX "vote_records_party_id_choice_idx" ON "vote_records"("party_id", "choice");

-- CreateIndex
CREATE UNIQUE INDEX "vote_records_vote_event_id_actor_type_actor_label_key" ON "vote_records"("vote_event_id", "actor_type", "actor_label");

-- CreateIndex
CREATE INDEX "laws_published_at_idx" ON "laws"("published_at");

-- CreateIndex
CREATE UNIQUE INDEX "laws_official_identifier_published_at_key" ON "laws"("official_identifier", "published_at");

-- CreateIndex
CREATE UNIQUE INDEX "government_programmes_government_number_title_key" ON "government_programmes"("government_number", "title");

-- CreateIndex
CREATE UNIQUE INDEX "promises_stable_key_key" ON "promises"("stable_key");

-- CreateIndex
CREATE INDEX "promises_status_area_idx" ON "promises"("status", "area");

-- CreateIndex
CREATE INDEX "promises_programme_id_idx" ON "promises"("programme_id");

-- CreateIndex
CREATE UNIQUE INDEX "promise_evidence_promise_id_source_document_id_kind_key" ON "promise_evidence"("promise_id", "source_document_id", "kind");

-- CreateIndex
CREATE INDEX "promise_reviews_promise_id_reviewed_at_idx" ON "promise_reviews"("promise_id", "reviewed_at");

-- CreateIndex
CREATE INDEX "public_statements_person_id_stated_at_idx" ON "public_statements"("person_id", "stated_at");

-- CreateIndex
CREATE UNIQUE INDEX "statement_vote_comparisons_statement_id_vote_event_id_key" ON "statement_vote_comparisons"("statement_id", "vote_event_id");

-- CreateIndex
CREATE INDEX "asset_declaration_metadata_person_id_declared_at_idx" ON "asset_declaration_metadata"("person_id", "declared_at");

-- CreateIndex
CREATE INDEX "ai_summaries_review_status_idx" ON "ai_summaries"("review_status");

-- CreateIndex
CREATE UNIQUE INDEX "ai_summaries_source_document_id_provider_model_prompt_sha25_key" ON "ai_summaries"("source_document_id", "provider", "model", "prompt_sha256");

-- CreateIndex
CREATE UNIQUE INDEX "districts_code_key" ON "districts"("code");

-- CreateIndex
CREATE UNIQUE INDEX "municipalities_code_key" ON "municipalities"("code");

-- CreateIndex
CREATE INDEX "municipalities_district_id_idx" ON "municipalities"("district_id");

-- CreateIndex
CREATE INDEX "local_transparency_items_municipality_id_kind_status_idx" ON "local_transparency_items"("municipality_id", "kind", "status");

-- CreateIndex
CREATE INDEX "local_transparency_items_starts_at_idx" ON "local_transparency_items"("starts_at");

-- CreateIndex
CREATE UNIQUE INDEX "push_subscriptions_endpoint_key" ON "push_subscriptions"("endpoint");

-- CreateIndex
CREATE INDEX "push_subscriptions_is_active_idx" ON "push_subscriptions"("is_active");

-- CreateIndex
CREATE INDEX "source_documents_publisher_kind_published_at_idx" ON "source_documents"("publisher", "kind", "published_at");

-- CreateIndex
CREATE INDEX "source_documents_content_sha256_idx" ON "source_documents"("content_sha256");

-- CreateIndex
CREATE UNIQUE INDEX "source_documents_url_content_sha256_key" ON "source_documents"("url", "content_sha256");

-- CreateIndex
CREATE INDEX "sync_runs_source_name_started_at_idx" ON "sync_runs"("source_name", "started_at");

-- CreateIndex
CREATE INDEX "sync_runs_status_idx" ON "sync_runs"("status");

-- CreateIndex
CREATE INDEX "audit_events_entity_type_entity_id_created_at_idx" ON "audit_events"("entity_type", "entity_id", "created_at");

-- AddForeignKey
ALTER TABLE "mandates" ADD CONSTRAINT "mandates_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mandates" ADD CONSTRAINT "mandates_party_id_fkey" FOREIGN KEY ("party_id") REFERENCES "parties"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mandates" ADD CONSTRAINT "mandates_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "parliamentary_sessions" ADD CONSTRAINT "parliamentary_sessions_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendance_records" ADD CONSTRAINT "attendance_records_mandate_id_fkey" FOREIGN KEY ("mandate_id") REFERENCES "mandates"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendance_records" ADD CONSTRAINT "attendance_records_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "parliamentary_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendance_records" ADD CONSTRAINT "attendance_records_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "parliamentary_initiatives" ADD CONSTRAINT "parliamentary_initiatives_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vote_events" ADD CONSTRAINT "vote_events_initiative_id_fkey" FOREIGN KEY ("initiative_id") REFERENCES "parliamentary_initiatives"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vote_events" ADD CONSTRAINT "vote_events_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "parliamentary_sessions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vote_events" ADD CONSTRAINT "vote_events_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vote_records" ADD CONSTRAINT "vote_records_vote_event_id_fkey" FOREIGN KEY ("vote_event_id") REFERENCES "vote_events"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vote_records" ADD CONSTRAINT "vote_records_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vote_records" ADD CONSTRAINT "vote_records_party_id_fkey" FOREIGN KEY ("party_id") REFERENCES "parties"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vote_records" ADD CONSTRAINT "vote_records_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "laws" ADD CONSTRAINT "laws_initiative_id_fkey" FOREIGN KEY ("initiative_id") REFERENCES "parliamentary_initiatives"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "laws" ADD CONSTRAINT "laws_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "government_programmes" ADD CONSTRAINT "government_programmes_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "promises" ADD CONSTRAINT "promises_programme_id_fkey" FOREIGN KEY ("programme_id") REFERENCES "government_programmes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "promise_evidence" ADD CONSTRAINT "promise_evidence_promise_id_fkey" FOREIGN KEY ("promise_id") REFERENCES "promises"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "promise_evidence" ADD CONSTRAINT "promise_evidence_law_id_fkey" FOREIGN KEY ("law_id") REFERENCES "laws"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "promise_evidence" ADD CONSTRAINT "promise_evidence_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "promise_reviews" ADD CONSTRAINT "promise_reviews_promise_id_fkey" FOREIGN KEY ("promise_id") REFERENCES "promises"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "promise_reviews" ADD CONSTRAINT "promise_reviews_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public_statements" ADD CONSTRAINT "public_statements_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public_statements" ADD CONSTRAINT "public_statements_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "statement_vote_comparisons" ADD CONSTRAINT "statement_vote_comparisons_statement_id_fkey" FOREIGN KEY ("statement_id") REFERENCES "public_statements"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "statement_vote_comparisons" ADD CONSTRAINT "statement_vote_comparisons_vote_event_id_fkey" FOREIGN KEY ("vote_event_id") REFERENCES "vote_events"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "statement_vote_comparisons" ADD CONSTRAINT "statement_vote_comparisons_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "asset_declaration_metadata" ADD CONSTRAINT "asset_declaration_metadata_person_id_fkey" FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "asset_declaration_metadata" ADD CONSTRAINT "asset_declaration_metadata_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ai_summaries" ADD CONSTRAINT "ai_summaries_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "municipalities" ADD CONSTRAINT "municipalities_district_id_fkey" FOREIGN KEY ("district_id") REFERENCES "districts"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "local_transparency_items" ADD CONSTRAINT "local_transparency_items_municipality_id_fkey" FOREIGN KEY ("municipality_id") REFERENCES "municipalities"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "local_transparency_items" ADD CONSTRAINT "local_transparency_items_source_document_id_fkey" FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
