"""
NEXO Data Platform - Ingestion Module
"""

from app.ingestion.document_ingestion import DocumentIngestor, IngestionResult
from app.ingestion.manifest import ManifestRecord, ManifestManager
from app.ingestion.format_detector import (
    detect_format,
    calculate_sha256,
    calculate_file_sha256,
    FormatDetectionResult,
)
from app.ingestion.db_preparer import (
    prepare_document_record,
    prepare_source_record,
    prepare_scheme_record,
    prepare_scheme_version_record,
    prepare_sync_log_record,
)
from app.ingestion.exceptions import (
    NexoIngestionError,
    ValidationError,
    DuplicateDocumentError,
    ImmutableDocumentViolationError,
    UnsupportedFormatError,
    CorruptedFileError,
    StorageUploadError,
    NetworkTimeoutError,
    OCRDetectionError,
)
from app.ingestion.validation import (
    validate_sha256,
    validate_source_url,
    validate_target_domain,
    validate_file_size,
    validate_mime_type,
    validate_metadata,
    check_duplicate_sha256,
)
from app.ingestion.secure_cloud_ingestor import (
    SecureCloudIngestor,
    IngestionStatus,
    IngestionAuditRecord,
    redact_secrets,
)

__all__ = [
    "SecureCloudIngestor",
    "IngestionStatus",
    "IngestionAuditRecord",
    "redact_secrets",
    "DocumentIngestor",
    "IngestionResult",
    "ManifestRecord",
    "ManifestManager",
    "detect_format",
    "calculate_sha256",
    "calculate_file_sha256",
    "FormatDetectionResult",
    "prepare_document_record",
    "prepare_source_record",
    "prepare_scheme_record",
    "prepare_scheme_version_record",
    "prepare_sync_log_record",
    "NexoIngestionError",
    "ValidationError",
    "DuplicateDocumentError",
    "ImmutableDocumentViolationError",
    "UnsupportedFormatError",
    "CorruptedFileError",
    "StorageUploadError",
    "NetworkTimeoutError",
    "OCRDetectionError",
    "validate_sha256",
    "validate_source_url",
    "validate_target_domain",
    "validate_file_size",
    "validate_mime_type",
    "validate_metadata",
    "check_duplicate_sha256",
]
