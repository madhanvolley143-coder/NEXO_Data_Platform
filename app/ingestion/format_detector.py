"""
NEXO Data Platform - Format & MIME Detector with OCR Heuristics
Inspects file magic bytes and structure to accurately determine MIME type and OCR requirement.
"""

import hashlib
import json
import mimetypes
import os
import re
from typing import Tuple, Optional
from config.storage_config import is_ocr_mime, MIME_TO_EXTENSION_MAP


class FormatDetectionResult:
    """Encapsulates the detected format, MIME type, extension, and OCR requirement."""
    def __init__(
        self,
        mime_type: str,
        extension: str,
        requires_ocr: bool,
        detection_method: str,
    ):
        self.mime_type = mime_type
        self.extension = extension
        self.requires_ocr = requires_ocr
        self.detection_method = detection_method

    def __repr__(self) -> str:
        return (
            f"FormatDetectionResult(mime='{self.mime_type}', ext='{self.extension}', "
            f"requires_ocr={self.requires_ocr}, method='{self.detection_method}')"
        )


def calculate_sha256(content: bytes) -> str:
    """Compute standard SHA-256 hexadecimal checksum for bytes content."""
    hasher = hashlib.sha256()
    hasher.update(content)
    return hasher.hexdigest()


def calculate_file_sha256(file_path: str, chunk_size: int = 65536) -> str:
    """Compute standard SHA-256 hexadecimal checksum for a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_format(
    content: bytes,
    filename_or_url: Optional[str] = None,
) -> FormatDetectionResult:
    """
    Analyzes content header magic bytes to determine MIME type, extension,
    and whether OCR is required.
    """
    if not content:
        return FormatDetectionResult(
            mime_type="application/octet-stream",
            extension=".bin",
            requires_ocr=False,
            detection_method="empty_content",
        )

    header = content[:2048]

    # 1. PDF detection (%PDF-)
    if header.startswith(b"%PDF-"):
        requires_ocr = _heuristic_pdf_requires_ocr(content)
        return FormatDetectionResult(
            mime_type="application/pdf",
            extension=".pdf",
            requires_ocr=requires_ocr,
            detection_method="magic_bytes",
        )

    # 2. PNG detection (\x89PNG\r\n\x1a\n)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return FormatDetectionResult(
            mime_type="image/png",
            extension=".png",
            requires_ocr=True,
            detection_method="magic_bytes",
        )

    # 3. JPEG detection (\xff\xd8\xff)
    if header.startswith(b"\xff\xd8\xff"):
        return FormatDetectionResult(
            mime_type="image/jpeg",
            extension=".jpg",
            requires_ocr=True,
            detection_method="magic_bytes",
        )

    # 4. TIFF detection (II*\x00 or MM\x00*)
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return FormatDetectionResult(
            mime_type="image/tiff",
            extension=".tiff",
            requires_ocr=True,
            detection_method="magic_bytes",
        )

    # 5. WebP detection (RIFF....WEBP)
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return FormatDetectionResult(
            mime_type="image/webp",
            extension=".webp",
            requires_ocr=True,
            detection_method="magic_bytes",
        )

    # 6. DOCX / ZIP archive (PK\x03\x04)
    if header.startswith(b"PK\x03\x04"):
        # Check if Word document components are present
        if b"word/" in content or b"[Content_Types].xml" in content:
            return FormatDetectionResult(
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                extension=".docx",
                requires_ocr=False,
                detection_method="magic_bytes_zip_docx",
            )

    # 7. Text-based formats (HTML, XML, JSON, CSV, TXT)
    text_result = _detect_text_format(header, filename_or_url)
    if text_result:
        return text_result

    # 8. Filename / URL extension fallback
    if filename_or_url:
        ext_result = _detect_by_extension(filename_or_url)
        if ext_result:
            return ext_result

    return FormatDetectionResult(
        mime_type="application/octet-stream",
        extension=".bin",
        requires_ocr=False,
        detection_method="fallback_octet_stream",
    )


def _detect_text_format(
    header: bytes,
    filename_or_url: Optional[str] = None,
) -> Optional[FormatDetectionResult]:
    """Inspects text-based payloads (HTML, XML, JSON, CSV, Plaintext)."""
    try:
        text_snippet = header.decode("utf-8", errors="ignore").strip()
    except Exception:
        return None

    lower_snippet = text_snippet.lower()

    # HTML
    if (
        lower_snippet.startswith("<!doctype html")
        or "<html" in lower_snippet
        or "<body" in lower_snippet
    ):
        return FormatDetectionResult(
            mime_type="text/html",
            extension=".html",
            requires_ocr=False,
            detection_method="text_html_heuristic",
        )

    # XML
    if lower_snippet.startswith("<?xml") or (
        lower_snippet.startswith("<") and ">" in lower_snippet and "</" in lower_snippet
    ):
        return FormatDetectionResult(
            mime_type="application/xml",
            extension=".xml",
            requires_ocr=False,
            detection_method="text_xml_heuristic",
        )

    # JSON
    if lower_snippet.startswith("{") or lower_snippet.startswith("["):
        try:
            json.loads(text_snippet)
            return FormatDetectionResult(
                mime_type="application/json",
                extension=".json",
                requires_ocr=False,
                detection_method="json_parser",
            )
        except Exception:
            # Partial JSON chunk
            if lower_snippet.endswith("}") or lower_snippet.endswith("]"):
                return FormatDetectionResult(
                    mime_type="application/json",
                    extension=".json",
                    requires_ocr=False,
                    detection_method="json_heuristic",
                )

    # CSV checking (comma separated with rows)
    if filename_or_url and filename_or_url.lower().endswith(".csv"):
        return FormatDetectionResult(
            mime_type="text/csv",
            extension=".csv",
            requires_ocr=False,
            detection_method="filename_csv",
        )

    lines = text_snippet.splitlines()
    if len(lines) >= 2 and all("," in line for line in lines[:3]):
        return FormatDetectionResult(
            mime_type="text/csv",
            extension=".csv",
            requires_ocr=False,
            detection_method="csv_delimiters",
        )

    # Generic Plaintext
    if text_snippet and all(ord(c) < 128 for c in text_snippet[:100]):
        ext = ".txt"
        mime = "text/plain"
        if filename_or_url and filename_or_url.lower().endswith(".csv"):
            ext = ".csv"
            mime = "text/csv"
        return FormatDetectionResult(
            mime_type=mime,
            extension=ext,
            requires_ocr=False,
            detection_method="plaintext_ascii",
        )

    return None


def _detect_by_extension(filename_or_url: str) -> Optional[FormatDetectionResult]:
    """Fallback detection using file extension."""
    ext = os.path.splitext(filename_or_url.split("?")[0])[1].lower()
    guessed_type, _ = mimetypes.guess_type(filename_or_url)

    if ext in (".jpg", ".jpeg"):
        return FormatDetectionResult("image/jpeg", ".jpg", True, "extension_fallback")
    if ext == ".png":
        return FormatDetectionResult("image/png", ".png", True, "extension_fallback")
    if ext in (".tiff", ".tif"):
        return FormatDetectionResult("image/tiff", ".tiff", True, "extension_fallback")
    if ext == ".webp":
        return FormatDetectionResult("image/webp", ".webp", True, "extension_fallback")
    if ext == ".pdf":
        return FormatDetectionResult("application/pdf", ".pdf", False, "extension_fallback")
    if ext == ".docx":
        return FormatDetectionResult(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
            False,
            "extension_fallback",
        )
    if ext in (".html", ".htm"):
        return FormatDetectionResult("text/html", ".html", False, "extension_fallback")
    if ext == ".csv":
        return FormatDetectionResult("text/csv", ".csv", False, "extension_fallback")
    if ext == ".json":
        return FormatDetectionResult("application/json", ".json", False, "extension_fallback")
    if ext == ".xml":
        return FormatDetectionResult("application/xml", ".xml", False, "extension_fallback")
    if ext == ".txt":
        return FormatDetectionResult("text/plain", ".txt", False, "extension_fallback")

    if guessed_type and guessed_type in MIME_TO_EXTENSION_MAP:
        return FormatDetectionResult(
            mime_type=guessed_type,
            extension=MIME_TO_EXTENSION_MAP[guessed_type],
            requires_ocr=is_ocr_mime(guessed_type),
            detection_method="mimetypes_guess",
        )

    return None


def _heuristic_pdf_requires_ocr(pdf_bytes: bytes) -> bool:
    """
    Lightweight heuristic to evaluate whether a PDF is a raster/scanned document.
    Scanned PDFs typically contain image XObjects (/Subtype /Image) with no or
    negligible text blocks (/Font or BT ... ET text streams).
    """
    # Sample up to 64KB
    sample = pdf_bytes[:65536]

    has_font = b"/Font" in sample
    has_text_blocks = b"BT" in sample and b"ET" in sample
    has_images = b"/Image" in sample or b"/XObject" in sample

    # If it contains raster images and no font definitions, it is almost certainly a scan
    if has_images and not has_font and not has_text_blocks:
        return True

    return False
