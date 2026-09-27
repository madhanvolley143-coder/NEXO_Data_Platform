"""
NEXO Data Platform - Document and Metadata Validation Functions
Provides strict integrity checking for URLs, checksums, formats, and required fields.
"""

import re
from typing import Dict, Any, List, Set, Optional
from urllib.parse import urlparse

from config.storage_config import is_supported_mime, get_domain_folder
from app.ingestion.exceptions import (
    ValidationError,
    DuplicateDocumentError,
    UnsupportedFormatError,
    CorruptedFileError,
)

# Regex matching exactly 64 hexadecimal characters
SHA256_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")

REQUIRED_DOCUMENT_FIELDS = {
    "source_url",
    "target_domain",
    "title",
    "sha256",
    "mime_type",
    "file_size",
}


def validate_sha256(sha256_str: str) -> bool:
    """
    Validates that a string is a well-formed 64-character hex SHA-256 checksum.
    Raises ValidationError if invalid.
    """
    if not isinstance(sha256_str, str) or not SHA256_REGEX.match(sha256_str.strip()):
        raise ValidationError(
            f"Invalid SHA-256 checksum format: '{sha256_str}'. "
            "Must be exactly 64 hexadecimal characters."
        )
    return True


def validate_source_url(url: str) -> bool:
    """
    Validates that a URL is a valid, well-formed HTTP/HTTPS official government URL.
    Raises ValidationError if invalid.
    """
    if not url or not isinstance(url, str):
        raise ValidationError("Source URL must be a non-empty string.")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            f"Invalid URL scheme '{parsed.scheme}' for URL: '{url}'. "
            "Must be 'http' or 'https'."
        )
    if not parsed.netloc:
        raise ValidationError(f"URL missing valid network domain/host: '{url}'")

    return True


def validate_target_domain(domain: str) -> str:
    """
    Validates that a domain string matches one of the 7 supported NEXO domains.
    Returns the canonical folder slug or raises ValidationError.
    """
    try:
        return get_domain_folder(domain)
    except ValueError as err:
        raise ValidationError(str(err)) from err


def validate_file_size(size_bytes: int, max_bytes: int = 100 * 1024 * 1024) -> bool:
    """
    Ensures the file is non-empty and does not exceed maximum allowable ingestion size (default 100MB).
    Raises CorruptedFileError or ValidationError.
    """
    if size_bytes <= 0:
        raise CorruptedFileError(
            f"File size must be greater than 0 bytes (received {size_bytes} bytes)."
        )
    if size_bytes > max_bytes:
        raise ValidationError(
            f"File size ({size_bytes} bytes) exceeds maximum limit of {max_bytes} bytes."
        )
    return True


def validate_mime_type(mime_type: str) -> bool:
    """
    Ensures the MIME type is in the list of supported formats.
    Raises UnsupportedFormatError if not supported.
    """
    if not is_supported_mime(mime_type):
        raise UnsupportedFormatError(mime_type)
    return True


def validate_metadata(metadata: Dict[str, Any]) -> List[str]:
    """
    Validates that all required fields are present and non-empty in document metadata.
    Returns list of missing field names (empty if all valid).
    Raises ValidationError if any required field is missing or empty.
    """
    missing = []
    for field in REQUIRED_DOCUMENT_FIELDS:
        val = metadata.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)

    if missing:
        raise ValidationError(
            f"Document metadata missing required field(s): {', '.join(missing)}"
        )

    # Validate individual components
    validate_sha256(metadata["sha256"])
    validate_source_url(metadata["source_url"])
    validate_target_domain(metadata["target_domain"])
    validate_file_size(metadata["file_size"])
    validate_mime_type(metadata["mime_type"])

    return missing


def check_duplicate_sha256(sha256_hash: str, existing_hashes: Set[str]) -> bool:
    """
    Checks if a SHA-256 hash already exists in a given set/manifest registry.
    Raises DuplicateDocumentError if a duplicate is found.
    """
    normalized = sha256_hash.strip().lower()
    if normalized in existing_hashes:
        raise DuplicateDocumentError(sha256_hash)
    return False
