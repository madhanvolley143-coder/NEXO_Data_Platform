"""
NEXO Data Platform - DOCX Document Processor
Extracts paragraphs, headings, and tables from Word (.docx) documents using python-docx.
"""

import io
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from config.logging_config import get_logger

logger = get_logger("processing.docx")

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


class DOCXProcessor:
    """Extracts text, headings, and tables from DOCX files."""

    @property
    def processor_name(self) -> str:
        return "python_docx_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not DOCX_AVAILABLE:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="DEPENDENCY_MISSING",
                error_message="python-docx is not installed in the environment.",
            )

        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="EMPTY_FILE",
                error_message="DOCX file bytes are empty.",
            )

        try:
            stream = io.BytesIO(file_bytes)
            doc = docx.Document(stream)

            parts = []
            for p in doc.paragraphs:
                text = p.text.strip()
                if text:
                    parts.append(text)

            # Extract tables
            for t_idx, table in enumerate(doc.tables, 1):
                table_rows = []
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        table_rows.append(" | ".join(cells))
                if table_rows:
                    parts.append(f"\n--- [Table {t_idx}] ---\n" + "\n".join(table_rows))

            full_text = "\n\n".join(parts).strip()
            char_count = len(full_text)
            words = full_text.split()
            word_count = len(words)

            status = ExtractionStatus.SUCCESS
            if char_count == 0:
                status = ExtractionStatus.LOW_TEXT
            elif char_count < 100:
                status = ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=full_text,
                page_count=None,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.processor_name,
                status=status,
                requires_ocr=False,
                metadata={
                    "paragraph_count": len(doc.paragraphs),
                    "table_count": len(doc.tables),
                },
            )

        except Exception as exc:
            logger.error(f"DOCX extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="DOCX_PARSE_ERROR",
                error_message=str(exc),
            )


# Backward-compatible alias
DOCXExtractor = DOCXProcessor
