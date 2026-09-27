"""
NEXO Data Platform - Image Document Extractor
Routes image files (PNG, JPG, JPEG, TIFF, WEBP) to the OCR adapter.
"""

from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus, OCRStatus
from app.processing.extractors.base import BaseExtractor
from app.processing.ocr.adapter import OCRAdapter
from config.logging_config import get_logger

logger = get_logger("processing.image")


class ImageExtractor(BaseExtractor):
    """Handles image files by delegating to the pluggable OCR adapter."""

    def __init__(self, ocr_adapter: Optional[OCRAdapter] = None):
        self.ocr_adapter = ocr_adapter or OCRAdapter()

    @property
    def extractor_name(self) -> str:
        return f"image_ocr_extractor ({self.ocr_adapter.engine.name})"

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.extractor_name,
                requires_ocr=True,
                error_code="EMPTY_FILE",
                error_message="Image file bytes are empty.",
            )

        lang_hint = (metadata or {}).get("language") or "en"
        ocr_res = self.ocr_adapter.process(
            file_bytes=file_bytes,
            filename=filename,
            language_hint=lang_hint,
        )

        extracted_text = (ocr_res.text or "").strip()
        char_count = len(extracted_text)
        word_count = len(extracted_text.split())

        if ocr_res.status == OCRStatus.COMPLETED and char_count > 0:
            status = ExtractionStatus.SUCCESS
        elif ocr_res.status == OCRStatus.PENDING:
            status = ExtractionStatus.OCR_REQUIRED
        elif ocr_res.status == OCRStatus.FAILED:
            status = ExtractionStatus.EXTRACTION_FAILED
        else:
            status = ExtractionStatus.OCR_REQUIRED

        return ExtractionResult(
            text=extracted_text,
            page_count=1,
            character_count=char_count,
            word_count=word_count,
            extraction_method=self.extractor_name,
            status=status,
            requires_ocr=True,
            metadata={
                "media_type": "image",
                "ocr_status": ocr_res.status.value,
                "ocr_confidence": ocr_res.confidence,
                "ocr_language": ocr_res.language,
                "ocr_failure_reason": ocr_res.failure_reason,
            },
        )
