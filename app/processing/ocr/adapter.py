"""
NEXO Data Platform - OCR Engine Adapters & Registry
Provides default No-Op, Mock, and extensible OCR engine adapters.
"""

from typing import Optional, Dict, Any
from app.processing.models import OCRResult, OCRStatus
from app.processing.ocr.base import BaseOCREngine
from config.logging_config import get_logger

logger = get_logger("processing.ocr")


class NoOpOCREngine(BaseOCREngine):
    """
    Default safe OCR adapter when no external OCR provider (e.g. Tesseract, Google Vision)
    is configured. Accurately marks OCR status as PENDING or SKIPPED without fabricating text.
    """

    @property
    def name(self) -> str:
        return "noop_ocr"

    def is_available(self) -> bool:
        return True

    def process(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> OCRResult:
        logger.info(
            f"No-op OCR invoked for '{filename or 'unknown'}' (lang hint: {language_hint}). "
            f"Flagging as PENDING without generating synthetic text."
        )
        return OCRResult(
            status=OCRStatus.PENDING,
            text="",
            confidence=None,
            language=language_hint,
            failure_reason="OCR engine not configured in environment. Queued for OCR processing.",
        )


class MockOCREngine(BaseOCREngine):
    """Configurable mock OCR engine for testing."""

    def __init__(
        self,
        mock_text: str = "Sample OCR Extracted Government Text",
        confidence: float = 0.95,
        language: str = "en",
        should_fail: bool = False,
    ):
        self.mock_text = mock_text
        self.confidence = confidence
        self.language = language
        self.should_fail = should_fail

    @property
    def name(self) -> str:
        return "mock_ocr"

    def is_available(self) -> bool:
        return True

    def process(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> OCRResult:
        if self.should_fail:
            return OCRResult(
                status=OCRStatus.FAILED,
                text="",
                confidence=0.0,
                language=language_hint or self.language,
                failure_reason="Mock OCR execution error triggered for testing.",
            )
        return OCRResult(
            status=OCRStatus.COMPLETED,
            text=self.mock_text,
            confidence=self.confidence,
            language=language_hint or self.language,
            failure_reason=None,
        )


class OCRAdapter:
    """Central adapter managing OCR routing and execution."""

    def __init__(self, engine: Optional[BaseOCREngine] = None):
        self.engine = engine or NoOpOCREngine()

    def set_engine(self, engine: BaseOCREngine) -> None:
        self.engine = engine

    def process(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> OCRResult:
        try:
            return self.engine.process(
                file_bytes=file_bytes,
                filename=filename,
                language_hint=language_hint,
            )
        except Exception as exc:
            logger.error(f"OCR execution failed on '{filename}': {exc}")
            return OCRResult(
                status=OCRStatus.FAILED,
                text="",
                confidence=0.0,
                language=language_hint,
                failure_reason=str(exc),
            )
