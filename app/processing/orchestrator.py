"""
NEXO Data Platform - Content Processing Pipeline Orchestrator
Coordinates document retrieval, format extraction, OCR routing,
text quality validation, metadata enrichment, artifact persistence,
and database audit recording with zero-trust immutability.
"""

import os
import sys
import json
import hashlib
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone

from config.logging_config import get_logger
from config.storage_config import STORAGE_BUCKET_NAME, get_domain_folder
from app.ingestion.secure_cloud_ingestor import SecureCloudIngestor
from app.processing.models import (
    ExtractionStatus,
    OCRStatus,
    TextQualityStatus,
    ExtractionResult,
    DocumentProcessingRecord,
    ProcessingStats,
)
from app.processing.extractors.registry import ExtractorRegistry
from app.processing.validator import TextQualityValidator
from app.processing.enricher import MetadataEnricher
from app.processing.storage import ProcessedStorageManager
from app.processing.ocr.adapter import OCRAdapter

logger = get_logger("processing.orchestrator")

DEFAULT_MANIFEST_DIR = os.path.join("data", "manifests", "processing")
DEFAULT_CHECKPOINT_PATH = os.path.join(DEFAULT_MANIFEST_DIR, "processing_checkpoint.json")
DEFAULT_FAILED_DIR = os.path.join("data", "failed", "processing")


