"""
NEXO Data Platform - OCR Document Processor & Routing
Handles images (PNG, JPG, JPEG) and scanned PDF documents requiring OCR.
Strictly conforms to data safety:
- Never invents or hallucinates OCR text if the engine is unavailable.
- Records OCR_REQUIRED or OCR_FAILED safely.
"""

from typing import Dict, Any, Optional
from app.processing.models import (
    ExtractionResult,
    ExtractionStatus,
    OCRResult,
    OCRStatus,
)
from app.processing.ocr.adapter import OCRAdapter, NoOpOCREngine, MockOCREngine
from config.logging_config import get_logger

logger = get_logger("processing.ocr")


class OCRProcessor:
    """
    Image and scanned document processor with safe OCR routing.
    Routes to configured OCR engine without guessing or hallucinating missing text.
    """

    def __init__(self, adapter: Optional[OCRAdapter] = None):
        self.adapter = adapter or OCRAdapter()

    @property
    def processor_name(self) -> str:
        return "ocr_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def is_engine_available(self) -> bool:
        """Returns True if a functional OCR engine is attached and ready."""
        return self.adapter.is_available()

    def process_ocr(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        language_hint: Optional[str] = "en",
    ) -> OCRResult:
        """
        Executes OCR if available. If unavailable, records status safely without inventing text.
        """
        if not file_bytes:
            return OCRResult(
                status=OCRStatus.FAILED,
                text="",
                failure_reason="Empty file bytes provided to OCR engine",
            )

        if not self.is_engine_available():
            logger.info(f"No OCR engine configured/available for '{filename}'. Safely recording OCR_REQUIRED.")
            return OCRResult(
                status=OCRStatus.PENDING,
                text="",
                confidence=None,
                language=language_hint,
                failure_reason="OCR engine not installed or unavailable in current environment",
            )

        try:
            return self.adapter.process(
                file_bytes=file_bytes,
                filename=filename,
                language_hint=language_hint,
            )
        except Exception as exc:
            logger.error(f"OCR execution failed on '{filename}': {exc}")
            return OCRResult(
                status=OCRStatus.FAILED,
                text="",
                failure_reason=str(exc),
            )

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """
        Processes image or scanned input, setting requires_ocr=True and calling OCR safely.
        """
        fn = filename or "image_document.png"
        meta = metadata or {}
        lang_hint = meta.get("language") or "en"

        ocr_res = self.process_ocr(
            file_bytes=file_bytes,
            filename=fn,
            language_hint=lang_hint,
        )

        if ocr_res.status == OCRStatus.COMPLETED and ocr_res.text.strip():
            txt = ocr_res.text.strip()
            char_count = len(txt)
            word_count = len(txt.split())
            status = ExtractionStatus.SUCCESS if word_count >= 10 else ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=txt,
                page_count=1,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.processor_name,
                status=status,
                requires_ocr=True,
                metadata={
                    "ocr_status": OCRStatus.COMPLETED.value,
                    "ocr_confidence": ocr_res.confidence,
                    "ocr_language": ocr_res.language or lang_hint,
                    "media_type": "image",
                },
            )

        # Engine unavailable or failed -> Safely record OCR_REQUIRED or OCR_FAILED without inventing text
        final_status = ExtractionStatus.OCR_REQUIRED if ocr_res.status in (OCRStatus.PENDING, OCRStatus.NOT_REQUIRED) else ExtractionStatus.EXTRACTION_FAILED

        return ExtractionResult(
            text="",
            page_count=1,
            character_count=0,
            word_count=0,
            extraction_method=self.processor_name,
            status=final_status,
            requires_ocr=True,
            error_code="OCR_REQUIRED" if final_status == ExtractionStatus.OCR_REQUIRED else "OCR_FAILED",
            error_message=ocr_res.failure_reason or "Document requires OCR extraction.",
            metadata={
                "ocr_status": ocr_res.status.value,
                "ocr_failure_reason": ocr_res.failure_reason,
                "media_type": "image",
            },
        )


# Backward-compatible alias
ImageExtractor = OCRProcessor
