"""
NEXO Data Platform - Ingestion Exception Hierarchy
Specialized exceptions for pipeline, validation, storage, and immutability errors.
"""


class NexoIngestionError(Exception):
    """Base exception for all ingestion-related errors."""
    pass


class ValidationError(NexoIngestionError):
    """Raised when metadata, URL, or document integrity fails validation."""
    pass


class DuplicateDocumentError(NexoIngestionError):
    """Raised when a document with identical SHA-256 already exists in registry/manifest."""
    def __init__(self, sha256: str, message: str = "Duplicate document detected"):
        self.sha256 = sha256
        super().__init__(f"{message}: {sha256}")


class ImmutableDocumentViolationError(NexoIngestionError):
    """
    Raised when an operation attempts to overwrite, delete, or modify
    an existing ingested document in storage or database records.
    """
    def __init__(self, storage_path: str, message: str = "Immutable document violation"):
        self.storage_path = storage_path
        super().__init__(
            f"{message}: Cannot overwrite or mutate existing document at '{storage_path}'."
        )


class UnsupportedFormatError(NexoIngestionError):
    """Raised when an ingested file has an unsupported MIME type or extension."""
    def __init__(self, mime_type: str, message: str = "Unsupported document format"):
        self.mime_type = mime_type
        super().__init__(f"{message}: {mime_type}")


class CorruptedFileError(NexoIngestionError):
    """Raised when a file cannot be parsed or has 0 bytes."""
    pass


class StorageUploadError(NexoIngestionError):
    """Raised when a Supabase Storage operation fails."""
    pass


class NetworkTimeoutError(NexoIngestionError):
    """Raised when fetching a remote document times out."""
    pass


class OCRDetectionError(NexoIngestionError):
    """Raised during OCR heuristic evaluation failures."""
    pass
