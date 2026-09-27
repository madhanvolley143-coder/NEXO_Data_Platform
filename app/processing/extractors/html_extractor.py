"""
NEXO Data Platform - HTML Content Extractor
Extracts clean content from HTML files, stripping navigation, headers, footers,
scripts, and styling boilerplate while preserving reading hierarchy.
"""

import re
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from app.processing.extractors.base import BaseExtractor
from config.logging_config import get_logger

logger = get_logger("processing.html")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


class HTMLExtractor(BaseExtractor):
    """Extracts clean text content from HTML documents."""

    @property
    def extractor_name(self) -> str:
        return "bs4_html_extractor" if BS4_AVAILABLE else "regex_html_extractor"

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
                error_message="HTML file bytes are empty.",
            )

        # Decode content with UTF-8 / fallback
        html_str = ""
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                html_str = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not html_str:
            html_str = file_bytes.decode("utf-8", errors="replace")

        try:
            if BS4_AVAILABLE:
                text = self._extract_with_bs4(html_str)
            else:
                text = self._extract_with_regex(html_str)

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
                page_count=1,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.extractor_name,
                status=status,
            )

        except Exception as exc:
            logger.error(f"HTML extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.extractor_name,
                error_code="HTML_PARSE_ERROR",
                error_message=str(exc),
            )

    def _extract_with_bs4(self, html_str: str) -> str:
        soup = BeautifulSoup(html_str, "html.parser")

        # Decompose non-content elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript", "svg"]):
            tag.decompose()

        # Extract text with linebreaks
        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive newlines
        return re.sub(r"\n{3,}", "\n\n", text)

    def _extract_with_regex(self, html_str: str) -> str:
        # Strip script and style blocks
        clean = re.sub(r"<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", "", html_str, flags=re.DOTALL | re.IGNORECASE)
        # Strip all HTML tags
        clean = re.sub(r"<[^>]+>", " ", clean)
        # Normalize whitespace
        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        return "\n".join(lines)
