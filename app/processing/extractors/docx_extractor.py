"""
NEXO Data Platform - DOCX Document Extractor
Extracts paragraphs and structured table content from DOCX files.
Uses python-docx with pure Python zipfile/xml fallback for zero-failure resilience.
"""

import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from app.processing.extractors.base import BaseExtractor
from config.logging_config import get_logger

logger = get_logger("processing.docx")

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


class DOCXExtractor(BaseExtractor):
    """Extracts text and table content from Microsoft Word DOCX files."""

    @property
    def extractor_name(self) -> str:
        return "python_docx_extractor" if DOCX_AVAILABLE else "zipfile_xml_docx_extractor"

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
                error_message="DOCX file bytes are empty.",
            )

        try:
            if DOCX_AVAILABLE:
                text = self._extract_with_docx(file_bytes)
            else:
                text = self._extract_with_zipfile(file_bytes)

            text = text.strip()
            char_count = len(text)
            words = text.split()
            word_count = len(words)

            if char_count == 0:
                status = ExtractionStatus.EXTRACTION_FAILED
            elif char_count < 100:
                status = ExtractionStatus.LOW_TEXT
            else:
                status = ExtractionStatus.SUCCESS

            return ExtractionResult(
                text=text,
                page_count=None,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.extractor_name,
                status=status,
            )

        except Exception as exc:
            # Try fallback to zipfile if docx failed
            if DOCX_AVAILABLE:
                try:
                    text = self._extract_with_zipfile(file_bytes)
                    text = text.strip()
                    char_count = len(text)
                    return ExtractionResult(
                        text=text,
                        page_count=None,
                        character_count=char_count,
                        word_count=len(text.split()),
                        extraction_method="zipfile_xml_docx_extractor",
                        status=ExtractionStatus.SUCCESS if char_count >= 100 else ExtractionStatus.LOW_TEXT,
                    )
                except Exception:
                    pass

            logger.error(f"DOCX extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.extractor_name,
                error_code="DOCX_PARSE_ERROR",
                error_message=str(exc),
            )

    def _extract_with_docx(self, file_bytes: bytes) -> str:
        stream = io.BytesIO(file_bytes)
        doc = docx.Document(stream)
        lines = []

        # Extract paragraphs
        for p in doc.paragraphs:
            p_text = p.text.strip()
            if p_text:
                lines.append(p_text)

        # Extract tables
        for table in doc.tables:
            lines.append("--- [Table] ---")
            for row in table.rows:
                row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells if cell.text.strip()]
                if row_cells:
                    lines.append(" | ".join(row_cells))
            lines.append("--- [End Table] ---")

        return "\n\n".join(lines)

    def _extract_with_zipfile(self, file_bytes: bytes) -> str:
        stream = io.BytesIO(file_bytes)
        with zipfile.ZipFile(stream) as zf:
            xml_content = zf.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Namespace for WordprocessingML
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for p in tree.findall(".//w:p", ns):
                texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
                if texts:
                    paragraphs.append("".join(texts).strip())
            return "\n\n".join(paragraphs)
