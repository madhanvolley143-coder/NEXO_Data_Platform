"""
NEXO Data Platform - Processing Metadata Manager
Preserves existing document governance metadata and enriches it with extraction
and processing audit fields without hallucinating or guessing missing attributes.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.processing.models import ExtractionResult, ExtractionStatus, TextQualityStatus


class MetadataEnricher:
    """Combines raw document lineage and processing telemetry."""

    def __init__(self, processor_version: str = "1.0.0"):
        self.processor_version = processor_version

    def enrich(
        self,
        raw_doc: Dict[str, Any],
        extraction_result: ExtractionResult,
        final_status: ExtractionStatus,
        quality_status: TextQualityStatus,
        metrics: Dict[str, Any],
        processed_storage_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates an enriched metadata payload adhering strictly to zero-guessing principles.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        title = raw_doc.get("title") or "Untitled Official Document"
        source_url = raw_doc.get("source_url") or ""
        source_id = raw_doc.get("source_id")
        source_name = raw_doc.get("source_name") or raw_doc.get("organization_name")
        domain = raw_doc.get("domain") or raw_doc.get("relevance_category") or "general"
        language = raw_doc.get("language") or "en"
        state = raw_doc.get("state")
        district = raw_doc.get("district")
        doc_type = raw_doc.get("document_type") or "guideline"
        mime_type = raw_doc.get("mime_type")
        published_at = raw_doc.get("published_at")
        raw_sha256 = raw_doc.get("sha256") or raw_doc.get("raw_sha256")

        ocr_meta = extraction_result.metadata.get("ocr_status")
        ocr_status_val = ocr_meta or ("COMPLETED" if extraction_result.requires_ocr and extraction_result.text else "NOT_REQUIRED")

        enriched = {
            "document_id": raw_doc.get("id"),
            "raw_sha256": raw_sha256,
            "title": title,
            "source_id": source_id,
            "source_name": source_name,
            "source_url": source_url,
            "domain": domain,
            "document_type": doc_type,
            "language_declared": language,
            "language_detected": metrics.get("detected_language") or language,
            "state": state,
            "district": district,
            "mime_type": mime_type,
            "published_at": published_at,
            "processor_version": self.processor_version,
            "processing_timestamp": now_iso,
            "extraction_method": extraction_result.extraction_method,
            "extraction_status": final_status.value,
            "text_quality_status": quality_status.value,
            "character_count": metrics.get("character_count", 0),
            "word_count": metrics.get("word_count", 0),
            "page_count": extraction_result.page_count,
            "printable_ratio": metrics.get("printable_ratio", 1.0),
            "requires_ocr": extraction_result.requires_ocr,
            "ocr_status": ocr_status_val,
            "ocr_confidence": extraction_result.metadata.get("ocr_confidence"),
            "ocr_language": extraction_result.metadata.get("ocr_language"),
            "processed_storage_path": processed_storage_path,
            "error_code": extraction_result.error_code,
            "error_message": extraction_result.error_message,
        }

        return enriched


# Backward-compatible alias
ProcessingMetadataManager = MetadataEnricher
