"""
NEXO Data Platform - JSON and XML Content Extractors
Extracts hierarchical structured data from JSON and XML documents into readable text.
"""

import json
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult, ExtractionStatus
from app.processing.extractors.base import BaseExtractor
from config.logging_config import get_logger

logger = get_logger("processing.structured")


class JSONExtractor(BaseExtractor):
    """Extracts text representation from JSON files."""

    @property
    def extractor_name(self) -> str:
        return "json_structured_extractor"

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
                error_message="JSON file bytes are empty.",
            )

        try:
            raw_text = file_bytes.decode("utf-8")
            data = json.loads(raw_text)

            # Format as clean indented JSON text
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            char_count = len(formatted)
            word_count = len(formatted.split())

            status = ExtractionStatus.SUCCESS if char_count >= 20 else ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=formatted,
                page_count=None,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.extractor_name,
                status=status,
            )
        except Exception as exc:
            logger.error(f"JSON extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.extractor_name,
                error_code="JSON_PARSE_ERROR",
                error_message=str(exc),
            )


class XMLExtractor(BaseExtractor):
    """Extracts text and hierarchical structure from XML files."""

    @property
    def extractor_name(self) -> str:
        return "xml_tree_extractor"

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
                error_message="XML file bytes are empty.",
            )

        try:
            root = ET.fromstring(file_bytes)
            lines = []

            def _traverse(node: ET.Element, depth: int = 0):
                indent = "  " * depth
                tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
                text = (node.text or "").strip()
                attrs = " ".join(f'{k}="{v}"' for k, v in node.attrib.items())
                attr_str = f" [{attrs}]" if attrs else ""

                if text:
                    lines.append(f"{indent}<{tag}{attr_str}>: {text}")
                elif list(node):
                    lines.append(f"{indent}<{tag}{attr_str}>")

                for child in node:
                    _traverse(child, depth + 1)

            _traverse(root)
            full_text = "\n".join(lines).strip()
            char_count = len(full_text)
            word_count = len(full_text.split())

            status = ExtractionStatus.SUCCESS if char_count >= 30 else ExtractionStatus.LOW_TEXT

            return ExtractionResult(
                text=full_text,
                page_count=None,
                character_count=char_count,
                word_count=word_count,
                extraction_method=self.extractor_name,
                status=status,
            )
        except Exception as exc:
            logger.error(f"XML extraction error on '{filename}': {exc}")
            return ExtractionResult(
                status=ExtractionStatus.EXTRACTION_FAILED,
                extraction_method=self.extractor_name,
                error_code="XML_PARSE_ERROR",
                error_message=str(exc),
            )
