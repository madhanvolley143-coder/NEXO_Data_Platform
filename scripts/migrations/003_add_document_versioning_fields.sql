-- ==============================================================================
-- NEXO Data Platform - Document Versioning & Lineage Migration
-- Migration: 003_add_document_versioning_fields.sql
-- Description: Adds version, previous_sha256, and is_current columns to the
--              documents table to support immutable versioning and lineage tracking.
-- ==============================================================================

-- 1. Extend documents table with versioning and lineage columns
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS previous_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT true;

-- 2. Create indexes for versioning and lineage queries
CREATE INDEX IF NOT EXISTS idx_documents_version ON documents (version);
CREATE INDEX IF NOT EXISTS idx_documents_is_current ON documents (is_current);
CREATE INDEX IF NOT EXISTS idx_documents_previous_sha256 ON documents (previous_sha256) WHERE previous_sha256 IS NOT NULL;

-- 3. Comments for data dictionary
COMMENT ON COLUMN documents.version IS 'Sequential integer version number (starting at 1).';
COMMENT ON COLUMN documents.previous_sha256 IS 'SHA-256 hash of the immediate prior document version in the lineage chain.';
COMMENT ON COLUMN documents.is_current IS 'Boolean flag indicating whether this is the latest active version.';
