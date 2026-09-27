"""
NEXO Data Platform - Processing Pipeline Exceptions
Custom exceptions for extraction, OCR routing, quality validation,
and storage manifest operations.
"""


class ProcessingError(Exception):
    """Base exception for document content processing pipeline."""
    pass


class UnsupportedFormatError(ProcessingError):
    """Raised when encountering an unsupported file format or MIME type."""
    pass


class ExtractionError(ProcessingError):
    """Raised when an extractor fails to parse a document."""
    def __init__(self, message: str, error_code: str = "EXTRACTION_FAILED"):
        super().__init__(message)
        self.error_code = error_code


class QualityValidationError(ProcessingError):
    """Raised when text quality fails essential validation constraints."""
    pass


class OCRError(ProcessingError):
    """Raised during OCR routing or engine failure."""
    pass


class OCRUnavailableError(OCRError):
    """Raised when OCR is required but no engine is available."""
    pass


class IdempotencySkip(ProcessingError):
    """Raised or returned when a document has already been processed with the same version."""
    def __init__(self, raw_sha256: str, processor_version: str):
        super().__init__(f"Document with SHA-256 {raw_sha256} already processed at version {processor_version}")
        self.raw_sha256 = raw_sha256
        self.processor_version = processor_version


class CheckpointError(ProcessingError):
    """Raised when loading or persisting the processing checkpoint fails."""
    pass


class ManifestStorageError(ProcessingError):
    """Raised when saving or verifying processed artifacts fails."""
    pass
