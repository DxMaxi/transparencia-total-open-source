-- Transparência Total V4.1: arquivo privado de originais com atestação append-only.
-- A ausência de uma atestação significa "dados indisponíveis" e nunca autoriza
-- revisão ou publicação do documento derivado.

CREATE TABLE "source_archive_attestations" (
    "id" TEXT NOT NULL,
    "source_document_id" TEXT NOT NULL,
    "storage_backend" TEXT NOT NULL,
    "storage_key" TEXT NOT NULL,
    "content_sha256" TEXT NOT NULL,
    "byte_size" BIGINT NOT NULL,
    "mime_type" TEXT,
    "retrieval_url" TEXT NOT NULL,
    "retrieved_at" TIMESTAMP(3) NOT NULL,
    "archived_at" TIMESTAMP(3) NOT NULL,
    "archived_by" TEXT NOT NULL,
    "attestation_sha256" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "source_archive_attestations_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "source_archive_attestations_byte_size_check" CHECK ("byte_size" > 0),
    CONSTRAINT "source_archive_attestations_content_sha256_check"
        CHECK ("content_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "source_archive_attestations_attestation_sha256_check"
        CHECK ("attestation_sha256" ~ '^[0-9a-f]{64}$'),
    CONSTRAINT "source_archive_attestations_storage_key_check"
        CHECK ("storage_key" ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{64}$'),
    CONSTRAINT "source_archive_attestations_storage_key_hash_check"
        CHECK (
            "storage_key" = 'sha256/' || substring("content_sha256" FROM 1 FOR 2)
                || '/' || "content_sha256"
        ),
    CONSTRAINT "source_archive_attestations_storage_backend_check"
        CHECK ("storage_backend" ~ '^[A-Z][A-Z0-9_]{1,63}$'),
    CONSTRAINT "source_archive_attestations_mime_type_check"
        CHECK ("mime_type" IS NULL OR length("mime_type") <= 255),
    CONSTRAINT "source_archive_attestations_timeline_check"
        CHECK ("archived_at" >= "retrieved_at"),
    CONSTRAINT "source_archive_attestations_archived_by_check"
        CHECK (length(trim("archived_by")) BETWEEN 1 AND 200)
);

CREATE UNIQUE INDEX "source_archive_attestations_source_backend_key_key"
ON "source_archive_attestations"("source_document_id", "storage_backend", "storage_key");

CREATE INDEX "source_archive_attestations_source_archived_at_idx"
ON "source_archive_attestations"("source_document_id", "archived_at");

CREATE INDEX "source_archive_attestations_backend_key_idx"
ON "source_archive_attestations"("storage_backend", "storage_key");

CREATE INDEX "source_archive_attestations_content_sha256_idx"
ON "source_archive_attestations"("content_sha256");

ALTER TABLE "source_archive_attestations"
ADD CONSTRAINT "source_archive_attestations_source_document_id_fkey"
FOREIGN KEY ("source_document_id") REFERENCES "source_documents"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE FUNCTION "validate_source_archive_attestation_insert"()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM "source_documents" AS source
        WHERE source."id" = NEW."source_document_id"
          AND source."content_sha256" = NEW."content_sha256"
          AND source."url" = NEW."retrieval_url"
    ) THEN
        RAISE EXCEPTION
            'a atestação de arquivo tem de corresponder ao URL e SHA-256 do SourceDocument';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "source_archive_attestations_validate_insert"
BEFORE INSERT ON "source_archive_attestations"
FOR EACH ROW EXECUTE FUNCTION "validate_source_archive_attestation_insert"();

CREATE FUNCTION "protect_attested_source_document_anchor"()
RETURNS TRIGGER AS $$
BEGIN
    IF (
        OLD."url" IS DISTINCT FROM NEW."url"
        OR OLD."content_sha256" IS DISTINCT FROM NEW."content_sha256"
    ) AND EXISTS (
        SELECT 1
        FROM "source_archive_attestations" AS archive
        WHERE archive."source_document_id" = OLD."id"
    ) THEN
        RAISE EXCEPTION
            'o URL e o SHA-256 de um SourceDocument atestado são imutáveis';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "source_documents_protect_attested_anchor"
BEFORE UPDATE OF "url", "content_sha256" ON "source_documents"
FOR EACH ROW EXECUTE FUNCTION "protect_attested_source_document_anchor"();

CREATE FUNCTION "reject_source_archive_attestation_mutation"()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'source_archive_attestations é append-only; UPDATE e DELETE são proibidos';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "source_archive_attestations_append_only"
BEFORE UPDATE OR DELETE ON "source_archive_attestations"
FOR EACH ROW EXECUTE FUNCTION "reject_source_archive_attestation_mutation"();

