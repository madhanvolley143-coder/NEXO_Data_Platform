"""
NEXO Data Platform - Document Discovery Engine
Extracts hyperlinks from official government HTML pages using standard-library HTMLParser,
identifies target document formats, resolves relative URLs, and limits crawl depth.
"""

import os
from html.parser import HTMLParser
from typing import List, Tuple, Set, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

from app.sources.validator import normalize_url
from app.collector.security import validate_crawl_target

# Supported document and data extensions
TARGET_DOCUMENT_EXTENSIONS: Set[str] = {
    ".pdf", ".docx", ".doc", ".txt", ".rtf",
    ".csv", ".json", ".xml", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif",
}


class HtmlLinkExtractor(HTMLParser):
    """
    Standard library HTML parser extracting hyperlinks and their anchor texts.
    No third-party dependencies required.
    """

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: List[Tuple[str, str]] = []  # (absolute_url, anchor_text)
        self._current_tag: Optional[str] = None
        self._current_href: Optional[str] = None
        self._current_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        if tag_lower == "a":
            self._current_tag = "a"
            self._current_text = []
            for attr, val in attrs:
                if attr.lower() == "href" and val:
                    self._current_href = val.strip()
                    break
        elif tag_lower in ("iframe", "embed", "object"):
            for attr, val in attrs:
                if attr.lower() in ("src", "data") and val:
                    resolved = urljoin(self.base_url, val.strip())
                    self.links.append((resolved, tag_lower))
                    break

    def handle_data(self, data: str):
        if self._current_tag == "a":
            self._current_text.append(data.strip())

    def handle_endtag(self, tag: str):
        if tag.lower() == "a" and self._current_href:
            anchor_text = " ".join(self._current_text).strip()
            resolved = urljoin(self.base_url, self._current_href)
            self.links.append((resolved, anchor_text))
            self._current_tag = None
            self._current_href = None
            self._current_text = []


def is_document_url(url: str) -> bool:
    """Checks if a URL points directly to a document/data file based on its extension."""
    parsed = urlparse(url.lower())
    path = parsed.path
    return any(path.endswith(ext) for ext in TARGET_DOCUMENT_EXTENSIONS)


def extract_links_from_html(
    base_url: str,
    html_content: str,
    source_url: str,
) -> List[Tuple[str, str, bool]]:
    """
    Extracts, normalizes, and filters links from HTML.
    Returns: List of (canonical_url, anchor_text, is_document)
    """
    extractor = HtmlLinkExtractor(base_url)
    try:
        extractor.feed(html_content)
    except Exception:
        # Gracefully handle malformed HTML
        pass

    results: List[Tuple[str, str, bool]] = []
    seen = set()

    for raw_url, anchor_text in extractor.links:
        # Filter and validate against source domain
        if not validate_crawl_target(raw_url, source_url):
            continue

        try:
            canonical = normalize_url(raw_url)
        except Exception:
            continue

        if canonical in seen:
            continue
        seen.add(canonical)

        is_doc = is_document_url(canonical)
        results.append((canonical, anchor_text, is_doc))

    return results
