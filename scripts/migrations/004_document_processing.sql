-- ==============================================================================
-- NEXO Data Platform - Document Content Processing Schema Migration
-- Migration: 004_document_processing.sql
-- Description: Creates the document_processing table to store text extraction,
--              OCR audit metadata, text quality metrics, and processed artifact pointers.
-- ==============================================================================

-- 1. Create document_processing table
CREATE TABLE IF NOT EXISTS document_processing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    raw_sha256 TEXT NOT NULL,
    processor_version TEXT NOT NULL DEFAULT '1.0.0',
    extraction_method TEXT NOT NULL,
    extraction_status TEXT NOT NULL, -- 'SUCCESS', 'OCR_REQUIRED', 'LOW_TEXT', 'EXTRACTION_FAILED', 'NEEDS_REVIEW'
    ocr_status TEXT DEFAULT 'NOT_REQUIRED', -- 'NOT_REQUIRED', 'PENDING', 'COMPLETED', 'FAILED', 'SKIPPED'
    ocr_language TEXT,
    ocr_confidence NUMERIC,
    character_count INTEGER NOT NULL DEFAULT 0,
    word_count INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER,
    language_detected TEXT,
    text_quality_status TEXT NOT NULL, -- 'HIGH', 'MEDIUM', 'LOW', 'EMPTY', 'CORRUPT'
    processed_storage_path TEXT,
    processing_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processing_completed_at TIMESTAMPTZ,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_processing_sha_version UNIQUE (raw_sha256, processor_version)
);

-- 2. Performance & Query Indexes
CREATE INDEX IF NOT EXISTS idx_doc_proc_document_id ON document_processing (document_id);
CREATE INDEX IF NOT EXISTS idx_doc_proc_raw_sha256 ON document_processing (raw_sha256);
CREATE INDEX IF NOT EXISTS idx_doc_proc_extraction_status ON document_processing (extraction_status);
CREATE INDEX IF NOT EXISTS idx_doc_proc_text_quality ON document_processing (text_quality_status);
CREATE INDEX IF NOT EXISTS idx_doc_proc_processor_version ON document_processing (processor_version);

-- 3. Automatic updated_at Trigger
DROP TRIGGER IF EXISTS trg_document_processing_updated_at ON document_processing;
CREATE TRIGGER trg_document_processing_updated_at
    BEFORE UPDATE ON document_processing
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 4. Enable Row Level Security (RLS)
ALTER TABLE document_processing ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies
DROP POLICY IF EXISTS "Public can view completed document processing" ON document_processing;
CREATE POLICY "Public can view completed document processing"
    ON document_processing FOR SELECT
    TO anon, authenticated
    USING (extraction_status IN ('SUCCESS', 'LOW_TEXT'));

DROP POLICY IF EXISTS "Service role full access on document_processing" ON document_processing;
CREATE POLICY "Service role full access on document_processing"
    ON document_processing FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 6. Comments for Data Dictionary
COMMENT ON TABLE document_processing IS 'Processed content metadata, text quality metrics, and artifact references for government documents.';
COMMENT ON COLUMN document_processing.raw_sha256 IS 'Cryptographic hash linking processing record immutably to original raw document.';
COMMENT ON COLUMN document_processing.processor_version IS 'Semantic version of the processing pipeline for versioned reprocessing.';
COMMENT ON COLUMN document_processing.extraction_status IS 'Extraction state: SUCCESS, OCR_REQUIRED, LOW_TEXT, EXTRACTION_FAILED, NEEDS_REVIEW.';
COMMENT ON COLUMN document_processing.processed_storage_path IS 'Path to extracted text and metadata package in storage.';
