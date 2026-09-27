"""
NEXO Data Platform - Document Discovery & Collector Pipeline Orchestrator
Coordinates source intake, domain security, polite crawling, relevance filtering,
format validation, SHA-256 calculation, immutability/versioning, and manifest generation.
"""

import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from collections import deque

from config.logging_config import get_logger
from config.storage_config import STORAGE_BUCKET_NAME, get_domain_folder
from app.sources.models import SourceRecord
from app.sources.validator import normalize_url
from app.collector.models import DiscoveredDocument, CrawlStats
from app.collector.security import validate_crawl_target
from app.collector.relevance import assess_relevance, CONFIRMED, NEEDS_REVIEW, IRRELEVANT
from app.collector.discovery import extract_links_from_html, is_document_url
from app.collector.polite_client import PoliteHttpClient
from app.collector.downloader import DocumentDownloader, DownloadResult
from app.collector.geo_tagger import classify_geography
from app.collector.checkpoint import CheckpointManager
from app.ingestion.db_preparer import prepare_document_record
from app.storage.supabase_storage import generate_storage_path

logger = get_logger("collector.orchestrator")

DEFAULT_VERIFIED_MANIFEST = os.path.join("data", "manifests", "sources", "verified_sources.json")
DEFAULT_COLLECTOR_DIR = os.path.join("data", "manifests", "collector")


