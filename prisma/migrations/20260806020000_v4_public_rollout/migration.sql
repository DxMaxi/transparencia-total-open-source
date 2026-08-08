-- V4 public rollout: preserve exact official index bytes in PostgreSQL.
-- The tables are private infrastructure. Public APIs expose metadata only.

CREATE TABLE IF NOT EXISTS raw_source_objects (
    storage_key TEXT PRIMARY KEY,
    content_sha256 CHAR(64) NOT NULL UNIQUE,
    byte_size INTEGER NOT NULL,
    mime_type TEXT,
    content BYTEA NOT NULL,
    created_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT raw_source_objects_sha256_format
        CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT raw_source_objects_storage_key_matches_hash
        CHECK (storage_key = 'sha256/' || substring(content_sha256 FROM 1 FOR 2) || '/' || content_sha256),
    CONSTRAINT raw_source_objects_byte_size_matches
        CHECK (byte_size > 0 AND octet_length(content) = byte_size)
);

CREATE TABLE IF NOT EXISTS official_index_snapshots (
    id TEXT PRIMARY KEY,
    source_document_id TEXT NOT NULL UNIQUE,
    sync_run_id TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    publisher "SourcePublisher" NOT NULL,
    collected_at TIMESTAMP(3) NOT NULL,
    resource_count INTEGER NOT NULL,
    publishable BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT official_index_snapshots_source_document_fk
        FOREIGN KEY (source_document_id) REFERENCES source_documents(id) ON DELETE RESTRICT,
    CONSTRAINT official_index_snapshots_sync_run_fk
        FOREIGN KEY (sync_run_id) REFERENCES sync_runs(id) ON DELETE RESTRICT,
    CONSTRAINT official_index_snapshots_resource_count_nonnegative
        CHECK (resource_count >= 0),
    CONSTRAINT official_index_snapshots_never_auto_publish
        CHECK (publishable = FALSE)
);

CREATE TABLE IF NOT EXISTS official_index_resources (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    url TEXT NOT NULL,
    created_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT official_index_resources_snapshot_fk
        FOREIGN KEY (snapshot_id) REFERENCES official_index_snapshots(id) ON DELETE RESTRICT,
    CONSTRAINT official_index_resources_ordinal_nonnegative
        CHECK (ordinal >= 0),
    CONSTRAINT official_index_resources_title_nonempty
        CHECK (length(btrim(title)) > 0),
    CONSTRAINT official_index_resources_url_https
        CHECK (url LIKE 'https://%'),
    CONSTRAINT official_index_resources_snapshot_ordinal_unique
        UNIQUE (snapshot_id, ordinal),
    CONSTRAINT official_index_resources_snapshot_url_unique
        UNIQUE (snapshot_id, url)
);

CREATE INDEX IF NOT EXISTS official_index_snapshots_source_name_collected_at_idx
    ON official_index_snapshots(source_name, collected_at DESC);
CREATE INDEX IF NOT EXISTS official_index_resources_snapshot_id_idx
    ON official_index_resources(snapshot_id);

CREATE OR REPLACE FUNCTION reject_v4_rollout_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'V4 rollout evidence is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS raw_source_objects_append_only ON raw_source_objects;
CREATE TRIGGER raw_source_objects_append_only
BEFORE UPDATE OR DELETE ON raw_source_objects
FOR EACH ROW EXECUTE FUNCTION reject_v4_rollout_mutation();

DROP TRIGGER IF EXISTS official_index_snapshots_append_only ON official_index_snapshots;
CREATE TRIGGER official_index_snapshots_append_only
BEFORE UPDATE OR DELETE ON official_index_snapshots
FOR EACH ROW EXECUTE FUNCTION reject_v4_rollout_mutation();

DROP TRIGGER IF EXISTS official_index_resources_append_only ON official_index_resources;
CREATE TRIGGER official_index_resources_append_only
BEFORE UPDATE OR DELETE ON official_index_resources
FOR EACH ROW EXECUTE FUNCTION reject_v4_rollout_mutation();

