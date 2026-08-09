-- Preserve every parser interpretation of the same archived official bytes.
-- Existing evidence is not replaced: legacy rows receive a truthful technical
-- marker and all new rows must identify the parser version that created them.

ALTER TABLE official_index_snapshots
    ADD COLUMN parser_version TEXT NOT NULL DEFAULT 'legacy-unversioned';

ALTER TABLE official_index_snapshots
    ALTER COLUMN parser_version DROP DEFAULT;

ALTER TABLE official_index_snapshots
    DROP CONSTRAINT IF EXISTS official_index_snapshots_source_document_id_key;

ALTER TABLE official_index_snapshots
    ADD CONSTRAINT official_index_snapshots_parser_version_nonempty
        CHECK (length(btrim(parser_version)) > 0),
    ADD CONSTRAINT official_index_snapshots_source_document_parser_unique
        UNIQUE (source_document_id, parser_version);
