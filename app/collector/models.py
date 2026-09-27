"""
NEXO Data Platform - Document Discovery & Collector Data Models
Defines data structures for tracking discovered links, documents, crawl statistics,
and pipeline checkpoints.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set
from pydantic import BaseModel, Field


class DiscoveredDocument(BaseModel):
    """
    Representation of an official government document identified during crawling.
    Tracks its discovery, canonicalization, validation, versioning, and staging lifecycle.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    source_name: str
    source_url: str
    discovered_url: str
    canonical_url: str = ""
    final_url: str = ""
    depth: int = 0
    title: str = ""
    content_type: str = "document"  # document, webpage, dataset, etc.
    extension: str = ""
    mime_type: str = ""
    file_size: int = 0
    sha256: Optional[str] = None
    relevance_category: str = ""
    relevance_score: float = 0.0
    relevance_reason: str = ""
    relevance_status: str = "CONFIRMED"  # CONFIRMED, NEEDS_REVIEW, IRRELEVANT
    state: Optional[str] = None
    district: Optional[str] = None
    government_level: str = "Central"  # Central, State, District, Unknown
    language: str = "en"
    requires_ocr: bool = False
    storage_path: Optional[str] = None
    staged_path: Optional[str] = None
    discovery_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    download_timestamp: Optional[str] = None
    version: int = 1
    previous_sha256: Optional[str] = None
    status: str = "discovered"  # discovered, downloaded, staged, duplicate_preserved, failed, quarantined, dry_run_staged
    failure_reason: Optional[str] = None

    def to_manifest_dict(self) -> Dict[str, Any]:
        """Serializes record for the collector manifest."""
        return self.model_dump()


class CrawlStats(BaseModel):
    """Tracks discovery and collection metrics across a pipeline execution."""
    total_sources: int = 0
    urls_discovered: int = 0
    documents_identified: int = 0
    documents_downloaded: int = 0
    duplicates_preserved: int = 0
    new_versions: int = 0
    documents_failed: int = 0
    documents_staged: int = 0
    start_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: Optional[str] = None

    def to_summary_dict(self) -> Dict[str, Any]:
        """Returns statistics summary."""
        return self.model_dump()


class CheckpointState(BaseModel):
    """Tracks state across collector runs to allow resilient resume."""
    visited_urls: List[str] = Field(default_factory=list)
    processed_hashes: List[str] = Field(default_factory=list)
    completed_sources: List[str] = Field(default_factory=list)
    last_updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
