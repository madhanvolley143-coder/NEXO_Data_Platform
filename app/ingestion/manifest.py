"""
NEXO Data Platform - Document Ingestion Manifest System with Version Lineage
Provides structured JSON and JSONL manifest tracking with complete immutability
and version lineage audit trails.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from pydantic import BaseModel, Field, field_validator

from app.ingestion.validation import (
    validate_sha256,
    validate_source_url,
    validate_target_domain,
    validate_file_size,
    validate_mime_type,
)


class ManifestRecord(BaseModel):
    """
    Schema for a single document entry in the ingestion manifest.
    Tracks content identity (SHA-256), immutable storage path, and version lineage.
    """
    source_url: str
    source_id: Optional[str] = None
    title: str
    target_domain: str
    language: str = "en"
    mime_type: str
    file_size: int
    sha256: str
    requires_ocr: bool = False
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    storage_path: str
    processing_status: str = "pending"  # pending, staged, uploaded, duplicate_preserved, failed
    error_message: Optional[str] = None

    # Version lineage & immutability fields
    version: int = 1
    previous_sha256: Optional[str] = None
    previous_storage_path: Optional[str] = None
    is_current: bool = True
    duplicate_check_count: int = 0
    last_verified_at: Optional[str] = None

    @field_validator("sha256")
    def check_sha256(cls, v: str) -> str:
        validate_sha256(v)
        return v.lower().strip()

    @field_validator("source_url")
    def check_url(cls, v: str) -> str:
        validate_source_url(v)
        return v.strip()

    @field_validator("target_domain")
    def check_domain(cls, v: str) -> str:
        validate_target_domain(v)
        return v.strip()

    @field_validator("file_size")
    def check_size(cls, v: int) -> int:
        validate_file_size(v)
        return v

    @field_validator("mime_type")
    def check_mime(cls, v: str) -> str:
        validate_mime_type(v)
        return v.strip()


class ManifestManager:
    """
    Manages reading, appending, searching, and exporting document manifests
    in both JSON and JSONL formats with version lineage queries.
    """

    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        self._is_jsonl = manifest_path.lower().endswith(".jsonl")
        os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)

    def append_record(self, record: ManifestRecord) -> None:
        """Appends a record to the manifest file."""
        if self._is_jsonl:
            with open(self.manifest_path, "a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")
        else:
            # JSON array
            records = self.load_records()
            records.append(record)
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in records], f, indent=2)

    def load_records(self) -> List[ManifestRecord]:
        """Loads all records from the manifest file."""
        if not os.path.exists(self.manifest_path):
            return []

        records: List[ManifestRecord] = []
        if self._is_jsonl:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(ManifestRecord.model_validate_json(line))
        else:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            records.append(ManifestRecord.model_validate(item))
                except json.JSONDecodeError:
                    return []
        return records

    def get_known_hashes(self) -> Set[str]:
        """Returns the set of all SHA-256 hashes recorded in this manifest."""
        return {r.sha256 for r in self.load_records()}

    def has_sha256(self, sha256_hash: str) -> bool:
        """Checks if a document with this SHA-256 is already recorded."""
        normalized = sha256_hash.strip().lower()
        return normalized in self.get_known_hashes()

    def get_latest_record_by_url(self, source_url: str) -> Optional[ManifestRecord]:
        """
        Retrieves the latest current version record for a given source URL.
        """
        clean_url = source_url.strip()
        records = self.load_records()
        matching = [r for r in records if r.source_url == clean_url]
        if not matching:
            return None
        # Return the record marked is_current, or the highest version
        current_recs = [r for r in matching if r.is_current]
        if current_recs:
            return max(current_recs, key=lambda r: r.version)
        return max(matching, key=lambda r: r.version)

    def get_lineage_by_url(self, source_url: str) -> List[ManifestRecord]:
        """
        Retrieves the chronological version history (v1 -> v2 -> ...) for a source URL.
        """
        clean_url = source_url.strip()
        records = self.load_records()
        matching = [r for r in records if r.source_url == clean_url]
        return sorted(matching, key=lambda r: r.version)

    def record_duplicate_check(
        self,
        sha256: str,
        source_url: str,
        **kwargs: Any,
    ) -> Optional[ManifestRecord]:
        """
        Audits a duplicate detection event without altering original file or creating duplicate.
        Increments duplicate_check_count and updates last_verified_at timestamp.
        """
        records = self.load_records()
        normalized = sha256.strip().lower()
        clean_url = source_url.strip()
        matched: Optional[ManifestRecord] = None

        for r in records:
            if r.sha256 == normalized and r.source_url == clean_url:
                r.duplicate_check_count += 1
                r.last_verified_at = datetime.now(timezone.utc).isoformat()
                r.processing_status = "duplicate_preserved"
                matched = r
                break

        if matched:
            self.write_all(records)
        return matched

    def deprecate_previous_version(self, source_url: str) -> Optional[ManifestRecord]:
        """
        Marks any active current version for this source_url as is_current=False.
        Preserves the previous record completely for audit history.
        """
        records = self.load_records()
        clean_url = source_url.strip()
        deprecating: Optional[ManifestRecord] = None

        for r in records:
            if r.source_url == clean_url and r.is_current:
                r.is_current = False
                deprecating = r

        if deprecating:
            self.write_all(records)
        return deprecating

    def update_status(
        self,
        sha256_hash: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """Updates the processing status of an existing record by SHA-256."""
        records = self.load_records()
        normalized = sha256_hash.strip().lower()
        found = False

        for r in records:
            if r.sha256 == normalized:
                r.processing_status = status
                r.error_message = error_message
                found = True
                break

        if found:
            self.write_all(records)
        return found

    def write_all(self, records: List[ManifestRecord]) -> None:
        """Rewrites the manifest with the provided records list."""
        if self._is_jsonl:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(r.model_dump_json() + "\n")
        else:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in records], f, indent=2)

    def export_json(self, destination_path: str) -> None:
        """Exports the current manifest to standard formatted JSON."""
        records = self.load_records()
        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
        with open(destination_path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in records], f, indent=2)

    def export_jsonl(self, destination_path: str) -> None:
        """Exports the current manifest to JSONL format."""
        records = self.load_records()
        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
        with open(destination_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(r.model_dump_json() + "\n")
