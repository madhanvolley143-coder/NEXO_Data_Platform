-- ==============================================================================
-- NEXO Data Platform - Canonical Database Schema
-- File: scripts/schema.sql
-- Description: Consolidated reference schema for NEXO Data Platform PostgreSQL.
--              Includes sources, schemes, scheme_versions, documents,
--              data_sync_logs, triggers, indexes, and Row Level Security.
-- ==============================================================================

-- 1. Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Helper Functions
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Core Tables
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    authority_level TEXT NOT NULL,
    last_checked_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure updated_at exists if sources was pre-created without it
ALTER TABLE sources ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS schemes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    domain TEXT NOT NULL,
    government_level TEXT NOT NULL,
    state TEXT,
    eligibility TEXT,
    benefits TEXT,
    application_process TEXT,
    official_url TEXT NOT NULL,
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    scheme_id UUID REFERENCES schemes(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    document_type TEXT,
    source_url TEXT NOT NULL,
    storage_path TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    mime_type TEXT,
    file_size BIGINT,
    sha256 TEXT NOT NULL UNIQUE,
    requires_ocr BOOLEAN NOT NULL DEFAULT false,
    scraped_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    version INTEGER NOT NULL DEFAULT 1,
    previous_sha256 TEXT,
    is_current BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS data_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    documents_found INTEGER DEFAULT 0,
    documents_added INTEGER DEFAULT 0,
    documents_updated INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Triggers
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

-- 5. Indexes
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources (domain);
CREATE INDEX IF NOT EXISTS idx_sources_language ON sources (language);
CREATE INDEX IF NOT EXISTS idx_sources_authority_level ON sources (authority_level);
CREATE INDEX IF NOT EXISTS idx_sources_is_active ON sources (is_active);

CREATE INDEX IF NOT EXISTS idx_schemes_domain ON schemes (domain);
CREATE INDEX IF NOT EXISTS idx_schemes_government_level ON schemes (government_level);
CREATE INDEX IF NOT EXISTS idx_schemes_state ON schemes (state) WHERE state IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_schemes_source_id ON schemes (source_id);
CREATE INDEX IF NOT EXISTS idx_schemes_is_active ON schemes (is_active);

CREATE INDEX IF NOT EXISTS idx_scheme_versions_scheme_id ON scheme_versions (scheme_id);
CREATE INDEX IF NOT EXISTS idx_scheme_versions_is_current ON scheme_versions (is_current);
CREATE INDEX IF NOT EXISTS idx_scheme_versions_content_hash ON scheme_versions (content_hash);

CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents (source_id);
CREATE INDEX IF NOT EXISTS idx_documents_scheme_id ON documents (scheme_id);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents (sha256);
CREATE INDEX IF NOT EXISTS idx_documents_language ON documents (language);
CREATE INDEX IF NOT EXISTS idx_documents_is_active ON documents (is_active);
CREATE INDEX IF NOT EXISTS idx_documents_requires_ocr ON documents (requires_ocr) WHERE requires_ocr = true;
CREATE INDEX IF NOT EXISTS idx_documents_version ON documents (version);
CREATE INDEX IF NOT EXISTS idx_documents_is_current ON documents (is_current);
CREATE INDEX IF NOT EXISTS idx_documents_previous_sha256 ON documents (previous_sha256) WHERE previous_sha256 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_data_sync_logs_source_id ON data_sync_logs (source_id);
CREATE INDEX IF NOT EXISTS idx_data_sync_logs_status ON data_sync_logs (status);
CREATE INDEX IF NOT EXISTS idx_data_sync_logs_started_at ON data_sync_logs (started_at DESC);

-- 6. Row Level Security (RLS)
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE schemes ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheme_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_sync_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public can view active sources" ON sources;
CREATE POLICY "Public can view active sources"
    ON sources FOR SELECT TO anon, authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS "Public can view active schemes" ON schemes;
CREATE POLICY "Public can view active schemes"
    ON schemes FOR SELECT TO anon, authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS "Public can view current scheme versions" ON scheme_versions;
CREATE POLICY "Public can view current scheme versions"
    ON scheme_versions FOR SELECT TO anon, authenticated
    USING (is_current = true);

DROP POLICY IF EXISTS "Public can view active documents" ON documents;
CREATE POLICY "Public can view active documents"
    ON documents FOR SELECT TO anon, authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS "Service role full access on sources" ON sources;
CREATE POLICY "Service role full access on sources"
    ON sources FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on schemes" ON schemes;
CREATE POLICY "Service role full access on schemes"
    ON schemes FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on scheme_versions" ON scheme_versions;
CREATE POLICY "Service role full access on scheme_versions"
    ON scheme_versions FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on documents" ON documents;
CREATE POLICY "Service role full access on documents"
    ON documents FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on data_sync_logs" ON data_sync_logs;
CREATE POLICY "Service role full access on data_sync_logs"
    ON data_sync_logs FOR ALL TO service_role
    USING (true) WITH CHECK (true);
