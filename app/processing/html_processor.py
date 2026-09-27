"""
NEXO Data Platform - HTML Document Processor
Extracts semantic text from HTML pages using BeautifulSoup4.
Strips boilerplate tags (scripts, styling, navigation, headers, footers)
and isolates body/article content.
"""

import re
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from config.logging_config import get_logger

logger = get_logger("processing.html")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


class HTMLProcessor:
    """Extracts clean text content from HTML documents."""

    @property
    def processor_name(self) -> str:
        return "bs4_html_processor"

    @property
    def extractor_name(self) -> str:
        return self.processor_name

    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        if not BS4_AVAILABLE:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="DEPENDENCY_MISSING",
                error_message="beautifulsoup4 is not installed in the environment.",
            )

        if not file_bytes:
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="EMPTY_FILE",
                error_message="HTML file bytes are empty.",
            )

        try:
            # Decode HTML with encoding fallback
            try:
                html_str = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                html_str = file_bytes.decode("latin-1", errors="replace")

            soup = BeautifulSoup(html_str, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
                tag.decompose()

            # Extract title if present
            title_text = ""
            if soup.title and soup.title.string:
                title_text = soup.title.string.strip()

            # Locate main content container if available
            main_content = soup.find("main") or soup.find("article") or soup.find("div", {"id": re.compile(r"content|main", re.I)})
            target = main_content if main_content else soup.body or soup

            # Extract text separated by newlines
            raw_text = target.get_text(separator="\n", strip=True)

            # Normalize multiple consecutive blank lines
            clean_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

            if title_text and not clean_text.startswith(title_text):
                clean_text = f"Title: {title_text}\n\n{clean_text}"

            char_count = len(clean_text)
            words = clean_text.split()
            word_count = len(words)

            status = ExtractionStatus.SUCCESS
            if char_count == 0:
                status = ExtractionStatus.LOW_TEXT
            elif char_count < 100:
                status = ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=clean_text,
                page_count=1,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.processor_name,
                status=status,
                requires_ocr=False,
                metadata={
                    "extracted_title": title_text,
                    "has_main_container": bool(main_content),
                },
            )

        except Exception as exc:
            logger.error(f"HTML extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.processor_name,
                error_code="HTML_PARSE_ERROR",
                error_message=str(exc),
            )


# Backward-compatible alias
HTMLExtractor = HTMLProcessor
