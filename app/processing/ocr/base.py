"""
NEXO Data Platform - Pluggable OCR Base Interface
Defines the abstract interface for OCR providers and engines.
"""

from abc import ABC, abstractmethod
from typing import Optional
from app.processing.models import OCRResult


class BaseOCREngine(ABC):
    """Abstract interface for all OCR provider adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the OCR engine."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks whether the OCR engine and required dependencies are installed/configured."""
        pass

    @abstractmethod
    def process(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> OCRResult:
        """
        Executes OCR on image or scanned document bytes.
        Returns an OCRResult containing text, confidence, language, and status.
        """
        pass
