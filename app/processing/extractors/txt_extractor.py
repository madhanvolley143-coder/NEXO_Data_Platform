"""
NEXO Data Platform - Plaintext Document Extractor
Extracts text directly from plaintext files with multi-encoding fallback support.
"""

from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from app.processing.extractors.base import BaseExtractor
from config.logging_config import get_logger

logger = get_logger("processing.txt")


class TXTExtractor(BaseExtractor):
    """Extracts text directly from plaintext documents."""

    @property
    def extractor_name(self) -> str:
        return "direct_plaintext_extractor"

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
                error_code="EMPTY_FILE",
                error_message="Text file bytes are empty.",
            )

        decoded_text = ""
        for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
            try:
                decoded_text = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not decoded_text:
            decoded_text = file_bytes.decode("utf-8", errors="replace")

        text = decoded_text.strip()
        char_count = len(text)
        words = text.split()
        word_count = len(words)

        if char_count == 0:
            status = ExtractionStatus.EXTRACTION_FAILED
        elif char_count < 50:
            status = ExtractionStatus.LOW_TEXT
        else:
            status = ExtractionStatus.SUCCESS

        return ExtractionResult(
            text=text,
            page_count=1,
            character_count=char_count,
            word_count=word_count,
            extraction_method=self.extractor_name,
            status=status,
        )
