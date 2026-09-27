"""
NEXO Data Platform - Text Quality Validator
Performs text quality checks, density analysis, printable character checks,
and status classification across all extracted documents.
Ensures no document is ever silently discarded.
"""

from typing import Dict, Any, Optional, Tuple
from app.processing.models import (
    ExtractionResult,
    ExtractionStatus,
    TextQualityStatus,
)
from config.logging_config import get_logger

logger = get_logger("processing.quality")


class TextQualityValidator:
    """Validates extracted text quality and classifies document status."""

    def validate(
        self,
        extraction_result: ExtractionResult,
        declared_language: Optional[str] = "en",
        raw_file_size: int = 0,
        initial_requires_ocr: bool = False,
    ) -> Tuple[ExtractionStatus, TextQualityStatus, Dict[str, Any]]:
        """
        Evaluates extraction output and returns:
        (final_extraction_status, text_quality_status, validation_metrics)
        """
        text = extraction_result.text or ""
        char_count = len(text)
        words = text.split()
        word_count = len(words)
        page_count = extraction_result.page_count

        # 1. Printable character ratio check
        printable_count = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
        printable_ratio = (printable_count / char_count) if char_count > 0 else 1.0

        # 2. Quality tier assessment
        if char_count == 0:
            quality = TextQualityStatus.EMPTY
        elif printable_ratio < 0.70:
            quality = TextQualityStatus.CORRUPT
        elif word_count < 30:
            quality = TextQualityStatus.LOW
        elif word_count < 100:
            quality = TextQualityStatus.MEDIUM
        else:
            quality = TextQualityStatus.HIGH

        # 3. Final extraction status classification:
        # SUCCESS, OCR_REQUIRED, LOW_TEXT, EXTRACTION_FAILED, NEEDS_REVIEW
        if extraction_result.status == ExtractionStatus.EXTRACTION_FAILED:
            final_status = ExtractionStatus.EXTRACTION_FAILED
        elif quality == TextQualityStatus.CORRUPT:
            final_status = ExtractionStatus.NEEDS_REVIEW
        elif extraction_result.requires_ocr or initial_requires_ocr:
            final_status = ExtractionStatus.OCR_REQUIRED
        elif char_count == 0:
            final_status = ExtractionStatus.LOW_TEXT
        elif word_count < 15 and raw_file_size > 50000:
            # Substantial file size but almost no text (e.g. scanned PDF with single-word banner)
            final_status = ExtractionStatus.OCR_REQUIRED
        elif word_count < 25:
            final_status = ExtractionStatus.LOW_TEXT
        else:
            final_status = ExtractionStatus.SUCCESS

        metrics = {
            "character_count": char_count,
            "word_count": word_count,
            "page_count": page_count,
            "printable_ratio": round(printable_ratio, 4),
            "quality_tier": quality.value,
            "detected_language": declared_language or "en",
            "is_empty": (char_count == 0),
            "is_near_empty": (0 < word_count < 25),
        }

        return final_status, quality, metrics


# Backward-compatible alias
TextQualityChecker = TextQualityValidator
