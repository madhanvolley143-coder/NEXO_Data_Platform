"""
NEXO Data Platform - Extractor Registry & Factory
Resolves the appropriate content extractor for a document based on file extension and MIME type.
"""

import os
from typing import Optional, Dict
from app.processing.extractors.base import BaseExtractor
from app.processing.extractors.pdf_extractor import PDFExtractor
from app.processing.extractors.html_extractor import HTMLExtractor
from app.processing.extractors.docx_extractor import DOCXExtractor
from app.processing.extractors.csv_extractor import CSVExtractor
from app.processing.extractors.json_xml_extractor import JSONExtractor, XMLExtractor
from app.processing.extractors.txt_extractor import TXTExtractor
from app.processing.extractors.image_extractor import ImageExtractor
from app.processing.ocr.adapter import OCRAdapter


class ExtractorRegistry:
    """Registry maintaining extractor singletons and dispatch logic."""

    def __init__(self, ocr_adapter: Optional[OCRAdapter] = None):
        self.ocr_adapter = ocr_adapter or OCRAdapter()
        self.pdf_extractor = PDFExtractor()
        self.html_extractor = HTMLExtractor()
        self.docx_extractor = DOCXExtractor()
        self.csv_extractor = CSVExtractor()
        self.json_extractor = JSONExtractor()
        self.xml_extractor = XMLExtractor()
        self.txt_extractor = TXTExtractor()
        self.image_extractor = ImageExtractor(ocr_adapter=self.ocr_adapter)

    def get_extractor(
        self,
        extension: Optional[str] = None,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> BaseExtractor:
        """Returns the appropriate extractor based on extension, filename, or MIME type."""
        ext = (extension or "").lower().strip()
        if not ext and filename:
            ext = os.path.splitext(filename)[1].lower().strip()

        mime = (mime_type or "").lower().strip()

        # 1. PDF
        if ext == ".pdf" or "pdf" in mime:
            return self.pdf_extractor

        # 2. HTML
        if ext in (".html", ".htm") or "html" in mime:
            return self.html_extractor

        # 3. DOCX
        if ext in (".docx", ".doc") or "wordprocessingml" in mime:
            return self.docx_extractor

        # 4. CSV
        if ext == ".csv" or "csv" in mime:
            return self.csv_extractor

        # 5. JSON
        if ext == ".json" or "json" in mime:
            return self.json_extractor

        # 6. XML
        if ext == ".xml" or "xml" in mime:
            return self.xml_extractor

        # 7. Images
        if ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp") or "image" in mime:
            return self.image_extractor

        # 8. Plain text fallback
        return self.txt_extractor