class CollectorPipeline:
    """
    Main orchestration engine for the NEXO Document Discovery & Collector Pipeline.
    Supports dry-run simulation and safe live staging with zero-trust security.
    """

    def __init__(
        self,
        verified_manifest_path: Optional[str] = None,
        dry_run: bool = True,
        max_depth: int = 1,
        max_pages_per_source: int = 10,
        allowed_domain: Optional[str] = None,
        target_source_id: Optional[str] = None,
        resume: bool = False,
        client: Optional[PoliteHttpClient] = None,
        manifest_dir: Optional[str] = None,
        processed_dir: Optional[str] = None,
    ):
        self.verified_manifest_path = verified_manifest_path or DEFAULT_VERIFIED_MANIFEST
        self.dry_run = dry_run
        self.max_depth = max_depth
        self.max_pages_per_source = max_pages_per_source
        self.allowed_domain = allowed_domain.strip().lower() if allowed_domain else None
        self.target_source_id = target_source_id.strip() if target_source_id else None
        self.resume = resume

        self.manifest_dir = manifest_dir or DEFAULT_COLLECTOR_DIR
        self.processed_dir = processed_dir or os.path.join("data", "processed")
        self.ocr_dir = os.path.join("data", "ocr")

        os.makedirs(self.manifest_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.ocr_dir, exist_ok=True)

        self.client = client or PoliteHttpClient()
        self.downloader = DocumentDownloader(client=self.client)
        self.checkpoint = CheckpointManager(
            checkpoint_path=os.path.join(self.manifest_dir, "checkpoint.json")
        )

        self.discovered_documents: List[DiscoveredDocument] = []
        self.stats = CrawlStats()

    def load_verified_sources(self) -> List[SourceRecord]:
        """
        Loads active and verified sources from the verified manifest.
        Excludes unverified, pending, or inactive sources.
        """
        if not os.path.exists(self.verified_manifest_path):
            logger.warning(f"Verified manifest not found at '{self.verified_manifest_path}'.")
            return []

        with open(self.verified_manifest_path, "r", encoding="utf-8") as f:
            raw_sources = json.load(f)

        verified_records: List[SourceRecord] = []
        for item in raw_sources:
            record = SourceRecord(**item)

            # Strict guardrails: Must be active and officially verified
            if not record.is_active or record.verification_status != "VERIFIED":
                continue

            # Domain filter if specified
            if self.allowed_domain and record.domain_category != self.allowed_domain:
                continue

            # Source ID filter if specified
            if self.target_source_id and record.id != self.target_source_id:
                continue

            verified_records.append(record)

        return verified_records

    def run(self) -> CrawlStats:
        """Executes the discovery and collection pipeline."""
        sources = self.load_verified_sources()
        self.stats.total_sources = len(sources)

        mode_str = "DRY RUN (No live downloads or DB writes)" if self.dry_run else "LIVE COLLECTION"
        logger.info(f"Starting Collector Pipeline [{mode_str}] for {len(sources)} verified sources.")

        for source in sources:
            if self.resume and self.checkpoint.is_source_completed(source.id):
                logger.info(f"Skipping already completed source: '{source.source_name}' ({source.id})")
                continue

            self._crawl_source(source)
            self.checkpoint.mark_source_completed(source.id)
            self.checkpoint.save()

        self.stats.end_time = datetime.now(timezone.utc).isoformat()
        self._export_manifests()
        return self.stats

    def _crawl_source(self, source: SourceRecord) -> None:
        """Discovers documents starting from an official verified source URL."""
        logger.info(f"Crawling source: '{source.source_name}' -> {source.normalized_url}")

        queue = deque([(source.normalized_url, 0)])  # (url, depth)
        pages_crawled = 0
        seen_in_source: Set[str] = set()

        while queue and pages_crawled < self.max_pages_per_source:
            current_url, depth = queue.popleft()

            if current_url in seen_in_source:
                continue
            seen_in_source.add(current_url)

            if self.resume and self.checkpoint.is_visited(current_url):
                continue
            self.checkpoint.mark_visited(current_url)

            pages_crawled += 1
            self.stats.urls_discovered += 1

            fetch_res = self.client.fetch(current_url)
            if not fetch_res.success:
                logger.debug(f"Fetch failed for '{current_url}': {fetch_res.error_message}")
                continue

            # Parse HTML and extract links
            content_str = ""
            try:
                content_str = fetch_res.content.decode("utf-8", errors="replace")
            except Exception:
                pass

            extracted_links = extract_links_from_html(
                base_url=fetch_res.final_url or current_url,
                html_content=content_str,
                source_url=source.normalized_url,
            )

            for target_url, anchor_text, is_doc in extracted_links:
                # 1. Relevance assessment
                relevance = assess_relevance(
                    url=target_url,
                    title=anchor_text,
                    default_domain=source.domain_category,
                )

                if relevance.status == IRRELEVANT:
                    continue

                # 2. Geographic metadata classification
                geo = classify_geography(
                    url=target_url,
                    title=anchor_text,
                    source_state=source.state,
                    authority_level=source.authority_level,
                )

                if is_doc:
                    self._process_document(
                        url=target_url,
                        title=anchor_text or os.path.basename(target_url),
                        source=source,
                        relevance=relevance,
                        geo=geo,
                        depth=depth + 1,
                    )
                elif depth < self.max_depth:
                    # Enqueue internal webpage for deeper discovery
                    if target_url not in seen_in_source:
                        queue.append((target_url, depth + 1))

    def _process_document(
        self,
        url: str,
        title: str,
        source: SourceRecord,
        relevance: Any,
        geo: Any,
        depth: int,
    ) -> None:
        """Handles a discovered document in either dry-run or live mode."""
        self.stats.documents_identified += 1

        ext = os.path.splitext(url)[1].lower() or ".bin"

        doc = DiscoveredDocument(
            source_id=source.id,
            source_name=source.source_name,
            source_url=source.normalized_url,
            discovered_url=url,
            canonical_url=url,
            final_url=url,
            depth=depth,
            title=title,
            extension=ext,
            relevance_category=relevance.category,
            relevance_score=relevance.score,
            relevance_reason=relevance.reason,
            relevance_status=relevance.status,
            state=geo.state,
            district=geo.district,
            government_level=geo.government_level,
            language=source.language,
        )

        if self.dry_run:
            doc.status = "dry_run_staged"
            doc.storage_path = generate_storage_path(
                domain=relevance.category,
                source_id=source.id,
                sha256="dry_run_simulation_hash",
                extension=ext,
            )
            self.discovered_documents.append(doc)
            self.stats.documents_staged += 1
            return

        # LIVE COLLECTION: Download, validate, hash, stage locally
        res: DownloadResult = self.downloader.download_and_validate(url)

        if not res.success:
            doc.status = "failed"
            doc.failure_reason = res.failure_reason
            self.discovered_documents.append(doc)
            self.stats.documents_failed += 1
            return

        doc.sha256 = res.sha256
        doc.file_size = res.file_size
        doc.mime_type = res.mime_type
        doc.extension = res.extension
        doc.requires_ocr = res.requires_ocr
        doc.download_timestamp = datetime.now(timezone.utc).isoformat()

        # Check for duplicates using checkpoint
        if self.checkpoint.is_hash_processed(res.sha256):
            doc.status = "duplicate_preserved"
            self.stats.duplicates_preserved += 1
        else:
            self.checkpoint.mark_hash_processed(res.sha256)
            doc.status = "downloaded"
            self.stats.documents_downloaded += 1

            # Stage locally in data/processed/
            folder = get_domain_folder(relevance.category)
            stage_dir = os.path.join(self.processed_dir, folder, source.id)
            os.makedirs(stage_dir, exist_ok=True)
            local_file = os.path.join(stage_dir, f"{res.sha256}{res.extension}")

            if not os.path.exists(local_file):
                with open(local_file, "wb") as f:
                    f.write(res.content)
            doc.staged_path = local_file

            # If OCR required, register in data/ocr/
            if res.requires_ocr:
                ocr_file = os.path.join(self.ocr_dir, f"{res.sha256}{res.extension}")
                if not os.path.exists(ocr_file):
                    with open(ocr_file, "wb") as f:
                        f.write(res.content)

            doc.storage_path = generate_storage_path(
                domain=relevance.category,
                source_id=source.id,
                sha256=res.sha256,
                extension=res.extension,
            )
            self.stats.documents_staged += 1

        self.discovered_documents.append(doc)

    def _export_manifests(self) -> None:
        """Writes discovery and collection manifests."""
        json_path = os.path.join(self.manifest_dir, "discovered_documents.json")
        jsonl_path = os.path.join(self.manifest_dir, "collection_manifest.jsonl")

        data = [d.to_manifest_dict() for d in self.discovered_documents]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info(
            f"Saved collector manifests: {json_path} and {jsonl_path} "
            f"({len(data)} total records, {self.stats.documents_staged} staged)."
        )
