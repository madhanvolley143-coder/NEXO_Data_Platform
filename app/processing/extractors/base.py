"""
NEXO Data Platform - Base Content Extractor Interface
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.processing.models import ExtractionResult


class BaseExtractor(ABC):
    """Abstract base class for all file format extractors."""

    @property
    @abstractmethod
    def extractor_name(self) -> str:
        """Name of the extraction method/library."""
        pass

    @abstractmethod
    def extract(
        self,
        file_bytes: bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """
        Extracts textual content from file bytes.
        Returns an ExtractionResult with extracted text, page count, and metrics.
        """
        pass