class DocumentContentProcessor:
    """
    Main execution engine for the NEXO Document Content Processing Pipeline.
    Supports dry-run simulation and safe live cloud execution.
    """

    PROCESSOR_VERSION = "1.0.0"

    def __init__(
        self,
        dry_run: bool = True,
        manifest_dir: Optional[str] = None,
        checkpoint_path: Optional[str] = None,
        ocr_adapter: Optional[OCRAdapter] = None,
        storage_manager: Optional[ProcessedStorageManager] = None,
        client: Optional[Any] = None,
        force_reprocess: bool = False,
    ):
        self.dry_run = dry_run
        self.force_reprocess = force_reprocess
        self.manifest_dir = manifest_dir or DEFAULT_MANIFEST_DIR
        self.checkpoint_path = checkpoint_path or DEFAULT_CHECKPOINT_PATH
        self.failed_dir = DEFAULT_FAILED_DIR

        os.makedirs(self.manifest_dir, exist_ok=True)
        os.makedirs(self.failed_dir, exist_ok=True)

        self.ocr_adapter = ocr_adapter or OCRAdapter()
        self.registry = ExtractorRegistry(ocr_adapter=self.ocr_adapter)
        self.validator = TextQualityValidator()
        self.enricher = MetadataEnricher(processor_version=self.PROCESSOR_VERSION)
        self.storage_manager = storage_manager or ProcessedStorageManager()

        # Database client
        self.client = client
        if self.client is None:
            try:
                from config.supabase_client import get_supabase_admin_client
                self.client = get_supabase_admin_client()
            except Exception as exc:
                logger.warning(f"Could not initialize admin client directly: {exc}")
                self.ingestor = SecureCloudIngestor(dry_run=self.dry_run)
                self.client = self.ingestor.client

        self.checkpoint = self._load_checkpoint()
        self.stats = ProcessingStats()

    def _load_checkpoint(self) -> Dict[str, Any]:
        """Loads processing checkpoint from disk."""
        if os.path.isfile(self.checkpoint_path):
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning(f"Could not read checkpoint file: {exc}")
        return {"last_updated": None, "processed_documents": {}}

    def _save_checkpoint(self) -> None:
        """Atomically saves processing checkpoint."""
        self.checkpoint["last_updated"] = datetime.now(timezone.utc).isoformat()
        temp_path = self.checkpoint_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.checkpoint, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.checkpoint_path)
        except Exception as exc:
            logger.error(f"Failed saving checkpoint: {exc}")

    def fetch_live_documents(
        self,
        limit: Optional[int] = None,
        document_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves active verified documents from PostgreSQL."""
        try:
            query = self.client.table("documents").select(
                "id, title, source_url, source_id, document_type, storage_path, "
                "language, mime_type, file_size, sha256, requires_ocr, published_at"
            ).eq("is_active", True)

            if document_id:
                query = query.eq("id", document_id)

            res = query.execute()
            docs = res.data or []

            # Also fetch source metadata to attach domain/name
            src_res = self.client.table("sources").select("id, name, domain, state, authority_level").execute()
            sources_map = {s["id"]: s for s in (src_res.data or [])}

            enriched_docs = []
            for d in docs:
                src = sources_map.get(d.get("source_id"), {})
                d["source_name"] = src.get("name")
                d["domain"] = src.get("domain") or "general"
                d["state"] = src.get("state")
                enriched_docs.append(d)

            if limit and limit > 0:
                enriched_docs = enriched_docs[:limit]

            return enriched_docs

        except Exception as exc:
            logger.error(f"Failed fetching documents from database: {exc}")
            raise

    def retrieve_raw_bytes(self, doc: Dict[str, Any]) -> Tuple[bytes, str]:
        """
        Retrieves raw document bytes from local CAS storage or Supabase Storage.
        Returns (content_bytes, location_info).
        """
        sha = doc.get("sha256", "").lower().strip()
        domain = doc.get("domain", "general")
        source_id = doc.get("source_id", "unknown")
        storage_path = doc.get("storage_path", "")

        # 1. Check local processed/staged directory
        domain_folder = get_domain_folder(domain)
        ext = os.path.splitext(storage_path)[1] if storage_path else ".bin"
        local_candidates = [
            os.path.join("data", "processed", domain_folder, source_id, f"{sha}{ext}"),
            os.path.join("data", "ocr", domain_folder, source_id, f"{sha}{ext}"),
        ]

        for lp in local_candidates:
            if os.path.isfile(lp):
                with open(lp, "rb") as f:
                    content = f.read()
                calc_sha = hashlib.sha256(content).hexdigest().lower()
                if calc_sha == sha:
                    return content, f"local_cas:{lp}"

        # 2. Download from Supabase Storage
        if not storage_path:
            raise FileNotFoundError(f"Document {doc.get('id')} has no storage_path or local cache.")

        logger.info(f"Downloading '{storage_path}' from bucket '{STORAGE_BUCKET_NAME}'...")
        obj_bytes = self.client.storage.from_(STORAGE_BUCKET_NAME).download(storage_path)
        calc_sha = hashlib.sha256(obj_bytes).hexdigest().lower()
        if calc_sha != sha:
            raise ValueError(f"Downloaded object SHA mismatch: expected {sha}, got {calc_sha}")

        return obj_bytes, f"storage:{storage_path}"

    def process_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Processes a single raw document through the complete pipeline."""
        doc_id = doc.get("id")
        raw_sha = doc.get("sha256", "").lower().strip()
        title = doc.get("title", "Untitled Document")
        domain = doc.get("domain", "general")
        source_id = doc.get("source_id", "unknown")
        mime_type = doc.get("mime_type")
        storage_path = doc.get("storage_path") or ""
        ext = os.path.splitext(storage_path)[1].lower() if storage_path else ""
        initial_requires_ocr = doc.get("requires_ocr", False)
        declared_lang = doc.get("language") or "en"

        logger.info(f"Processing document '{title[:40]}' (ID: {doc_id}, SHA: {raw_sha[:12]}...)")

        # 1. Idempotency Check
        proc_history = self.checkpoint.setdefault("processed_documents", {})
        if raw_sha in proc_history and not self.force_reprocess:
            prev = proc_history[raw_sha]
            if prev.get("processor_version") == self.PROCESSOR_VERSION and prev.get("status") in (
                ExtractionStatus.SUCCESS.value,
                ExtractionStatus.LOW_TEXT.value,
                ExtractionStatus.OCR_REQUIRED.value,
                ExtractionStatus.NEEDS_REVIEW.value,
            ):
                logger.info(f"Document {raw_sha[:12]}... already processed at version {self.PROCESSOR_VERSION} with status {prev.get('status')}. Skipping.")
                self.stats.skipped_already_processed += 1
                return {
                    "document_id": doc_id,
                    "raw_sha256": raw_sha,
                    "status": "ALREADY_PROCESSED",
                    "reason": f"Already processed at version {self.PROCESSOR_VERSION}",
                    "storage_path": prev.get("storage_path"),
                }

        # 2. Retrieve Raw Bytes (Zero-trust read-only)
        try:
            raw_bytes, source_loc = self.retrieve_raw_bytes(doc)
        except Exception as exc:
            logger.error(f"Retrieval failed for {raw_sha[:12]}...: {exc}")
            self.stats.extraction_failed += 1
            return {
                "document_id": doc_id,
                "raw_sha256": raw_sha,
                "status": ExtractionStatus.EXTRACTION_FAILED.value,
                "error": str(exc),
            }

        # 3. Format Extractor Dispatch
        extractor = self.registry.get_extractor(
            extension=ext,
            mime_type=mime_type,
            filename=storage_path,
        )

        extraction_result: ExtractionResult = extractor.extract(
            file_bytes=raw_bytes,
            filename=storage_path,
            metadata=doc,
        )

        # 4. OCR Routing Check
        # If extraction requested OCR or initial metadata requires OCR, route through OCR adapter
        if extraction_result.requires_ocr or initial_requires_ocr:
            self.stats.ocr_required += 1
            if not extraction_result.text.strip():
                ocr_res = self.ocr_adapter.process(
                    file_bytes=raw_bytes,
                    filename=storage_path,
                    language_hint=declared_lang,
                )
                if ocr_res.status == OCRStatus.COMPLETED and ocr_res.text.strip():
                    extraction_result.text = ocr_res.text
                    extraction_result.character_count = len(ocr_res.text)
                    extraction_result.word_count = len(ocr_res.text.split())
                    extraction_result.status = ExtractionStatus.SUCCESS
                    extraction_result.metadata["ocr_status"] = OCRStatus.COMPLETED.value
                    extraction_result.metadata["ocr_confidence"] = ocr_res.confidence
                    self.stats.ocr_processed += 1
                else:
                    extraction_result.metadata["ocr_status"] = ocr_res.status.value
                    extraction_result.metadata["ocr_failure_reason"] = ocr_res.failure_reason

        # 5. Text Quality Validation
        final_status, quality_status, metrics = self.validator.validate(
            extraction_result=extraction_result,
            declared_language=declared_lang,
            raw_file_size=len(raw_bytes),
            initial_requires_ocr=initial_requires_ocr,
        )

        # 6. Artifact Storage (Local Staging)
        storage_prefix = self.storage_manager.get_relative_storage_prefix(domain, source_id, raw_sha)
        enriched_metadata = self.enricher.enrich(
            raw_doc=doc,
            extraction_result=extraction_result,
            final_status=final_status,
            quality_status=quality_status,
            metrics=metrics,
            processed_storage_path=storage_prefix,
        )

        manifest_data = {
            "processing_version": self.PROCESSOR_VERSION,
            "document_id": doc_id,
            "raw_sha256": raw_sha,
            "domain": domain,
            "source_id": source_id,
            "extraction_method": extraction_result.extraction_method,
            "final_status": final_status.value,
            "quality_status": quality_status.value,
            "metrics": metrics,
            "artifacts": {
                "extracted_txt": "extracted.txt",
                "metadata_json": "metadata.json",
                "processing_manifest_json": "processing_manifest.json",
            },
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        saved_paths = self.storage_manager.save_artifacts(
            domain=domain,
            source_id=source_id,
            raw_sha256=raw_sha,
            extracted_text=extraction_result.text,
            metadata=enriched_metadata,
            manifest=manifest_data,
        )
        self.stats.artifacts_created += 1

        # 7. Database Record Preparation (and write if live)
        db_record = DocumentProcessingRecord(
            document_id=doc_id,
            raw_sha256=raw_sha,
            processor_version=self.PROCESSOR_VERSION,
            extraction_method=extraction_result.extraction_method,
            extraction_status=final_status.value,
            ocr_status=enriched_metadata.get("ocr_status") or OCRStatus.NOT_REQUIRED.value,
            ocr_language=enriched_metadata.get("ocr_language"),
            ocr_confidence=enriched_metadata.get("ocr_confidence"),
            character_count=metrics.get("character_count", 0),
            word_count=metrics.get("word_count", 0),
            page_count=extraction_result.page_count,
            language_detected=metrics.get("detected_language"),
            text_quality_status=quality_status.value,
            processed_storage_path=storage_prefix,
            processing_started_at=enriched_metadata.get("processing_timestamp"),
            processing_completed_at=datetime.now(timezone.utc).isoformat(),
            error_code=extraction_result.error_code,
            error_message=extraction_result.error_message,
        )

        if not self.dry_run:
            try:
                # Upsert processing record based on unique (raw_sha256, processor_version)
                payload = db_record.model_dump(exclude={"id", "created_at", "updated_at"})
                self.client.table("document_processing").upsert(
                    payload,
                    on_conflict="raw_sha256,processor_version",
                ).execute()
                self.stats.db_records_created += 1
            except Exception as db_exc:
                logger.error(f"Failed writing processing record to database for {raw_sha[:12]}...: {db_exc}")

        # Update stats
        if final_status == ExtractionStatus.SUCCESS:
            self.stats.successfully_extracted += 1
        elif final_status == ExtractionStatus.LOW_TEXT:
            self.stats.low_text += 1
        elif final_status == ExtractionStatus.OCR_REQUIRED:
            pass  # Already incremented ocr_required
        elif final_status == ExtractionStatus.NEEDS_REVIEW:
            self.stats.needs_review += 1
        elif final_status == ExtractionStatus.EXTRACTION_FAILED:
            self.stats.extraction_failed += 1

        # 8. Update Checkpoint
        proc_history[raw_sha] = {
            "document_id": doc_id,
            "processor_version": self.PROCESSOR_VERSION,
            "status": final_status.value,
            "quality_tier": quality_status.value,
            "character_count": metrics.get("character_count", 0),
            "word_count": metrics.get("word_count", 0),
            "storage_path": storage_prefix,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._save_checkpoint()

        return enriched_metadata

    def run(
        self,
        limit: Optional[int] = None,
        document_id: Optional[str] = None,
    ) -> ProcessingStats:
        """Executes the pipeline over matching documents."""
        docs = self.fetch_live_documents(limit=limit, document_id=document_id)
        self.stats.total_candidates = len(docs)

        mode_str = "DRY RUN (No live DB writes or remote artifact uploads)" if self.dry_run else "LIVE PROCESSING"
        print("=" * 80)
        print("NEXO DATA PLATFORM - DOCUMENT CONTENT PROCESSING PIPELINE")
        print(f"Mode                 : {mode_str}")
        print(f"Candidates Target    : {len(docs)}")
        print(f"Processor Version    : {self.PROCESSOR_VERSION}")
        print(f"Artifact Staging Dir : {self.storage_manager.local_base_dir}")
        print(f"Checkpoint File      : {self.checkpoint_path}")
        print("=" * 80 + "\n")

        manifest_entries = []

        for idx, doc in enumerate(docs, 1):
            self.stats.evaluated += 1
            title = doc.get("title", "Untitled")[:40]
            sha = doc.get("sha256", "")[:12]

            try:
                res = self.process_document(doc)
                manifest_entries.append(res)
                st = res.get("extraction_status") or res.get("status")
                chars = res.get("character_count", 0)
                words = res.get("word_count", 0)
                print(f"[{idx:03d}/{len(docs)}] {st:<18} | {title:<40} | {chars:,} chars | {words:,} words | SHA: {sha}...")
            except Exception as exc:
                logger.error(f"Failed processing document {idx}: {exc}")
                print(f"[{idx:03d}/{len(docs)}] FAILED             | {title:<40} | Error: {exc}")

        # Write overall processing manifests
        manifest_json_path = os.path.join(self.manifest_dir, "content_processing_manifest.json")
        manifest_jsonl_path = os.path.join(self.manifest_dir, "content_processing_manifest.jsonl")
        summary_path = os.path.join(self.manifest_dir, "content_processing_summary.json")

        with open(manifest_json_path, "w", encoding="utf-8") as f:
            json.dump(manifest_entries, f, indent=2, ensure_ascii=False)

        with open(manifest_jsonl_path, "w", encoding="utf-8") as f:
            for item in manifest_entries:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(self.stats.model_dump(), f, indent=2, ensure_ascii=False)

        self._print_summary()
        return self.stats

    def _print_summary(self) -> None:
        """Prints final execution summary."""
        s = self.stats
        print("\n" + "=" * 80)
        print("CONTENT PROCESSING EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Total Candidates Targeted     : {s.total_candidates}")
        print(f"Total Candidates Evaluated    : {s.evaluated}")
        print(f"Successfully Extracted        : {s.successfully_extracted}")
        print(f"Low Text Detected             : {s.low_text}")
        print(f"OCR Required Flagged          : {s.ocr_required}")
        print(f"OCR Processed                 : {s.ocr_processed}")
        print(f"Needs Review Flagged          : {s.needs_review}")
        print(f"Extraction Failed             : {s.extraction_failed}")
        print(f"Skipped (Already Processed)   : {s.skipped_already_processed}")
        print(f"Processed Artifacts Created   : {s.artifacts_created}")
        print(f"Database Records Created      : {s.db_records_created}")
        print("=" * 80 + "\n")
