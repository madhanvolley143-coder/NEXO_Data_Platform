"""
NEXO Data Platform - Structured & Plaintext Document Processor
Handles CSV, JSON, XML, and plain TXT document processing with robust encoding detection.
"""

import io
import csv
import json
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from config.logging_config import get_logger

logger = get_logger("processing.structured")


class CSVProcessor:
    """Extracts tabular text from CSV data."""

    @property
    def processor_name(self) -> str:
        return "csv_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="EMPTY_FILE",
                error_message="CSV file bytes are empty.",
            )

        try:
            try:
                content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = file_bytes.decode("latin-1", errors="replace")

            reader = csv.reader(io.StringIO(content))
            rows = [row for row in reader if any(cell.strip() for cell in row)]

            if not rows:
                return ExtractionResult(
                    status=ExtractionStatus.LOW_TEXT,
                    extraction_method=self.processor_name,
                    text="",
                    character_count=0,
                    word_count=0,
                )

            headers = rows[0]
            header_str = "Table Headers: " + ", ".join(headers)
            body_rows = [" | ".join(r) for r in rows[1:]]

            full_text = f"{header_str}\n\n" + "\n".join(body_rows)
            char_count = len(full_text)
            words = full_text.split()
            word_count = len(words)

            status = ExtractionStatus.SUCCESS if word_count >= 10 else ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=full_text,
                page_count=1,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.processor_name,
                status=status,
                requires_ocr=False,
                metadata={
                    "total_rows": len(rows),
                    "column_count": len(headers),
                },
            )

        except Exception as exc:
            logger.error(f"CSV extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="CSV_PARSE_ERROR",
                error_message=str(exc),
            )


class JSONProcessor:
    """Extracts structured text from JSON data."""

    @property
    def processor_name(self) -> str:
        return "json_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="EMPTY_FILE",
                error_message="JSON file bytes are empty.",
            )

        try:
            try:
                content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = file_bytes.decode("latin-1", errors="replace")

            parsed = json.loads(content)

            def flatten_json(obj: Any) -> list:
                texts = []
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        texts.append(f"{k}:")
                        texts.extend(flatten_json(v))
                elif isinstance(obj, list):
                    for item in obj:
                        texts.extend(flatten_json(item))
                elif obj is not None:
                    texts.append(str(obj))
                return texts

            flat_lines = flatten_json(parsed)
            full_text = "\n".join(flat_lines).strip()
            char_count = len(full_text)
            words = full_text.split()
            word_count = len(words)

            status = ExtractionStatus.SUCCESS if word_count >= 5 else ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=full_text,
                page_count=1,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.processor_name,
                status=status,
                requires_ocr=False,
                metadata={"json_type": type(parsed).__name__},
            )

        except Exception as exc:
            logger.error(f"JSON extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="JSON_PARSE_ERROR",
                error_message=str(exc),
            )


class XMLProcessor:
    """Extracts structured text from XML documents."""

    @property
    def processor_name(self) -> str:
        return "xml_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="EMPTY_FILE",
                error_message="XML file bytes are empty.",
            )

        try:
            root = ET.fromstring(file_bytes)
            texts = []
            for elem in root.iter():
                t = (elem.text or "").strip()
                if t:
                    texts.append(t)

            full_text = "\n".join(texts).strip()
            char_count = len(full_text)
            words = full_text.split()
            word_count = len(words)

            status = ExtractionStatus.SUCCESS if word_count >= 5 else ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=full_text,
                page_count=1,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.processor_name,
                status=status,
                requires_ocr=False,
                metadata={"root_tag": root.tag},
            )

        except Exception as exc:
            logger.error(f"XML extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="XML_PARSE_ERROR",
                error_message=str(exc),
            )


class TXTProcessor:
    """Extracts plaintext with robust encoding fallbacks."""

    @property
    def processor_name(self) -> str:
        return "txt_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="EMPTY_FILE",
                error_message="TXT file bytes are empty.",
            )

        text = None
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            text = file_bytes.decode("utf-8", errors="replace")

        clean_text = text.strip()
        char_count = len(clean_text)
        words = clean_text.split()
        word_count = len(words)

        status = ExtractionStatus.SUCCESS
        if char_count == 0:
            status = ExtractionStatus.LOW_TEXT
        elif char_count < 50:
            status = ExtractionStatus.LOW_TEXT

        return ExtractionResult(
            text=clean_text,
            page_count=1,
            character_count=char_count,
            word_count=word_count,
            extraction_method=self.processor_name,
            status=status,
            requires_ocr=False,
        )


class StructuredProcessor:
    """
    Unified processor dispatching CSV, JSON, XML, and TXT documents.
    """

    def __init__(self):
        self.csv_proc = CSVProcessor()
        self.json_proc = JSONProcessor()
        self.xml_proc = XMLProcessor()
        self.txt_proc = TXTProcessor()

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        fn = (filename or "").lower()
        if fn.endswith(".csv"):
            return self.csv_proc.extract(file_bytes, filename, metadata)
        elif fn.endswith(".json"):
            return self.json_proc.extract(file_bytes, filename, metadata)
        elif fn.endswith(".xml"):
            return self.xml_proc.extract(file_bytes, filename, metadata)
        else:
            return self.txt_proc.extract(file_bytes, filename, metadata)


# Backward-compatible aliases
CSVExtractor = CSVProcessor
JSONExtractor = JSONProcessor
XMLExtractor = XMLProcessor
TXTExtractor = TXTProcessor
