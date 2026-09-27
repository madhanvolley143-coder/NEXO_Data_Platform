-- ==============================================================================
-- NEXO Data Platform - Initial Database Schema Migration
-- Migration: 001_initial_schema.sql
-- Description: Core schema for government information, versioning, documents,
--              and synchronization audit logs.
-- ==============================================================================

-- 1. Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Helper Functions
-- Automatic updated_at timestamp maintenance
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- Table 1: sources
-- Official government websites, departmental portals, and statutory registries.
-- ==============================================================================
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    authority_level TEXT NOT NULL, -- e.g., 'central', 'state', 'district', 'local'
    last_checked_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure updated_at exists if sources was pre-created without it
ALTER TABLE sources ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Comments on sources
COMMENT ON TABLE sources IS 'Registry of official government domains, ministries, and portals.';
COMMENT ON COLUMN sources.authority_level IS 'Administrative tier: central, state, district, or local.';
COMMENT ON COLUMN sources.domain IS 'NEXO domain categorization (e.g., Agriculture, Cooperative Governance).';

-- ==============================================================================
-- Table 2: schemes
-- Structured records of government schemes, subsidies, and welfare programs.
-- ==============================================================================
CREATE TABLE IF NOT EXISTS schemes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    domain TEXT NOT NULL,
    government_level TEXT NOT NULL, -- e.g., 'central', 'state'
    state TEXT,                     -- NULL for central schemes, state name for state schemes
    eligibility TEXT,
    benefits TEXT,
    application_process TEXT,
    official_url TEXT NOT NULL,
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Comments on schemes
COMMENT ON TABLE schemes IS 'Verified government welfare schemes, entitlements, and initiatives.';
COMMENT ON COLUMN schemes.source_id IS 'Foreign key reference to originating official source.';

-- ==============================================================================
-- Table 3: scheme_versions
-- Point-in-time snapshots and audit history for scheme revisions.
-- ==============================================================================
CREATE TABLE IF NOT EXISTS scheme_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id UUID NOT NULL REFERENCES schemes(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    changed_fields JSONB DEFAULT '{}'::jsonb,
    snapshot JSONB NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_scheme_versions_scheme_version UNIQUE (scheme_id, version_number)
);

-- Comments on scheme_versions
COMMENT ON TABLE scheme_versions IS 'Historical versions and audit trails of scheme changes.';
COMMENT ON COLUMN scheme_versions.snapshot IS 'Complete JSONB snapshot of the scheme at this version.';
COMMENT ON COLUMN scheme_versions.changed_fields IS 'JSONB diff showing which attributes changed in this version.';

