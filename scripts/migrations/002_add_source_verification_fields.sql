-- ==============================================================================
-- NEXO Data Platform - Source Verification & Storage Configuration Migration
-- Migration: 002_add_source_verification_fields.sql
-- Description: Adds governance, audit, and verification fields to the sources table,
--              and sets up the private nexo-government-documents storage bucket.
-- ==============================================================================

-- 1. Extend the sources table with official verification metadata
ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS organization_name TEXT,
    ADD COLUMN IF NOT EXISTS country TEXT NOT NULL DEFAULT 'IN',
    ADD COLUMN IF NOT EXISTS state TEXT,
    ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'PENDING',
    ADD COLUMN IF NOT EXISTS verification_method TEXT,
    ADD COLUMN IF NOT EXISTS verification_notes TEXT,
    ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;

-- 2. Verification status check constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_sources_verification_status'
    ) THEN
        ALTER TABLE sources
            ADD CONSTRAINT chk_sources_verification_status
            CHECK (verification_status IN ('PENDING', 'VERIFIED', 'REJECTED', 'NEEDS_REVIEW'));
    END IF;
END $$;

-- 3. Indexes for governance and authority filtering
CREATE INDEX IF NOT EXISTS idx_sources_verification_status ON sources (verification_status);
CREATE INDEX IF NOT EXISTS idx_sources_country ON sources (country);
CREATE INDEX IF NOT EXISTS idx_sources_state ON sources (state) WHERE state IS NOT NULL;

-- 4. Comments for data dictionary
COMMENT ON COLUMN sources.organization_name IS 'Official parent ministry, department, or statutory body.';
COMMENT ON COLUMN sources.verification_status IS 'Audit status: PENDING, VERIFIED, REJECTED, or NEEDS_REVIEW.';
COMMENT ON COLUMN sources.verification_method IS 'Documented method used to verify official authority.';
COMMENT ON COLUMN sources.verification_notes IS 'Auditable rationale and evidence for verification.';

-- ==============================================================================
-- Storage: Configure Private nexo-government-documents Bucket
-- ==============================================================================
-- Ensure the private storage bucket exists with size and format restrictions
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'nexo-government-documents',
    'nexo-government-documents',
    false, -- Strictly private by default
    104857600, -- 100 MB max file size limit
    ARRAY[
        'application/pdf',
        'text/html',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/csv',
        'application/json',
        'application/xml',
        'text/xml',
        'text/plain',
        'image/jpeg',
        'image/png',
        'image/tiff',
        'image/webp'
    ]
)
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = 104857600;

-- Storage Security: Restrict bucket access to authenticated and service_role
DROP POLICY IF EXISTS "Private bucket - service role and authenticated upload" ON storage.objects;
CREATE POLICY "Private bucket - service role and authenticated upload"
    ON storage.objects FOR INSERT
    TO authenticated, service_role
    WITH CHECK (bucket_id = 'nexo-government-documents');

DROP POLICY IF EXISTS "Private bucket - authenticated and service role read" ON storage.objects;
CREATE POLICY "Private bucket - authenticated and service role read"
    ON storage.objects FOR SELECT
    TO authenticated, service_role
    USING (bucket_id = 'nexo-government-documents');
