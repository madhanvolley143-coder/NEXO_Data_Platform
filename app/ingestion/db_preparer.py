"""
NEXO Data Platform - Database Payload Preparation Module
Formats and validates record dictionaries matching core PostgreSQL tables.
Does NOT execute database queries or writes.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid


def prepare_document_record(
    title: str,
    source_url: str,
    target_domain: str,
    mime_type: str,
    file_size: int,
    sha256: str,
    storage_path: str,
    source_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    document_type: str = "guideline",
    language: str = "en",
    requires_ocr: bool = False,
    scraped_at: Optional[str] = None,
    published_at: Optional[str] = None,
    is_active: bool = True,
    doc_id: Optional[str] = None,
    version: int = 1,
    previous_sha256: Optional[str] = None,
    is_current: bool = True,
) -> Dict[str, Any]:
    """
    Prepares a clean payload ready for insertion into the 'documents' table.
    Maintains document immutability and version lineage.
    """
    return {
        "id": doc_id or str(uuid.uuid4()),
        "source_id": source_id,
        "scheme_id": scheme_id,
        "title": title.strip(),
        "document_type": document_type.strip(),
        "source_url": source_url.strip(),
        "storage_path": storage_path.strip(),
        "language": language.strip(),
        "mime_type": mime_type.strip(),
        "file_size": file_size,
        "sha256": sha256.lower().strip(),
        "requires_ocr": requires_ocr,
        "scraped_at": scraped_at or datetime.now(timezone.utc).isoformat(),
        "published_at": published_at,
        "is_active": is_active,
        "version": version,
        "previous_sha256": previous_sha256.lower().strip() if previous_sha256 else None,
        "is_current": is_current,
    }


def prepare_source_record(
    name: str,
    url: str,
    domain: str,
    authority_level: str,
    language: str = "en",
    is_active: bool = True,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prepares a clean payload ready for the 'sources' table."""
    return {
        "id": source_id or str(uuid.uuid4()),
        "name": name.strip(),
        "url": url.strip(),
        "domain": domain.strip(),
        "language": language.strip(),
        "authority_level": authority_level.strip(),
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
        "is_active": is_active,
    }


def prepare_scheme_record(
    name: str,
    domain: str,
    government_level: str,
    official_url: str,
    description: Optional[str] = None,
    state: Optional[str] = None,
    eligibility: Optional[str] = None,
    benefits: Optional[str] = None,
    application_process: Optional[str] = None,
    source_id: Optional[str] = None,
    is_active: bool = True,
    scheme_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prepares a clean payload ready for the 'schemes' table."""
    return {
        "id": scheme_id or str(uuid.uuid4()),
        "name": name.strip(),
        "description": description.strip() if description else None,
        "domain": domain.strip(),
        "government_level": government_level.strip(),
        "state": state.strip() if state else None,
        "eligibility": eligibility.strip() if eligibility else None,
        "benefits": benefits.strip() if benefits else None,
        "application_process": application_process.strip() if application_process else None,
        "official_url": official_url.strip(),
        "source_id": source_id,
        "is_active": is_active,
    }


def prepare_scheme_version_record(
    scheme_id: str,
    version_number: int,
    content_hash: str,
    snapshot: Dict[str, Any],
    changed_fields: Optional[Dict[str, Any]] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    is_current: bool = True,
    version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prepares a clean payload ready for the 'scheme_versions' table."""
    return {
        "id": version_id or str(uuid.uuid4()),
        "scheme_id": scheme_id,
        "version_number": version_number,
        "content_hash": content_hash.strip(),
        "changed_fields": changed_fields or {},
        "snapshot": snapshot,
        "valid_from": valid_from or datetime.now(timezone.utc).isoformat(),
        "valid_until": valid_until,
        "is_current": is_current,
    }


def prepare_sync_log_record(
    status: str,
    source_id: Optional[str] = None,
    documents_found: int = 0,
    documents_added: int = 0,
    documents_updated: int = 0,
    documents_failed: int = 0,
    error_message: Optional[str] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    log_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prepares a clean payload ready for the 'data_sync_logs' table."""
    return {
        "id": log_id or str(uuid.uuid4()),
        "source_id": source_id,
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "completed_at": completed_at,
        "status": status.strip(),
        "documents_found": documents_found,
        "documents_added": documents_added,
        "documents_updated": documents_updated,
        "documents_failed": documents_failed,
        "error_message": error_message,
    }
