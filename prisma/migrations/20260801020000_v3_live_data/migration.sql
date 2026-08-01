-- Transparência Total V3: persistência fiel de snapshots parlamentares.
-- `observed_at` nunca deve ser interpretado como início de mandato.

ALTER TABLE "vote_events"
ADD COLUMN "initiative_number" TEXT;

CREATE TABLE "parliamentary_membership_snapshots" (
    "id" TEXT NOT NULL,
    "person_id" TEXT NOT NULL,
    "party_id" TEXT,
    "legislature" TEXT NOT NULL,
    "constituency" TEXT,
    "observed_at" TIMESTAMP(3) NOT NULL,
    "source_document_id" TEXT NOT NULL,

    CONSTRAINT "parliamentary_membership_snapshots_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "parliamentary_membership_snapshots_person_id_legislature_source_document_id_key"
ON "parliamentary_membership_snapshots"("person_id", "legislature", "source_document_id");

CREATE INDEX "parliamentary_membership_snapshots_person_id_legislature_observed_at_idx"
ON "parliamentary_membership_snapshots"("person_id", "legislature", "observed_at");

CREATE INDEX "parliamentary_membership_snapshots_party_id_legislature_idx"
ON "parliamentary_membership_snapshots"("party_id", "legislature");

ALTER TABLE "parliamentary_membership_snapshots"
ADD CONSTRAINT "parliamentary_membership_snapshots_person_id_fkey"
FOREIGN KEY ("person_id") REFERENCES "people"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "parliamentary_membership_snapshots"
ADD CONSTRAINT "parliamentary_membership_snapshots_party_id_fkey"
FOREIGN KEY ("party_id") REFERENCES "parties"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "parliamentary_membership_snapshots"
ADD CONSTRAINT "parliamentary_membership_snapshots_source_document_id_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id") ON DELETE CASCADE ON UPDATE CASCADE;
