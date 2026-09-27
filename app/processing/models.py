"""
NEXO Data Platform - Document Content Processing Models
Defines data structures, status enums, and results for text extraction,
OCR processing, text quality analysis, and processing audit tracking.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class ExtractionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    OCR_REQUIRED = "OCR_REQUIRED"
    LOW_TEXT = "LOW_TEXT"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class OCRStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TextQualityStatus(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    EMPTY = "EMPTY"
    CORRUPT = "CORRUPT"


class ExtractionResult(BaseModel):
    """Result of format-specific text extraction."""
    text: str = ""
    page_count: Optional[int] = None
    character_count: int = 0
    word_count: int = 0
    extraction_method: str = "unknown"
    status: ExtractionStatus = ExtractionStatus.SUCCESS
    requires_ocr: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OCRResult(BaseModel):
    """Result of an OCR operation."""
    status: OCRStatus = OCRStatus.NOT_REQUIRED
    text: str = ""
    confidence: Optional[float] = None
    language: Optional[str] = None
    failure_reason: Optional[str] = None


class DocumentProcessingRecord(BaseModel):
    """Database and manifest representation of a processed document."""
    id: Optional[str] = None
    document_id: str
    raw_sha256: str
    processor_version: str = "1.0.0"
    extraction_method: str
    extraction_status: str
    ocr_status: str = OCRStatus.NOT_REQUIRED.value
    ocr_language: Optional[str] = None
    ocr_confidence: Optional[float] = None
    character_count: int = 0
    word_count: int = 0
    page_count: Optional[int] = None
    language_detected: Optional[str] = None
    text_quality_status: str
    processed_storage_path: Optional[str] = None
    processing_started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processing_completed_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProcessingStats(BaseModel):
    """Aggregated processing execution metrics."""
    total_candidates: int = 0
    evaluated: int = 0
    successfully_extracted: int = 0
    ocr_required: int = 0
    ocr_processed: int = 0
    low_text: int = 0
    extraction_failed: int = 0
    needs_review: int = 0
    skipped_already_processed: int = 0
    artifacts_created: int = 0
    db_records_created: int = 0
