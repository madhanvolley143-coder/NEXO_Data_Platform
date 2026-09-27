"""
NEXO Data Platform - Core Document Ingestion Processor with Immutable Versioning
Coordinates file ingestion, format detection, hashing, OCR flagging,
manifest logging, and immutable version lineage.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from config.logging_config import get_logger
from config.storage_config import get_domain_folder
from app.ingestion.exceptions import (
    ValidationError,
    DuplicateDocumentError,
    CorruptedFileError,
    ImmutableDocumentViolationError,
)
from app.ingestion.format_detector import (
    detect_format,
    calculate_sha256,
    FormatDetectionResult,
)
from app.ingestion.validation import (
    validate_source_url,
    validate_target_domain,
    validate_file_size,
    validate_mime_type,
    validate_sha256,
)
from app.ingestion.manifest import ManifestRecord, ManifestManager
from app.storage.supabase_storage import generate_storage_path
from app.ingestion.db_preparer import prepare_document_record

logger = get_logger("ingestion")


@dataclass
class IngestionResult:
    """Encapsulates the complete outcome of a document ingestion operation."""
    sha256: str
    file_size: int
    mime_type: str
    extension: str
    requires_ocr: bool
    storage_path: str
    manifest_record: ManifestRecord
    document_db_record: Dict[str, Any]
    detection_method: str
    version: int = 1
    is_duplicate: bool = False
    staged_local_path: Optional[str] = None
    processing_status: str = "staged"


class DocumentIngestor:
    """
    Reusable processor for ingesting official government documents with strict
    immutability guarantees and version lineage tracking.
    """

    def __init__(
        self,
        manifest_manager: Optional[ManifestManager] = None,
        local_staging_dir: Optional[str] = None,
    ):
        self.manifest_manager = manifest_manager
        self.local_staging_dir = local_staging_dir or os.path.join("data", "processed")
        self.ocr_staging_dir = os.path.join("data", "ocr")

    def ingest_bytes(
        self,
        content: bytes,
        source_url: str,
        target_domain: str,
        title: str,
        filename_hint: Optional[str] = None,
        source_id: Optional[str] = None,
        scheme_id: Optional[str] = None,
        language: str = "en",
        document_type: str = "guideline",
        allow_duplicates: bool = False,
        stage_locally: bool = False,
        published_at: Optional[str] = None,
    ) -> IngestionResult:
        """
        Ingests document from raw in-memory bytes.
        Enforces content-addressable storage and version lineage.
        """
        # 1. Basic validation
        validate_source_url(source_url)
        validate_target_domain(target_domain)
        if not title or not title.strip():
            raise ValidationError("Document title must be a non-empty string.")

        file_size = len(content)
        validate_file_size(file_size)

        # 2. Checksum calculation (Content Identity)
        sha256_hash = calculate_sha256(content)
        validate_sha256(sha256_hash)

        # 3. Format & MIME detection
        detection: FormatDetectionResult = detect_format(
            content=content,
            filename_or_url=filename_hint or source_url,
        )
        validate_mime_type(detection.mime_type)

        scraped_at = datetime.now(timezone.utc).isoformat()

        # 4. Check existing records for this source_url in manifest
        prior_record: Optional[ManifestRecord] = None
        if self.manifest_manager:
            prior_record = self.manifest_manager.get_latest_record_by_url(source_url)

        # Case A: Identical content previously ingested for this URL (Duplicate Check)
        if prior_record and prior_record.sha256 == sha256_hash:
            logger.info(
                f"[IMMUTABLE] Duplicate document detected for URL: '{source_url}'. "
                f"SHA-256 matches version {prior_record.version} ({sha256_hash[:10]}...). "
                f"Preserving original file without duplicate storage."
            )
            updated_manifest = self.manifest_manager.record_duplicate_check(
                sha256=sha256_hash,
                source_url=source_url,
            ) or prior_record

            doc_record = prepare_document_record(
                title=title,
                source_url=source_url,
                target_domain=target_domain,
                mime_type=detection.mime_type,
                file_size=file_size,
                sha256=sha256_hash,
                storage_path=prior_record.storage_path,
                source_id=source_id,
                scheme_id=scheme_id,
                document_type=document_type,
                language=language,
                requires_ocr=detection.requires_ocr,
                scraped_at=scraped_at,
                published_at=published_at,
                is_active=True,
                version=prior_record.version,
                previous_sha256=prior_record.previous_sha256,
                is_current=True,
            )

            return IngestionResult(
                sha256=sha256_hash,
                file_size=file_size,
                mime_type=detection.mime_type,
                extension=detection.extension,
                requires_ocr=detection.requires_ocr,
                storage_path=prior_record.storage_path,
                manifest_record=updated_manifest,
                document_db_record=doc_record,
                detection_method=detection.detection_method,
                version=prior_record.version,
                is_duplicate=True,
                staged_local_path=None,
                processing_status="duplicate_preserved",
            )

        # Case B: Updated version published by the government source
        if prior_record and prior_record.sha256 != sha256_hash:
            new_version = prior_record.version + 1
            previous_sha = prior_record.sha256
            previous_path = prior_record.storage_path

            logger.info(
                f"[VERSIONING] Official source update detected for URL: '{source_url}'. "
                f"Transitioning v{prior_record.version} ({previous_sha[:8]}...) -> "
                f"v{new_version} ({sha256_hash[:8]}...). Original file preserved permanently."
            )

            # Deprecate prior current flag in manifest
            self.manifest_manager.deprecate_previous_version(source_url)

            # Generate distinct deterministic cloud storage path for the new version
            new_storage_path = generate_storage_path(
                domain=target_domain,
                source_id=source_id,
                sha256=sha256_hash,
                extension=detection.extension,
            )

            manifest_record = ManifestRecord(
                source_url=source_url,
                source_id=source_id,
                title=title,
                target_domain=target_domain,
                language=language,
                mime_type=detection.mime_type,
                file_size=file_size,
                sha256=sha256_hash,
                requires_ocr=detection.requires_ocr,
                scraped_at=scraped_at,
                storage_path=new_storage_path,
                processing_status="staged",
                version=new_version,
                previous_sha256=previous_sha,
                previous_storage_path=previous_path,
                is_current=True,
            )
            self.manifest_manager.append_record(manifest_record)

            staged_path = None
            if stage_locally:
                target_dir = self.ocr_staging_dir if detection.requires_ocr else self.local_staging_dir
                os.makedirs(target_dir, exist_ok=True)
                staged_path = os.path.join(target_dir, f"{sha256_hash}{detection.extension}")
                if not os.path.exists(staged_path):
                    with open(staged_path, "wb") as f:
                        f.write(content)

            doc_record = prepare_document_record(
                title=title,
                source_url=source_url,
                target_domain=target_domain,
                mime_type=detection.mime_type,
                file_size=file_size,
                sha256=sha256_hash,
                storage_path=new_storage_path,
                source_id=source_id,
                scheme_id=scheme_id,
                document_type=document_type,
                language=language,
                requires_ocr=detection.requires_ocr,
                scraped_at=scraped_at,
                published_at=published_at,
                is_active=True,
                version=new_version,
                previous_sha256=previous_sha,
                is_current=True,
            )

            return IngestionResult(
                sha256=sha256_hash,
                file_size=file_size,
                mime_type=detection.mime_type,
                extension=detection.extension,
                requires_ocr=detection.requires_ocr,
                storage_path=new_storage_path,
                manifest_record=manifest_record,
                document_db_record=doc_record,
                detection_method=detection.detection_method,
                version=new_version,
                is_duplicate=False,
                staged_local_path=staged_path,
                processing_status="staged",
            )

        # Case C: First-time document ingestion (Version 1)
        # Check global SHA-256 uniqueness across other URLs if duplicates disallowed
        if not allow_duplicates and self.manifest_manager:
            if self.manifest_manager.has_sha256(sha256_hash):
                logger.warning(
                    f"Duplicate SHA-256 detected under different URL: {sha256_hash}"
                )
                raise DuplicateDocumentError(sha256_hash)

        storage_path = generate_storage_path(
            domain=target_domain,
            source_id=source_id,
            sha256=sha256_hash,
            extension=detection.extension,
        )

        manifest_record = ManifestRecord(
            source_url=source_url,
            source_id=source_id,
            title=title,
            target_domain=target_domain,
            language=language,
            mime_type=detection.mime_type,
            file_size=file_size,
            sha256=sha256_hash,
            requires_ocr=detection.requires_ocr,
            scraped_at=scraped_at,
            storage_path=storage_path,
            processing_status="staged",
            version=1,
            previous_sha256=None,
            is_current=True,
        )

        if self.manifest_manager:
            self.manifest_manager.append_record(manifest_record)

        staged_path = None
        if stage_locally:
            target_dir = self.ocr_staging_dir if detection.requires_ocr else self.local_staging_dir
            os.makedirs(target_dir, exist_ok=True)
            staged_path = os.path.join(target_dir, f"{sha256_hash}{detection.extension}")
            if not os.path.exists(staged_path):
                with open(staged_path, "wb") as f:
                    f.write(content)

        doc_record = prepare_document_record(
            title=title,
            source_url=source_url,
            target_domain=target_domain,
            mime_type=detection.mime_type,
            file_size=file_size,
            sha256=sha256_hash,
            storage_path=storage_path,
            source_id=source_id,
            scheme_id=scheme_id,
            document_type=document_type,
            language=language,
            requires_ocr=detection.requires_ocr,
            scraped_at=scraped_at,
            published_at=published_at,
            is_active=True,
            version=1,
            previous_sha256=None,
            is_current=True,
        )

        logger.info(
            f"Successfully ingested initial v1 document: '{title[:40]}' -> "
            f"sha256={sha256_hash[:10]}..., path={storage_path}"
        )

        return IngestionResult(
            sha256=sha256_hash,
            file_size=file_size,
            mime_type=detection.mime_type,
            extension=detection.extension,
            requires_ocr=detection.requires_ocr,
            storage_path=storage_path,
            manifest_record=manifest_record,
            document_db_record=doc_record,
            detection_method=detection.detection_method,
            version=1,
            is_duplicate=False,
            staged_local_path=staged_path,
            processing_status="staged",
        )

    def ingest_file(
        self,
        file_path: str,
        source_url: str,
        target_domain: str,
        title: str,
        source_id: Optional[str] = None,
        scheme_id: Optional[str] = None,
        language: str = "en",
        document_type: str = "guideline",
        allow_duplicates: bool = False,
        stage_locally: bool = False,
        published_at: Optional[str] = None,
    ) -> IngestionResult:
        """
        Ingests document from a local filesystem file.
        """
        if not os.path.exists(file_path):
            raise CorruptedFileError(f"File does not exist: '{file_path}'")

        file_size = os.path.getsize(file_path)
        validate_file_size(file_size)

        with open(file_path, "rb") as f:
            content = f.read()

        return self.ingest_bytes(
            content=content,
            source_url=source_url,
            target_domain=target_domain,
            title=title,
            filename_hint=os.path.basename(file_path),
            source_id=source_id,
            scheme_id=scheme_id,
            language=language,
            document_type=document_type,
            allow_duplicates=allow_duplicates,
            stage_locally=stage_locally,
            published_at=published_at,
        )
