"""
NEXO Data Platform - Document Downloader & Content Validator
Fetches documents, validates HTTP status, MIME type, magic bytes, and quarantines failures.
"""

import os
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Dict, Any

from config.logging_config import get_logger
from app.collector.polite_client import PoliteHttpClient, FetchResult
from app.ingestion.format_detector import (
    detect_format,
    calculate_sha256,
    FormatDetectionResult,
)
from app.ingestion.validation import validate_file_size, validate_mime_type

logger = get_logger("collector.downloader")


@dataclass
class DownloadResult:
    """Outcome of document download and format validation."""
    success: bool
    url: str
    final_url: str
    content: bytes
    sha256: str
    file_size: int
    mime_type: str
    extension: str
    requires_ocr: bool
    detection_method: str
    error_message: Optional[str] = None
    failure_reason: Optional[str] = None


class DocumentDownloader:
    """
    Downloads and validates official government documents against content signatures.
    Quarantines failed or corrupted downloads to data/failed/.
    """

    def __init__(
        self,
        client: Optional[PoliteHttpClient] = None,
        quarantine_dir: Optional[str] = None,
    ):
        self.client = client or PoliteHttpClient()
        self.quarantine_dir = quarantine_dir or os.path.join("data", "failed")
        os.makedirs(self.quarantine_dir, exist_ok=True)

    def download_and_validate(self, url: str) -> DownloadResult:
        """
        Fetches the URL, validates HTTP status, checks MIME and magic bytes,
        and computes SHA-256.
        """
        fetch_res: FetchResult = self.client.fetch(url)

        # 1. Validate HTTP Status
        if not fetch_res.success:
            reason = f"HTTP {fetch_res.status_code}: {fetch_res.error_message or 'Fetch failed'}"
            self._quarantine_failure(url, reason)
            return DownloadResult(
                success=False,
                url=url,
                final_url=fetch_res.final_url,
                content=b"",
                sha256="",
                file_size=0,
                mime_type="",
                extension="",
                requires_ocr=False,
                detection_method="http_error",
                error_message=fetch_res.error_message,
                failure_reason=reason,
            )

        content = fetch_res.content
        file_size = len(content)

        # 2. Validate non-empty file
        if file_size == 0:
            reason = "Empty document content (0 bytes)"
            self._quarantine_failure(url, reason)
            return DownloadResult(
                success=False,
                url=url,
                final_url=fetch_res.final_url,
                content=b"",
                sha256="",
                file_size=0,
                mime_type="",
                extension="",
                requires_ocr=False,
                detection_method="empty_content",
                error_message=reason,
                failure_reason=reason,
            )

        # 3. File size check
        try:
            validate_file_size(file_size)
        except Exception as exc:
            reason = f"File size validation error: {exc}"
            self._quarantine_failure(url, reason)
            return DownloadResult(
                success=False,
                url=url,
                final_url=fetch_res.final_url,
                content=b"",
                sha256="",
                file_size=file_size,
                mime_type="",
                extension="",
                requires_ocr=False,
                detection_method="size_check",
                error_message=str(exc),
                failure_reason=reason,
            )

        # 4. Format & Magic Bytes Signature Detection
        detection: FormatDetectionResult = detect_format(
            content=content,
            filename_or_url=fetch_res.final_url or url,
        )

        # Check for HTML error pages masquerading as PDFs
        url_lower = (fetch_res.final_url or url).lower()
        if (url_lower.endswith(".pdf") or "pdf" in url_lower) and detection.mime_type in ("text/html", "application/xhtml+xml"):
            reason = "Content mismatch: Expected PDF but received HTML response (likely portal error or login page)"
            self._quarantine_failure(url, reason, content=content[:2048])
            return DownloadResult(
                success=False,
                url=url,
                final_url=fetch_res.final_url,
                content=b"",
                sha256="",
                file_size=file_size,
                mime_type=detection.mime_type,
                extension=detection.extension,
                requires_ocr=False,
                detection_method=detection.detection_method,
                error_message=reason,
                failure_reason=reason,
            )

        # 5. Calculate SHA-256
        sha256 = calculate_sha256(content)

        return DownloadResult(
            success=True,
            url=url,
            final_url=fetch_res.final_url,
            content=content,
            sha256=sha256,
            file_size=file_size,
            mime_type=detection.mime_type,
            extension=detection.extension,
            requires_ocr=detection.requires_ocr,
            detection_method=detection.detection_method,
        )

    def _quarantine_failure(
        self,
        url: str,
        reason: str,
        content: Optional[bytes] = None,
    ) -> None:
        """Records a failure record and optional sample into data/failed/."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "failure_reason": reason,
        }
        log_file = os.path.join(self.quarantine_dir, "failed_downloads.jsonl")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as exc:
            logger.warning(f"Could not record quarantine log: {exc}")