-- ==============================================================================
-- Table 4: documents
-- Metadata and storage pointers for original official documents (PDF, gazettes).
-- ==============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    scheme_id UUID REFERENCES schemes(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    document_type TEXT, -- e.g., 'guideline', 'gazette', 'circular', 'application_form'
    source_url TEXT NOT NULL,
    storage_path TEXT,  -- Path within Supabase Storage bucket
    language TEXT NOT NULL DEFAULT 'en',
    mime_type TEXT,
    file_size BIGINT,
    sha256 TEXT NOT NULL UNIQUE,
    requires_ocr BOOLEAN NOT NULL DEFAULT false,
    scraped_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Comments on documents
COMMENT ON TABLE documents IS 'Metadata for original government documents, circulars, and forms.';
COMMENT ON COLUMN documents.sha256 IS 'Cryptographic hash to ensure tamper-proofing and avoid duplicate files.';

-- ==============================================================================
-- Table 5: data_sync_logs
-- Audit log tracking every scraper run and ingestion pipeline execution.
-- ==============================================================================
CREATE TABLE IF NOT EXISTS data_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL, -- e.g., 'in_progress', 'completed', 'failed', 'partial'
    documents_found INTEGER DEFAULT 0,
    documents_added INTEGER DEFAULT 0,
    documents_updated INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Comments on data_sync_logs
COMMENT ON TABLE data_sync_logs IS 'Execution logs for automated web scrapers and sync jobs.';

-- ==============================================================================
-- Triggers: Automatic updated_at Maintenance
-- ==============================================================================
DROP TRIGGER IF EXISTS trg_sources_updated_at ON sources;
CREATE TRIGGER trg_sources_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_schemes_updated_at ON schemes;
CREATE TRIGGER trg_schemes_updated_at
    BEFORE UPDATE ON schemes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ==============================================================================
-- Performance & Search Indexes
-- ==============================================================================
-- sources indexes
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources (domain);
CREATE INDEX IF NOT EXISTS idx_sources_language ON sources (language);
CREATE INDEX IF NOT EXISTS idx_sources_authority_level ON sources (authority_level);
CREATE INDEX IF NOT EXISTS idx_sources_is_active ON sources (is_active);

-- schemes indexes
CREATE INDEX IF NOT EXISTS idx_schemes_domain ON schemes (domain);
CREATE INDEX IF NOT EXISTS idx_schemes_government_level ON schemes (government_level);
CREATE INDEX IF NOT EXISTS idx_schemes_state ON schemes (state) WHERE state IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_schemes_source_id ON schemes (source_id);
CREATE INDEX IF NOT EXISTS idx_schemes_is_active ON schemes (is_active);

-- scheme_versions indexes
CREATE INDEX IF NOT EXISTS idx_scheme_versions_scheme_id ON scheme_versions (scheme_id);
CREATE INDEX IF NOT EXISTS idx_scheme_versions_is_current ON scheme_versions (is_current);
CREATE INDEX IF NOT EXISTS idx_scheme_versions_content_hash ON scheme_versions (content_hash);

-- documents indexes
CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents (source_id);
CREATE INDEX IF NOT EXISTS idx_documents_scheme_id ON documents (scheme_id);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents (sha256);
CREATE INDEX IF NOT EXISTS idx_documents_language ON documents (language);
CREATE INDEX IF NOT EXISTS idx_documents_is_active ON documents (is_active);
CREATE INDEX IF NOT EXISTS idx_documents_requires_ocr ON documents (requires_ocr) WHERE requires_ocr = true;

-- data_sync_logs indexes
CREATE INDEX IF NOT EXISTS idx_data_sync_logs_source_id ON data_sync_logs (source_id);
CREATE INDEX IF NOT EXISTS idx_data_sync_logs_status ON data_sync_logs (status);
CREATE INDEX IF NOT EXISTS idx_data_sync_logs_started_at ON data_sync_logs (started_at DESC);

-- ==============================================================================
-- Security: Row Level Security (RLS) Policies
-- ==============================================================================
-- Enable RLS across all tables
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE schemes ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheme_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_sync_logs ENABLE ROW LEVEL SECURITY;

-- 1. Read policies for anon and authenticated users (Public read of active data)
DROP POLICY IF EXISTS "Public can view active sources" ON sources;
CREATE POLICY "Public can view active sources"
    ON sources FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS "Public can view active schemes" ON schemes;
CREATE POLICY "Public can view active schemes"
    ON schemes FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS "Public can view current scheme versions" ON scheme_versions;
CREATE POLICY "Public can view current scheme versions"
    ON scheme_versions FOR SELECT
    TO anon, authenticated
    USING (is_current = true);

DROP POLICY IF EXISTS "Public can view active documents" ON documents;
CREATE POLICY "Public can view active documents"
    ON documents FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

-- 2. Service role / Data pipeline full write access
DROP POLICY IF EXISTS "Service role full access on sources" ON sources;
CREATE POLICY "Service role full access on sources"
    ON sources FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on schemes" ON schemes;
CREATE POLICY "Service role full access on schemes"
    ON schemes FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on scheme_versions" ON scheme_versions;
CREATE POLICY "Service role full access on scheme_versions"
    ON scheme_versions FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on documents" ON documents;
CREATE POLICY "Service role full access on documents"
    ON documents FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on data_sync_logs" ON data_sync_logs;
CREATE POLICY "Service role full access on data_sync_logs"
    ON data_sync_logs FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
