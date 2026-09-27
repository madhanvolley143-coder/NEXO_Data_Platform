"""
NEXO Data Platform - PDF Document Processor
Extracts text page-by-page from PDF files using pypdf.
Preserves logical reading order, counts pages, and detects scanned/image-only PDFs.
"""

import io
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from config.logging_config import get_logger

logger = get_logger("processing.pdf")

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


class PDFProcessor:
    """Extracts text and structure from PDF documents."""

    @property
    def processor_name(self) -> str:
        return "pypdf_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not PYPDF_AVAILABLE:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="DEPENDENCY_MISSING",
                error_message="pypdf is not installed in the environment.",
            )

        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="EMPTY_FILE",
                error_message="PDF file bytes are empty.",
            )

        try:
            stream = io.BytesIO(file_bytes)
            reader = pypdf.PdfReader(stream)

            if reader.is_encrypted:
                try:
                    # Attempt decrypt with empty password
                    reader.decrypt("")
                except Exception as dec_exc:
                    return ExtractionResult(
                        status=ExtractionStatus.EXTRACTION_FAILED,
                        extraction_method=self.processor_name,
                        error_code="ENCRYPTED_PDF",
                        error_message=f"PDF is password-encrypted: {dec_exc}",
                    )

            page_count = len(reader.pages)
            extracted_pages = []

            for page_idx, page in enumerate(reader.pages, 1):
                try:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        extracted_pages.append(f"--- [Page {page_idx}] ---\n{page_text.strip()}")
                except Exception as p_exc:
                    logger.debug(f"Failed extracting text from page {page_idx} of '{filename}': {p_exc}")

            full_text = "\n\n".join(extracted_pages).strip()
            char_count = len(full_text)
            words = full_text.split()
            word_count = len(words)

            # Scanned / Image PDF detection:
            # If total text is less than 50 characters or average < 20 chars per page,
            # this PDF is likely an image scan requiring OCR.
            is_scanned = (char_count < 50) or (page_count > 0 and (char_count / page_count) < 20)

            status = ExtractionStatus.SUCCESS
            requires_ocr = False

            if is_scanned:
                status = ExtractionStatus.OCR_REQUIRED
                requires_ocr = True
            elif char_count < 150:
                status = ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=full_text,
                page_count=page_count,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.processor_name,
                status=status,
                requires_ocr=requires_ocr,
                metadata={
                    "page_count": page_count,
                    "is_scanned_pdf": is_scanned,
                },
            )

        except Exception as exc:
            logger.error(f"PDF extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="PDF_PARSE_ERROR",
                error_message=str(exc),
            )


# Backward-compatible alias
PDFExtractor = PDFProcessor
