"""
NEXO Data Platform - CSV Content Extractor
Extracts tabular CSV data into structured, readable text preserving columns and rows.
"""

import csv
import io
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from app.processing.extractors.base import BaseExtractor
from config.logging_config import get_logger

logger = get_logger("processing.csv")


class CSVExtractor(BaseExtractor):
    """Extracts CSV data into structured readable text."""

    @property
    def extractor_name(self) -> str:
        return "csv_tabular_extractor"

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
                error_message="CSV file bytes are empty.",
            )

        # Decode with fallback
        text_content = ""
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                text_content = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not text_content:
            text_content = file_bytes.decode("utf-8", errors="replace")

        try:
            sample = text_content[:2048]
            delimiter = ","
            try:
                dialect = csv.Sniffer().sniff(sample)
                delimiter = dialect.delimiter
            except Exception:
                if "\t" in sample and "," not in sample:
                    delimiter = "\t"
                elif ";" in sample and "," not in sample:
                    delimiter = ";"

            reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
            rows = [r for r in reader if any(field.strip() for field in r)]

            if not rows:
                return ExtractionResult(
                    status=ExtractionStatus.LOW_TEXT,
                    extraction_method=self.extractor_name,
                    character_count=0,
                    word_count=0,
                )

            headers = [h.strip() for h in rows[0]]
            formatted_lines = [f"Table Headers: {', '.join(headers)}", ""]

            for row_idx, row in enumerate(rows[1:], 1):
                cell_pairs = []
                for col_idx, cell in enumerate(row):
                    header = headers[col_idx] if col_idx < len(headers) else f"Col_{col_idx+1}"
                    val = cell.strip()
                    if val:
                        cell_pairs.append(f"{header}={val}")
                if cell_pairs:
                    formatted_lines.append(f"Row {row_idx}: " + " | ".join(cell_pairs))

            full_text = "\n".join(formatted_lines).strip()
            char_count = len(full_text)
            words = full_text.split()
            word_count = len(words)

            status = ExtractionStatus.SUCCESS if char_count >= 50 else ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=full_text,
                page_count=None,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.extractor_name,
                status=status,
                metadata={
                    "total_rows": len(rows),
                    "total_columns": len(headers),
                    "delimiter": delimiter,
                },
            )

        except Exception as exc:
            logger.error(f"CSV extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.extractor_name,
                error_code="CSV_PARSE_ERROR",
                error_message=str(exc),
            )
