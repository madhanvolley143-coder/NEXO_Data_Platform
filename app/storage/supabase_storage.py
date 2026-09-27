"""
NEXO Data Platform - Supabase Storage Upload Interface
Enforces document immutability: files cannot be overwritten, modified, or deleted once stored.
"""

import os
from typing import Dict, Any, Optional, Set
from config.storage_config import STORAGE_BUCKET_NAME, get_domain_folder
from config.logging_config import get_logger
from app.ingestion.exceptions import (
    StorageUploadError,
    ImmutableDocumentViolationError,
)

logger = get_logger("storage")


def generate_storage_path(
    domain: str,
    source_id: Optional[str],
    sha256: str,
    extension: str,
) -> str:
    """
    Generates a canonical, deterministic cloud storage path in the format:
    {domain_folder}/{source_id or 'general'}/{sha256}.{ext}
    Content-Addressable: content hash guarantees uniqueness per file content state.
    """
    folder = get_domain_folder(domain)
    source_slug = (source_id or "general").strip().lower().replace(" ", "_")
    clean_ext = extension if extension.startswith(".") else f".{extension}"
    return f"{folder}/{source_slug}/{sha256.lower()}{clean_ext.lower()}"


def document_exists(
    storage_path: str,
    bucket_name: str = STORAGE_BUCKET_NAME,
    client: Optional[Any] = None,
    mock_registry: Optional[Set[str]] = None,
) -> bool:
    """
    Checks if a document exists at the designated storage path.
    If mock_registry is supplied, checks offline mock set.
    Otherwise queries Supabase Storage API if client is available.
    """
    if mock_registry is not None:
        return storage_path in mock_registry

    if client is None:
        return False

    try:
        folder, filename = os.path.split(storage_path)
        response = client.storage.from_(bucket_name).list(folder)
        if isinstance(response, list):
            return any(item.get("name") == filename for item in response)
        return False
    except Exception as exc:
        logger.warning(f"Error querying storage path '{storage_path}': {exc}")
        return False


def upload_document(
    file_content: bytes,
    storage_path: str,
    content_type: str,
    bucket_name: str = STORAGE_BUCKET_NAME,
    dry_run: bool = True,
    client: Optional[Any] = None,
    mock_registry: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Uploads document binary to Supabase Storage with strict immutability guards.
    
    IMMUTABILITY GUARANTEES:
    1. If the file already exists at storage_path, ImmutableDocumentViolationError is raised.
    2. Overwrites ('upsert') are strictly disabled.
    3. In dry_run mode (default), verifies immutability constraints without network calls.
    """
    if not file_content:
        raise StorageUploadError("Cannot upload empty file content (0 bytes).")

    # 1. Immutability Pre-check
    if document_exists(storage_path, bucket_name=bucket_name, client=client, mock_registry=mock_registry):
        logger.error(
            f"Immutability violation: file already exists at '{storage_path}'. Overwrites are forbidden."
        )
        raise ImmutableDocumentViolationError(storage_path)

    file_size = len(file_content)

    if dry_run:
        logger.info(
            f"[DRY RUN - IMMUTABLE] Staging document upload: bucket='{bucket_name}', "
            f"path='{storage_path}', size={file_size} bytes, mime='{content_type}'"
        )
        # If mock_registry provided, simulate recording the immutable path
        if mock_registry is not None:
            mock_registry.add(storage_path)

        return {
            "status": "staged_dry_run",
            "bucket": bucket_name,
            "storage_path": storage_path,
            "content_type": content_type,
            "file_size": file_size,
            "uploaded": False,
            "immutable": True,
        }

    # 2. Live upload (only when dry_run=False and client provided)
    if client is None:
        raise StorageUploadError(
            "Supabase client is required for live storage upload when dry_run=False."
        )

    try:
        logger.info(
            f"Executing live immutable upload: bucket='{bucket_name}', path='{storage_path}'"
        )
        # upsert is explicitly 'false' to enforce database/storage level immutability
        response = client.storage.from_(bucket_name).upload(
            path=storage_path,
            file=file_content,
            file_options={"content-type": content_type, "upsert": "false"},
        )
        return {
            "status": "uploaded",
            "bucket": bucket_name,
            "storage_path": storage_path,
            "content_type": content_type,
            "file_size": file_size,
            "uploaded": True,
            "immutable": True,
            "response": response,
        }
    except Exception as exc:
        err_msg = str(exc)
        if "Duplicate" in err_msg or "already exists" in err_msg or "409" in err_msg:
            raise ImmutableDocumentViolationError(storage_path) from exc
        logger.error(f"Failed to upload document to '{storage_path}': {exc}")
        raise StorageUploadError(f"Storage upload failed: {exc}") from exc
